# SeMA(서울시립미술관) 전시 크롤러

서울시립미술관 본관과 분관(북서울·서서울·남서울·사진·미술아카이브·난지·백남준의 집 등)의
현재 진행중·예정 전시를 매일 자동으로 수집해서 **CSV·JSON**으로 저장하는 도구입니다.

전시맵(`artmap.ai.kr`)이 이 데이터를 읽어가게 만들면, **종료된 전시는 자동으로 빠지고
새 전시는 자동으로 들어옵니다.**

---

## 1. 폴더 구성

```
sema_crawler/
├── crawler.py                       ← 본체 (Python)
├── venues.json                      ← 분관 정보(주소·좌표)
├── requirements.txt                 ← 필요 라이브러리
├── data/
│   ├── exhibitions_YYYY-MM-DD.csv   ← 그날 수집 결과 (히스토리)
│   ├── exhibitions_YYYY-MM-DD.json
│   ├── exhibitions_latest.csv       ← 최신 스냅샷 (사이트가 읽을 파일)
│   └── exhibitions_latest.json
├── .github/workflows/sema_daily.yml ← GitHub 자동 실행 설정
└── README.md
```

---

## 2. 로컬에서 한 번 돌려보기 (선택)

본인 컴퓨터에 Python이 있다면 (대부분 맥은 기본 설치).

```bash
cd sema_crawler
pip install -r requirements.txt
python crawler.py
```

`data/exhibitions_latest.csv`가 만들어지면 성공입니다.

---

## 3. GitHub Actions로 매일 자동 실행하기 (권장)

본인 컴퓨터를 켜놓지 않아도 GitHub 서버가 매일 새벽에 알아서 돌립니다. **무료.**

### 3-1. GitHub 저장소(repo) 만들기

1. `github.com` 가입 → 우측 상단 `+` → `New repository`
2. 이름: `artmap-sema-crawler` (아무거나)
3. **Public**으로 만들기 (Private도 가능, 단 무료 한도 다름)
4. `Create repository`

### 3-2. 이 폴더의 모든 파일을 저장소에 올리기

가장 쉬운 방법은 **GitHub Desktop** 앱.

1. <https://desktop.github.com> 에서 앱 다운로드·설치
2. `File → Add Local Repository` → 이 `sema_crawler` 폴더 선택
3. 화면 안내대로 `Publish repository`

또는 웹 UI에서 `Add file → Upload files` 로 폴더 통째 드래그.

### 3-3. 권한 확인

저장소에서 `Settings → Actions → General` → 맨 아래 `Workflow permissions`
→ **Read and write permissions** 체크 → Save.

(이게 켜져 있어야 GitHub Actions가 매일 결과 파일을 자동 커밋할 수 있습니다.)

### 3-4. 첫 실행 테스트

`Actions` 탭 → 좌측 `SeMA 전시 자동 수집 (매일)` →
`Run workflow` 버튼 → 1~2분 뒤 초록불 뜨면 OK.

`data/` 폴더에 `exhibitions_YYYY-MM-DD.csv`가 새로 들어와 있을 겁니다.

이후로는 **매일 한국시간 새벽 5시**에 알아서 돌아갑니다.

---

## 4. 사이트(artmap.ai.kr)와 연결하는 두 가지 방법

### 방법 A) JSON URL을 사이트가 직접 읽기 (가장 쉬움)

GitHub 저장소가 Public이면 `exhibitions_latest.json`은 다음 URL로 누구나 읽을 수 있습니다.

```
https://raw.githubusercontent.com/{사용자명}/artmap-sema-crawler/main/data/exhibitions_latest.json
```

`artmap.ai.kr` 코드에 다음 한 줄만 추가하면 됩니다.

```javascript
const res = await fetch('https://raw.githubusercontent.com/{사용자명}/artmap-sema-crawler/main/data/exhibitions_latest.json');
const { exhibitions } = await res.json();
// exhibitions 배열을 지도에 표시
```

Claude한테 사이트 코드를 보여주며 *"이 JSON을 fetch해서 active 상태인 전시만 지도에
표시하도록 코드 수정해줘"* 라고 부탁하면 됩니다.

### 방법 B) 구글 스프레드시트로 한 번 거쳐가기 (검수 단계가 필요한 경우)

1. 새 스프레드시트를 만들고 시트 이름을 `sema` 로.
2. GitHub Actions의 마지막 단계에 한 줄 더 추가해서 시트에 자동 import.
   → 이건 구글 서비스 계정 키 발급이 필요해서 살짝 번거롭습니다.
3. 본인이 보고 OK한 전시만 `status=approved` 로 바꾸면 사이트에 노출.

처음에는 방법 A로 가고, 검수 단계가 필요해지면 방법 B로 옮기는 것을 권합니다.

---

## 5. 동작 원리 (간단히)

1. `https://sema.seoul.go.kr/kr/whatson/landing?...&whenType=FROM_TODAY` 로 진행중 전시 목록 페이지를 가져옴.
2. HTML에서 카드별로 **제목 / 장소 / 기간 / 썸네일**을 BeautifulSoup으로 추출.
3. `venues.json` 의 분관 별칭과 매칭해서 **주소·좌표**를 채움.
4. 오늘 날짜와 비교해 `upcoming / active / ended / permanent` 상태를 자동 표시.
5. 같은 폴더의 `data/` 에 날짜별·최신본 두 가지로 저장.

---

## 6. 자주 일어나는 일 / 대응

| 증상 | 원인 / 해결 |
|---|---|
| 새 전시가 안 들어옴 | GitHub `Actions` 탭에서 빨간 X 클릭 → 로그 복사 → Claude한테 그대로 붙여넣어 진단 요청 |
| SeMA 사이트 구조가 바뀜 | `parse_list_page()` 함수의 셀렉터를 새 구조에 맞게 수정 (Claude한테 SeMA 페이지 HTML 보여주며 수정 요청) |
| 좌표가 None으로 나옴 | `venues.json` 의 별칭(`aliases`)에 새 분관명·표기 추가 |
| 충무아트센터처럼 외부 협력전시 | 정상. SeMA 분관이 아니라 좌표 None — 본인이 검수 단계에서 직접 좌표 보정 |

---

## 7. 확장 계획

이게 잘 굴러가는 걸 1~2주 보고 나면 같은 패턴으로 다음을 추가하세요.

- `mmca_crawler.py` — 국립현대미술관(서울/덕수궁/과천/청주)
- `arko_crawler.py` — 아르코미술관
- `gokams_api.py` — 예술경영지원센터 API (공식 OpenAPI 있음)
- `culture_seoul_api.py` — 서울시 문화포털 API (공식 OpenAPI 있음)

각 크롤러가 같은 스키마(CSV 컬럼)를 출력하면, 사이트는 단일 `exhibitions_latest.json` 하나만 읽으면 됩니다.

---

## 8. 법적 주의 (꼭 읽기)

- 이 크롤러는 **공공기관(서울시립미술관)** 데이터만 수집합니다.
- 요청 간격 **3초**, User-Agent에 본인 연락처 명시(`crawler.py` 상단에서 수정 가능).
- **이미지·소개글 원문 전체 복사 금지** — 썸네일은 SeMA 서버 URL을 그대로 링크로 걸고,
  소개글은 본인이 직접 짧게 요약하거나 SeMA 상세 페이지로 링크 처리하세요.
- 민간 갤러리로 확장할 때는 각 사이트의 `robots.txt` 와 이용약관을 반드시 먼저 확인.

---

작성: 2026-05-11 / 운영자: 고수길 (sookil05114@gmail.com)
