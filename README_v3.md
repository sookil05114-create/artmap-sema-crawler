# v3 — 을지로 갤러리 자동화 + URL 제보 시스템 (1차)

## 들어있는 것

```
gallery_crawler/
  ├ venues.json           # 을지로 26곳 시드 (엑셀에서 변환)
  └ crawler.py            # 매주 1회 26곳 인스타 자동 수집
submissions/
  ├ processor.py          # URL 한 줄 받아 OG 메타 → Claude API → pending 큐
  ├ requirements.txt
  └ data/
      └ pending_queue.json   # 검수 대기 큐 (빈 상태로 시작)
.github/workflows/
  └ gallery_weekly.yml    # 매주 월요일 새벽 6시 자동 실행
```

## 동작 흐름 한눈에

```
[제보자 URL]   ────┐                ┌──── [매주 1회 자동, 26곳]
                  ↓                ↓
            submissions/processor.py — fetch OG 메타 (FB bot UA 트릭)
                  ↓
            Claude Haiku API — 전시 정보 구조화
                  ↓
            submissions/data/pending_queue.json (status=pending)
                  ↓
            [본인 1-클릭 검수] ← 2차 작업에서 만들 검수 화면
                  ↓
            merger가 approved 항목만 통합 데이터에 합쳐 사이트에 노출
```

## 왜 인스타 OG 메타가 작동하는가

GitHub Actions의 IP에서 일반 Chrome UA로 인스타에 접근하면 빈 메타만 옵니다.
하지만 **Facebook bot UA (`facebookexternalhit/1.1`)** 를 쓰면 인스타가 자기 봇으로 인식해서
정상적으로 OG 제목·설명·이미지를 반환합니다. (인스타가 페이스북 소유)

이 트릭이 핵심이라 `submissions/processor.py` 의 `fetch_page()` 함수에서
URL이 instagram.com 도메인이면 자동으로 FB bot UA를 사용합니다.

## GitHub에 올릴 때

기존 저장소(`artmap-sema-crawler`)에 이 폴더들을 그대로 추가하세요. SeMA·MMCA 자동화에는
영향 없이 새 폴더가 옆에 생기는 구조입니다.

## 다음 (2차 작업)

1차 검증 (제보 URL 하나가 큐에 정상으로 들어오는지) 끝나면 추가할 것:

- `admin/admin_review.html` — 단일 파일 검수 페이지, pending 큐를 카드로 보고 1-클릭 승인
- `merger/merge.py` 업데이트 — approved 항목을 `all_venues_seoul_only.json`에 합침
- 사이트의 "제보하기" 폼이 URL 한 줄을 받아 자동으로 큐에 넣도록 사이트 측 작업
