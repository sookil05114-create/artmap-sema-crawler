# v2 업그레이드 — SeMA + MMCA + 분관별 그룹화

## 무엇이 새로 들어왔나

1. **SeMA 크롤러 v2** — `region` 필드 추가, **분관별 그룹화 출력** 추가
2. **MMCA 크롤러** (신규) — 4관(서울·덕수궁·과천·청주) + 어린이미술관, 전시 + 교육프로그램
3. **통합 merger** (신규) — SeMA + MMCA를 단일 JSON으로 합쳐 사이트가 URL 하나만 알면 끝
4. **워크플로우 통합** — 매일 새벽 한 번에 다 돌고 합쳐 커밋

오늘(2026-05-11) 기준 자동 수집 결과:

- 전시 36건 (SeMA 14 + MMCA 22) / **서울만 27건**
- 분관 마커 11곳 / **서울 8곳**
- 교육프로그램 15건 (MMCA, 어린이·청소년·성인·교사 모두 포함)

---

## 1) GitHub 저장소 어떻게 업데이트하나

이미 만들어둔 `artmap-sema-crawler` 저장소에 **추가**하는 형식입니다. 새로 저장소를 만들 필요 없어요.

### A. ZIP 풀고 안의 내용물 통째로 업로드

1. ZIP 파일을 더블클릭으로 풀면 `v2_package` 폴더가 생깁니다.
2. Finder에서 `Cmd + Shift + .` 눌러 숨김 파일 보이게.
3. `v2_package` 폴더 안에 들어가서 **8개 항목 전부 선택** (`Cmd + A`):
   - `.github` (폴더, 숨김)
   - `sema_crawler` (폴더)
   - `mmca_crawler` (폴더) ← 신규
   - `merger` (폴더) ← 신규
   - `UPGRADE_GUIDE.md`
   - `README.md`
   - `apply_to_artmap_v2.md` ← 사이트 적용 가이드
   - (그 외 보이는 항목 전부)
4. GitHub 저장소 페이지에서 **Add file → Upload files**
5. 위에서 선택한 항목들을 통째로 드래그
6. *Replace existing files?* 같은 안내가 뜨면 **YES**(덮어쓰기) — `sema_crawler` 안의 파일들이 v2로 갱신됩니다.
7. 커밋 메시지: `v2 업그레이드 — MMCA 추가, 분관별 그룹화`
8. **Commit changes** 클릭.

### B. 첫 실행 확인

저장소 상단 **Actions** 탭 → 좌측 **`SeMA + MMCA 전시·교육 자동 수집 (매일)`** 클릭 → **Run workflow** → 초록 Run workflow.

2~3분 뒤 초록 체크면 성공. 새 데이터가 `sema_crawler/data/`, `mmca_crawler/data/`, `merger/data/`에 모두 들어가 있을 거예요.

---

## 2) 사이트가 받아갈 새 URL들

이제 단일 URL **하나만** 알면 모든 데이터가 들어옵니다:

### 가장 추천 (서울만, 분관별 묶음 — 지도 마커용)

```
https://raw.githubusercontent.com/sookil05114-create/artmap-sema-crawler/main/merger/data/all_venues_seoul_only.json
```

이 JSON 안에는 분관별로 묶인 전시 리스트가 있습니다. 한 분관(예: 서서울미술관)에서 동시에 진행되는 4건이 한 venue 객체의 `exhibitions` 배열로 들어가 있어, **마커 하나 클릭 시 4건을 리스트로 보여줄 수 있습니다.**

### 그 외 활용 가능한 URL

| 용도 | URL |
|---|---|
| 전시 전체 평면 (검색·필터용) | `.../merger/data/all_exhibitions_latest.json` |
| 전시 전체 — 서울만 | `.../merger/data/all_exhibitions_seoul_only.json` |
| 분관별 묶음 — 전국 | `.../merger/data/all_venues_latest.json` |
| 분관별 묶음 — **서울만** (★ 메인) | `.../merger/data/all_venues_seoul_only.json` |
| 교육프로그램 (별도 카테고리) | `.../merger/data/all_programs_latest.json` |

소스별 원본도 그대로 남아 있어요 (필요 시):

- `sema_crawler/data/exhibitions_latest.json`
- `mmca_crawler/data/exhibitions_latest.json`

---

## 3) 사이트 코드 수정 — Claude한테 줄 프롬프트

`apply_to_artmap_v2.md` 파일을 보시면 됩니다. 핵심 요지:

- 메인 데이터는 `all_venues_seoul_only.json` — 분관별로 묶여 있으니 사이트는 venue 단위로 마커 찍기
- 교육프로그램은 별도 카테고리 → 별도 페이지 또는 별도 필터 탭
- 마커 클릭 시 그 분관의 전시 리스트가 카드 형태로 펼쳐지도록

---

## 4) 데이터 흐름 한눈에 보기

```
매일 새벽 5시 (한국시간)
  │
  ├─ SeMA 크롤러 → sema_crawler/data/
  ├─ MMCA 크롤러 → mmca_crawler/data/  (전시 + 교육)
  │
  └─ Merger → merger/data/
       ├── all_exhibitions_latest.json      (평면 36건)
       ├── all_venues_latest.json           (분관별 11곳)
       ├── all_exhibitions_seoul_only.json  (서울 27건)
       ├── all_venues_seoul_only.json       ★ 사이트 메인 (서울 8곳)
       └── all_programs_latest.json         (교육 15건)
            │
            ▼
       artmap.ai.kr (사이트가 raw URL로 fetch)
```
