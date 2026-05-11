# artmap.ai.kr 에 SeMA 데이터 연결하기 — 실무 안내

크롤러가 매일 만들어내는 `exhibitions_latest.json` 을 사이트가 읽어
지도에 표시하게 만드는 가장 빠른 경로입니다.

---

## A. JSON 데이터 형태 (실제로 들어오는 모양)

```json
{
  "generated_at": "2026-05-11T11:52:25Z",
  "source": "sema",
  "count": 14,
  "exhibitions": [
    {
      "id": "a1b2c3d4e5f6",
      "source": "sema",
      "title": "난지미술창작스튜디오 20주년 기념전 《사랑의 기원》",
      "venue_raw": "서울시립미술관 서소문본관",
      "venue_key": "seosomun",
      "venue_name": "서울시립미술관 서소문본관",
      "address": "서울 중구 덕수궁길 61",
      "lat": 37.5641,
      "lng": 126.9737,
      "start_date": "2026-04-30",
      "end_date": "2026-09-06",
      "price": "무료",
      "url": "",
      "thumbnail": "https://sema.seoul.go.kr/common/imgFileView?FILE_ID=1005949",
      "status": "active",
      "collected_at": "2026-05-11T11:52:25Z"
    }
  ]
}
```

`status` 값은 다음 네 가지뿐입니다.

- `active`    — 현재 진행중 (오늘 날짜가 기간 안)
- `upcoming`  — 시작 전
- `ended`     — 종료됨
- `permanent` — 상시 전시

**사이트가 표시할 것은 `active`(+선택적으로 `upcoming`)** 만 골라쓰면 됩니다.

---

## B. Claude한테 줄 적용 프롬프트 (그대로 복사)

```
내 사이트는 artmap.ai.kr 이고, Claude로 바이브코딩해서 만들었어.
현재 진행중 전시를 표시하는 코드 부분을 다음 JSON URL을 fetch해 그리도록
수정해줘.

URL:
https://raw.githubusercontent.com/{내GitHub사용자명}/artmap-sema-crawler/main/data/exhibitions_latest.json

요구사항:
1. 페이지 로드 시 한 번 fetch.
2. `exhibitions` 배열 중 `status === "active"` 인 것만 표시.
3. 각 카드: title, venue_name, 기간(start_date~end_date), thumbnail, price.
4. 클릭시 SeMA 분관 공식 페이지(venues.json의 official_url)로 이동. url
   필드가 비어있으면 SeMA 메인으로.
5. 지도에는 (lat, lng) 좌표로 마커 찍기. 좌표 null 인 항목은 리스트에만 표시.
6. fetch 실패시 사용자에게 "잠시 후 다시 시도" 메시지.
7. 5분간 브라우저에 캐시(같은 세션 내).

먼저 어떤 파일을 수정해야 하는지 알려주고, 다음 응답에서 수정된 코드 전체를 보여줘.
```

이 한 통의 메시지면 Claude가 작업합니다. 응답이 너무 길어 끊기면
*"이어서"* 라고만 보내세요.

---

## C. 데이터 신선도 확인

- GitHub 저장소에서 `data/` 폴더를 열어 **가장 위에 있는 커밋 시각**을
  보면 마지막 자동 수집이 언제 돌았는지 알 수 있습니다.
- 사이트 푸터에 *"전시 정보 최종 업데이트: 2026-05-11"* 같은 표기를 두면
  방문자도 신뢰합니다 — 위 JSON 의 `generated_at` 을 그대로 표시.

---

## D. 검수 단계를 끼우고 싶다면

크롤러가 자동 수집한 14건을 모두 그대로 사이트에 띄우는 게 부담스러우면,
중간에 본인이 한 번 보고 OK 한 것만 노출하는 흐름을 만듭니다.

1. 크롤러는 JSON 그대로 두고,
2. 본인 컴퓨터에 작은 검수 페이지 하나(`review.html`)를 만들어 둠.
   - `exhibitions_latest.json` 을 열어
   - 카드별로 `[승인]` `[수정]` `[제외]` 버튼만 있는 페이지
   - `[승인]` 누른 것만 별도 `approved.json` 에 저장
3. 사이트는 `approved.json` 만 읽음.

Claude한테 *"단일 파일 HTML로 검수 페이지 만들어줘. 입력은
exhibitions_latest.json, 출력은 approved.json"* 이라고 하면 30분이면 됩니다.

---

## E. 막힐 때 디버깅 순서

1. GitHub Actions 로그가 빨간 X 인지 → 로그 그대로 Claude한테 붙여넣기
2. 실행은 됐는데 `data/` 가 비어있음 → SeMA 사이트 구조 변경 의심.
   `crawler.py` 의 `parse_list_page` 셀렉터 수정 필요.
3. 사이트에서 fetch 실패 → JSON URL 을 브라우저 주소창에 직접 쳐서 열어봄.
4. 좌표 누락 → `venues.json` 의 별칭 추가.
