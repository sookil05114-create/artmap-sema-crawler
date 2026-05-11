# artmap.ai.kr 적용 가이드 v2

v1의 단일 URL 방식에서, 이제 **분관별 그룹 + 카테고리 분리**가 가능한 구조로 업그레이드됩니다.

---

## 데이터 모양 (메인)

URL: `https://raw.githubusercontent.com/sookil05114-create/artmap-sema-crawler/main/merger/data/all_venues_seoul_only.json`

```json
{
  "generated_at": "2026-05-11T...",
  "sources": ["sema", "mmca"],
  "filter": "region=seoul",
  "venue_count": 8,
  "venues": [
    {
      "venue_key": "seoseoul",
      "venue_name": "서울시립 서서울미술관",
      "region": "seoul",
      "address": "서울 금천구 시흥대로73길 70",
      "lat": 37.4581, "lng": 126.8959,
      "official_url": "https://sema.seoul.go.kr/kr/visit/seoseoul",
      "active_count": 3,
      "upcoming_count": 1,
      "exhibitions": [
        {
          "id": "...",
          "title": "SeMA 프로젝트V_얄루",
          "start_date": "2026-03-12",
          "end_date": "2026-07-26",
          "status": "active",
          "thumbnail": "https://...",
          "url": "",
          "price": "무료"
        },
        { "title": "서서울미술관 개관특별전 《우리의 시간은 여기서부터》", ... },
        { "title": "《우리의 시간은 여기서부터》 - <태각(胎刻)>", ... },
        { "title": "...개관 특별 미디어 소장품전...", "status": "upcoming", ... }
      ]
    },
    ...
  ]
}
```

핵심: **한 venue 객체 안에 그 분관에서 동시에 진행되는 전시들이 배열로 들어있음.** 좌표가 venue 단위라 지도 마커도 venue 단위로 찍히고, 클릭 시 그 안의 `exhibitions` 배열을 펼쳐 보여주면 됩니다.

---

## Claude한테 줄 프롬프트 (그대로 복사)

```
내 사이트 artmap.ai.kr 코드를 분관별 그룹화 + 카테고리 분리 구조로
업그레이드해줘.

[전시 데이터 — 메인]
https://raw.githubusercontent.com/sookil05114-create/artmap-sema-crawler/main/merger/data/all_venues_seoul_only.json

[교육프로그램 데이터 — 별도 카테고리]
https://raw.githubusercontent.com/sookil05114-create/artmap-sema-crawler/main/merger/data/all_programs_latest.json

요구사항:
1. 페이지 로드 시 두 URL을 fetch (병렬).
2. 상단에 카테고리 탭: [전시] | [교육·프로그램]  (기본 전시 선택).
3. [전시] 탭일 때:
   - 첫 fetch JSON의 venues 배열을 순회.
   - 각 venue를 (lat, lng) 좌표로 지도에 마커 1개씩 찍음.
   - 마커에 active_count + upcoming_count를 배지로 표시
     (예: "3+1" 처럼 진행중·예정 수를 같이).
   - 마커 클릭 시 사이드 패널/팝업에 그 venue의 venue_name과 
     exhibitions 배열을 카드 리스트로 표시.
   - 각 카드: title, start_date~end_date, status 뱃지(active/upcoming),
     thumbnail, price.
   - 좌측 리스트 뷰도 함께 — 분관별로 접힌 아코디언 형태,
     펼치면 그 분관의 전시들이 나옴.
4. [교육·프로그램] 탭일 때:
   - 두 번째 fetch JSON의 programs 배열을 표시.
   - 카드 단위로 보여주고, 필터: target_category (어린이/청소년/성인/교사),
     application_status (open/closed/info_only).
   - 카드에 title, target_audience, venue_name, 기간, 
     time_range, capacity, application_status 뱃지 표시.
   - application_status === "open" 이면 카드를 강조 (테두리 강조 등).
5. 푸터에 "전시 정보 최종 업데이트: YYYY-MM-DD HH:MM" 
   (각 JSON의 generated_at 기준).
6. fetch 실패 시 사용자에게 친절한 안내 ("잠시 후 다시 시도해주세요").
7. 응답을 5분간 메모리 캐시.

먼저 어떤 파일(들)을 수정해야 하는지 알려주고,
다음 응답에서 수정된 코드 전체를 보여줘. 한국어로 응답.
```

---

## 사이트 디자인 권장 사항

- **마커 디자인**: 분관에 전시가 여러 개일 때 시각적으로 알 수 있도록 마커에 숫자 배지를 다는 것을 추천합니다 (예: 서서울미술관 마커 위에 "3" 또는 "3+1").
- **클러스터 vs 분관 그룹**: 가까운 두 분관(서울관/덕수궁관)은 자동 클러스터링하지 마세요 — 이미 venue 단위로 묶여 있으니 사용자가 혼란스러워합니다.
- **전시 카드 정렬**: 한 venue 안의 `exhibitions` 배열은 시작일 빠른 순. status가 `active`인 것을 위로, `upcoming`은 아래로 묶어주면 더 좋습니다.
- **교육 탭 강조**: 신청 가능(`application_status === "open"`) 카드만 따로 모은 "지금 신청 가능" 섹션을 상단에 두면 사용자 가치가 큽니다.

---

## 데이터 검증 — 사이트에 띄우기 전 확인

오늘 기준 이런 데이터가 들어옵니다:

**전시 — 서울 8곳 분관 마커**

| 분관 | 진행중 | 예정 |
|---|---|---|
| 서울시립미술관 서소문본관 | 2 | 1 |
| 서울시립 북서울미술관 | 3 | 0 |
| 서울시립 서서울미술관 | 3 | 1 |
| 서울시립 사진미술관 | 2 | 0 |
| 서울시립 미술아카이브 | 1 | 0 |
| 국립현대미술관 서울 | 5 | 5 |
| 국립현대미술관 덕수궁 | 0 | 2 |
| 국립현대미술관 어린이미술관 | 1 | 0 |

**교육 — 15건**

- 성인: 8
- 청소년: 5
- 어린이: 1
- 교사: 1

신청 가능 상태(`open`)는 한 건만 잡힘 (대부분 `info_only` 또는 `closed`) — 정상이며, 신청 시점이 따로 정해진 프로그램이 대부분이라 그렇습니다.
