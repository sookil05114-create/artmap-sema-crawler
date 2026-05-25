# 전시맵 7차 — venues 추출 결과 (종로 + 중구 + 강남·서초)

작업일: 2026-05-25
출처: `서울미술공간_표본300_알바작업시트.xlsx` (3개 권역 시트)

## 한 줄 요약

알바 검증 174건(종로 88 + 중구 26 + 강남·서초 60) 중 운영여부=O + 검증완료=OK인 **130곳을 추출**, 기존 저장소 venues.json과 dedup 거쳐 **최종 104곳을 신규 venue로 정리**했습니다.

## 산출물

| 파일 | 설명 |
|---|---|
| **`venues_new_final.json`** | 🎯 gallery_crawler/venues.json에 머지할 최종본 (104곳, `{"_comment", "source_doc", "venues":[]}` 래퍼) |
| `venues_new.json` | 1차 raw 추출본 (130곳, dedup 전) |
| `extract_report.json` | 추출 통계 (시트별, 카테고리별, skipped 사유) |
| `dedup_decisions.md` | 📋 dedup 결정 리포트 (사용자 검토용) |
| `existing/gallery_crawler_venues.json` | 기존 저장소 venues (참고용 다운로드본) |
| `existing/craft_museum_venues.json` | 기존 craft 저장소 venues |

## 처리 흐름

```
xlsx (174 OK행)
  │
  ├─ 운영여부 필터 (휴관/X/폐관/빈값 13곳 제외)
  ↓
130곳 (활성 O 100%)
  │
  ├─ daily 크롤러 처리 제외 (sema, mmca 서울관·덕수궁관) → 3곳
  ├─ 기존 venues.json과 중복 → 21곳 제외 (을지로 16 + 종로 미술관 4 + 서울공예박물관 1)
  ├─ 신규 내부 중복 → 2곳 제외 (PKM 강남 xlsx 주소 오류, 오페라갤러리 서울)
  ↓
104곳 (최종) 
  │
  └─ venue_key: 권역_접두어 + ASCII (한글은 korean-romanizer로 자동 변환)
```

## 적용한 사용자 결정 (대화 중 확정)

| 결정 사항 | 선택 |
|---|---|
| 강남·서초 미입력 14곳 (홈/인스타 없음) | 일단 제외, 추후 추가 입력 예정 |
| 유형 포함 범위 | 미술관 + 갤러리 + 기타 모두 |
| 기존과 중복 21곳 처리 | 신규에서 완전 제외 (기존 venues.json 보완 PR은 별도) |
| venue_key 컨벤션 | 권역 접두어 (jongno_*, junggu_*, gangnam_*, seocho_*) + ASCII 통일 |
| 한가람미술관/디자인미술관 | 둘 다 등록 (FORCE_KEEP) |
| PKM 갤러리 강남 (xlsx 주소 오류) | 제외 |
| 오페라갤러리 vs 오페라갤러리 서울 | 합쳐서 1곳만 유지 |
| 전시 실시간 업데이트 방식 | venues.json부터 채우고 크롤러 확장은 다음 단계 |

## 분포

### 권역(subregion)
| | 곳 |
|---|---|
| jongno | 63 |
| gangnam | 25 |
| junggu | 6 |
| seocho | 4 |
| yongsan | 4 |
| seongdong | 2 |
| **합계** | **104** |

> 💡 `yongsan`/`seongdong`은 시트는 강남·서초였지만 주소가 다른 구로 등록된 케이스 (e.g. 더페이지갤러리 = 성동구 서울숲).

### 카테고리
- 미술관: 24
- 갤러리: 76
- 기타: 4

## 알려진 한계

1. **좌표(lat/lng) 비어 있음** — Naver geocode는 `NAVER_CLIENT_ID/SECRET` secret이 필요하므로 GitHub Actions에서 자동 실행해야 합니다. 로컬에서 secret 환경변수가 있다면 별도 스크립트로 채울 수 있습니다.

2. **수동 좌표 필요 6곳은 모두 기존 venues.json에 포함** — PS센터/공간 형/FF서울/COSO/갤러리모스/서울미술관(석파정)은 이미 `gallery_crawler/venues.json`에 등록되어 있어 신규본에는 없습니다. 좌표 수정은 기존 파일에서 진행.

3. **로마자 일부 어색** — `gaelreorihyeondae` (갤러리현대) 등 자연스럽지 않은 변환이 있습니다. 자주 쓰는 영문 표기가 있는 갤러리는 venue_key 수동 보정 권장:
   - `jongno_gaelreorihyeondae` → `jongno_gallery_hyundai`
   - `jongno_gaelreoricurrent` → `jongno_gallery_*` 등

4. **xlsx 데이터 오류 발견 (사용자 보고용)**
   - PKM 갤러리 강남(강남·서초 No=?): 주소가 본점 "서울 종로구 삼청로7길 40"으로 잘못 입력
   - 알바에게 보완 요청 권장 항목

## 다음 단계

### A. GitHub에 반영 (사용자 액션)

저장소가 로컬에 클론되어 있지 않습니다. 옵션 2가지:

**옵션 1: 웹에서 직접 PR 생성**
1. https://github.com/sookil05114-create/artmap-sema-crawler 접속
2. `gallery_crawler/venues.json` 열기 → "Edit" → 기존 `venues` 배열 끝에 `venues_new_final.json`의 `venues` 배열 내용을 그대로 append (이때 wrapper의 `_comment`/`source_doc`은 무시하고 venues 항목만)
3. Commit → Create pull request

**옵션 2: 로컬 클론 후 머지** (권장 — dedup 재검증 가능)
```bash
# gh CLI 설치 (Homebrew)
brew install gh
gh auth login

# 클론
mkdir -p ~/repos && cd ~/repos
gh repo clone sookil05114-create/artmap-sema-crawler
cd artmap-sema-crawler

# 신규 venues 머지 — 기존 venues 배열에 append, venue_key dedup
python3 << 'EOF'
import json
existing = json.load(open("gallery_crawler/venues.json"))
new_pack = json.load(open("/path/to/venues_new_final.json"))
existing_keys = {v["venue_key"] for v in existing["venues"]}
added = 0
for v in new_pack["venues"]:
    if v["venue_key"] in existing_keys:
        print(f"SKIP (dup): {v['venue_key']}")
        continue
    existing["venues"].append(v)
    added += 1
print(f"+{added}곳 추가, 총 {len(existing['venues'])}곳")
json.dump(existing, open("gallery_crawler/venues.json", "w"), ensure_ascii=False, indent=2)
EOF

# 커밋 + PR
git checkout -b feat/venues-expand-jongno-junggu-gangnam
git add gallery_crawler/venues.json
git commit -m "feat(gallery_crawler): add 104 venues from 종로/중구/강남·서초 sample"
git push -u origin HEAD
gh pr create --fill
```

### B. 좌표 자동 채우기 (워크플로우 실행)

PR 머지 후 `gallery_weekly.yml` 워크플로우를 수동 실행:
```bash
gh workflow run gallery_weekly.yml
```
- 첫 실행에서 Naver geocode가 104곳 좌표를 채우고 `coords_cache.json`에 저장
- 알려진 6곳(PS센터 등)은 이미 기존 venues.json에 수동 좌표가 있어 영향 없음

### C. 후속 작업

1. **나머지 5개 권역 (용산·이태원·한남, 성북·노원·중랑, 홍대·합정·마포, 구로·관악·동작, 잠실·송파·강동) 검증** — 알바 작업 완료 후 같은 스크립트(`extract_and_convert.py`)에서 `TARGET_SHEETS` 리스트만 바꿔서 재실행
2. **xlsx 데이터 오류 보완** — PKM 갤러리 강남 주소 수정, 강남·서초 미입력 11곳 입력
3. **기존 venues.json에 검증 정보 보완** — dedup으로 빠진 21곳의 phone/email/hours/exhibit_channel을 기존 항목에 머지 (별도 PR)
4. **전시 실시간 크롤러 확장** — venues.json 확정 후 진행 (사용자가 다음 단계로 명시)

## 재현 명령

```bash
cd "/Users/gosoogil/Library/Mobile Documents/com~apple~CloudDocs/03 고수길 개인 자료/01 바이브코딩/전시맵 7차 venues_extract"

# 1) xlsx 구조 확인
python3 inspect_xlsx.py

# 2) raw 추출
python3 extract_and_convert.py
# → venues_new.json (130곳), extract_report.json

# 3) 기존 저장소 venues 다운로드 (이미 있음)
# curl -s https://raw.githubusercontent.com/sookil05114-create/artmap-sema-crawler/main/gallery_crawler/venues.json -o existing/gallery_crawler_venues.json
# curl -s https://raw.githubusercontent.com/sookil05114-create/artmap-sema-crawler/main/craft_museum_crawler/venues.json -o existing/craft_museum_venues.json

# 4) dedup 점검 (탐색용)
python3 dedup_check.py

# 5) 최종 정리 (권역 접두어 + ASCII + 화이트리스트)
python3 finalize_venues.py
# → venues_new_final.json (104곳), dedup_decisions.md
```
