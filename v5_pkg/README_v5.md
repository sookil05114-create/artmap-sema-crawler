# v5 — 갤러리 크롤러: 홈페이지 + 인스타 듀얼 수집

## 무엇이 바뀌나

기존 v3 갤러리 자동화는 **인스타 메인 페이지 OG 메타** 하나에만 의존했어요. 인스타가 캡션 기반이라 정보가 짧고, 게시물 URL이 아니라 메인 페이지 URL이면 "전시 없음"으로 빠지는 경우가 많았죠.

v5는 한 갤러리에 대해:

```
instagram_url  ─┐
                ├─► fetch_combined() ─► call_claude_multi() ─► 통합 추출 1건
official_url   ─┘
```

둘 다 채워져 있으면 양쪽을 같이 보고, 한쪽만 있어도 동작합니다. 둘 다 비어있으면 그 갤러리는 자동 스킵.

홈페이지는 보통 정식 표기(전시명·작가·기간)가 더 정확하고, 인스타는 임박한 일정·이미지가 더 빠르거든요. 두 소스를 교차 확인하면 정확도가 한 단계 올라갑니다.

## 들어있는 것

```
v5_pkg/
  submissions/
    processor.py        ★ fetch_combined / call_claude_multi 헬퍼 추가 (기존 함수 호환)
  gallery_crawler/
    crawler.py          ★ v2 — 두 URL 합쳐 처리
  README_v5.md          이 문서
```

**파일 두 개만 덮어쓰면 끝.** venues.json·워크플로우 yml은 손대지 않습니다.

## STEP 1 — GitHub에 두 파일 덮어쓰기

ZIP 풀어서 두 파일을 GitHub 저장소에 통째로 드래그:

- `submissions/processor.py` → 기존 v3 파일 **Replace**
- `gallery_crawler/crawler.py` → 기존 v3 파일 **Replace**

커밋 메시지: `v5 — 갤러리 크롤러 듀얼 fetch (홈페이지 + 인스타)`

## STEP 2 — `gallery_crawler/venues.json` 에 `official_url` 채우기

지금 26곳 모두 `official_url`이 `""` 빈 값이에요. 본인이 알고 있는 곳부터 채우면 됩니다.

GitHub에서 `gallery_crawler/venues.json` 파일을 열고 **연필 아이콘 클릭 → 직접 편집**.

```json
{
  "venue_key": "euljiro_doosanartcenter_gallery",
  "venue_name": "두산갤러리",
  ...
  "official_url": "https://www.doosanartcenter.com/ko/gallery",   ← 이 부분만 채우면 됨
  ...
}
```

**팁 — 어떤 URL을 넣을까**

- 갤러리 홈페이지 메인 (예: `https://galleryloop.com`) → 좋음
- 갤러리 홈페이지의 **"현재 전시" 또는 "Exhibition" 페이지** (예: `https://www.doosanartcenter.com/ko/gallery`) → **더 좋음**. 보통 OG 메타가 현재 전시로 채워져 있음
- 인스타 게시물 URL을 official_url로 넣지는 마세요 (그건 instagram_url 자리)
- 홈페이지가 없는 갤러리(작은 공간 등)는 `""` 빈 값 그대로 두기 — 자동으로 인스타만 사용됨

**26곳 다 한 번에 채울 필요 없어요.** 한두 곳부터 채워서 검증하고, 잘 되면 나머지 추가하는 식이 안전합니다.

## STEP 3 — 한 곳 dry-run (강력 추천)

본인이 채운 갤러리 하나만 골라 즉시 돌려보면 됩니다.

GitHub → Actions → `Gallery weekly` 워크플로우 → `Run workflow` 클릭.

또는 본인 컴퓨터에서 직접:

```bash
cd <repo>
export ANTHROPIC_API_KEY=sk-...
python gallery_crawler/crawler.py --only euljiro_doosanartcenter_gallery
```

성공하면 `submissions/data/pending_queue.json`에 그 갤러리의 전시 1건이 status=pending으로 들어옵니다. 검수 화면(admin_review.html)을 열어서 카드가 잘 떴는지 확인.

카드의 `source_urls` 필드를 보면 인스타와 홈페이지 둘 다에서 가져왔는지, 어느 쪽 정보가 채택됐는지(`extracted.sources_used`) 확인할 수 있어요.

## STEP 4 — 매주 자동 수집

v3에서 이미 깔린 `.github/workflows/gallery_weekly.yml` 이 매주 월요일 새벽 6시(KST)에 26곳 전체를 자동으로 돕니다. v5는 코드만 갈아끼우는 거라 워크플로우 변경 없음.

## 트러블슈팅

**Q. 홈페이지 fetch가 실패해요 (특정 갤러리)**
→ 그 사이트가 봇 차단을 하거나(403/429), JS로만 렌더되는 SPA(빈 페이지)인 경우. 그쪽은 `official_url`을 비우고 인스타만 쓰면 됨. v5는 한쪽이 실패해도 다른 쪽으로 계속 진행합니다.

**Q. 같은 전시가 큐에 두 번 들어와요**
→ id 시드가 `gallery|venue_key|title` 이라 title이 미묘하게 다르면 새 항목으로 보일 수 있음. 검수 화면에서 한쪽을 [반려] 처리하면 끝.

**Q. Claude API 비용이 늘어나나요?**
→ 갤러리당 호출 횟수는 1회로 동일 (멀티 URL을 한 프롬프트에 합쳐 보냄). 토큰은 약간 늘지만(홈페이지 본문 추가), 한 번 호출당 입력 7~8천 토큰 → 출력 600토큰 정도라 Haiku 기준 미미합니다.

**Q. 카드의 source_urls 필드를 검수 화면에서 못 보겠어요**
→ admin_review.html은 v4 기준이라 source_urls 필드는 표시되지 않을 수 있어요. 필요하면 다음 작업으로 검수 화면에 "출처 보기 — instagram / homepage" 토글을 추가할 수 있습니다.

---

## 다음 단계 후보

1. **검수 화면(admin_review.html)에 source_urls 표시 추가** — 어느 쪽 정보가 채택됐는지 검수자가 한눈에 보게
2. **official_url 자동 후보 제안** — venues.json에 빈 official_url 갤러리에 대해 WebSearch로 후보 1~2개를 venues.json 주석으로 넣어줌 (필요하면 진행)
3. **522개 아카이브** — v5 검증 끝나면 더 큰 갤러리 풀로 확장
