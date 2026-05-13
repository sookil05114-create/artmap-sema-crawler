# v4 — 검수 화면 + merger 통합

## 들어있는 것

```
admin/admin_review.html      ★ 검수 페이지 (브라우저에서 열어 사용)
merger/merge.py              ★ 갱신본 — approved 제보를 통합 데이터에 합침
```

기존 `merger/merge.py`를 v4로 **덮어쓰기** 하면 됩니다. `admin/admin_review.html` 은 GitHub에 올리되, **사용은 본인 브라우저에서 직접** 열어요 (GitHub Pages로 호스팅도 가능).

## 사용 흐름 한눈에

```
[제보 들어옴 (URL 한 줄)]
  → submissions/processor.py → AI 추출 → pending_queue.json (status=pending)
                                                  ↓
                                  본인이 admin_review.html 열기
                                                  ↓
                                  카드 보면서 [승인]/[수정]/[반려] 1-클릭
                                                  ↓
                                  PAT가 GitHub에 직접 commit (자동)
                                                  ↓
              매일 새벽 5시 자동 merger 실행 (또는 본인이 수동 트리거)
                                                  ↓
              all_venues_seoul_only.json 에 approved 항목 자동 통합
                                                  ↓
                          사이트 마커로 등장
```

## STEP 1 — GitHub에 v4 파일 두 개 업로드

ZIP 풀어서 안의 `admin/` 폴더와 `merger/` 폴더를 GitHub 저장소에 통째로 드래그.
- `merger/merge.py` → **Replace** (기존 v3 덮어쓰기)
- `admin/admin_review.html` → 새 파일로 추가

커밋 메시지: `v4 — 검수 화면 + merger 통합`

## STEP 2 — GitHub Personal Access Token 발급 (5분)

이 토큰이 있어야 검수 화면이 본인 대신 GitHub에 commit 합니다.

1. <https://github.com/settings/personal-access-tokens/new> 접속
2. **Token name**: `artmap-review`
3. **Expiration**: 90 days (만료되면 다시 발급)
4. **Repository access**: ⚪ Only select repositories → **artmap-sema-crawler** 선택
5. **Permissions** → **Repository permissions** 펼치기:
   - **Contents** → **Read and write**
6. 맨 아래 **Generate token** 클릭
7. 표시된 토큰 `github_pat_...` 또는 `ghp_...` 형태를 **복사**해서 메모장에 임시 저장
   - ★ **이 화면을 떠나면 다시 못 봄.** 한 번만 표시됨.

## STEP 3 — 검수 화면 열기

선택지 A·B 중 편한 거.

### A. 가장 빠른 방법 — GitHub에서 raw 보기 (한 번만)

GitHub의 [admin/admin_review.html](https://github.com/sookil05114-create/artmap-sema-crawler/blob/main/admin/admin_review.html) 파일 페이지 → 우측 상단 **Raw** 클릭 → 페이지 주소 복사.

그 주소를 브라우저 주소창에 *"raw.githack.com"* 등 raw HTML 렌더링 서비스로 변환해서 열거나, 본인 컴퓨터에 다운로드해서 더블클릭으로 여세요. **GitHub raw URL 자체는 보안상 HTML로 렌더되지 않습니다** (text/plain 으로 옴).

### B. 본인 컴퓨터에 다운로드 (권장)

1. `admin/admin_review.html` 다운로드
2. 다운로드된 파일을 더블클릭 → 본인 브라우저에서 열림
3. 책갈피에 저장해두면 다음부터 한 클릭

### C. GitHub Pages 호스팅 (한 번 셋업, 가장 매끄러움)

저장소 Settings → Pages → Source: **Deploy from a branch** → Branch: `main` → Folder: `/admin` → Save.

5분 후 `https://sookil05114-create.github.io/artmap-sema-crawler/admin_review.html` 형태로 영구 URL 생김. 책갈피에 박아두면 됨.

## STEP 4 — 첫 사용

1. 검수 페이지 우측 상단 **PAT 설정** 클릭
2. 위 STEP 2에서 복사한 토큰 붙여넣기 → **저장**
3. 화면에 pending 카드들이 나타남 (지금은 PS CENTER 1건, alternativespaceloop 1건)
4. 각 카드의 입력칸을 보고 잘못된 값 수정 가능
5. **승인** 클릭 → 자동으로 GitHub에 commit & push
6. 페이지 새로고침 시 PAT는 그대로 (localStorage 저장)

PAT는 본인 브라우저의 localStorage에만 들어가고, GitHub에는 절대 업로드되지 않습니다. 같은 브라우저에서는 다음 방문 시 자동 인식.

## STEP 5 — merger 실행해 사이트 데이터에 반영

검수에서 [승인]만 하면 큐에서 `status=approved`로 바뀔 뿐, 아직 사이트는 그걸 보지 못해요. **merger가 한 번 돌아야** `all_venues_seoul_only.json`에 합쳐집니다.

세 가지 방법:

1. **자동** — 매일 새벽 5시 자동 워크플로우가 돌 때 함께 처리됨 (그냥 기다림)
2. **수동** — GitHub Actions → `SeMA + MMCA 전시·교육 자동 수집 (매일)` → `Run workflow`로 즉시 실행
3. **별도 워크플로우 추가** — 검수 직후 바로 반영되도록 PUSH 트리거 워크플로우 추가 가능 (필요하면 다음 작업으로)

## 그 다음 단계 — 사이트 측 제보 폼 연결

이건 사이트 Claude에 위임합니다. 본인 사이트의 제보하기 폼이 우리 시스템으로 제보를 보내도록 작업 요청:

```
내 사이트 artmap.ai.kr 의 '제보하기' 폼을 다음 방식으로 바꿔줘:

1. 폼은 텍스트 입력 한 줄만 (URL 한 줄 입력 안내)
2. 제출 버튼 누르면 fetch로 GitHub Actions API를 호출해
   "TEST — 제보 URL 1건 처리" 워크플로우를 트리거.
   (POST https://api.github.com/repos/sookil05114-create/artmap-sema-crawler/actions/workflows/test_submission.yml/dispatches
    body: {"ref":"main","inputs":{"url":"입력한URL"}})
3. GitHub API 호출에 필요한 토큰은 환경변수로 분리.
4. 제출 후 사용자에게 "제보 접수됨. 관리자 검수 후 사이트에 반영됩니다." 안내.

게시판 게시글 저장은 하지 마. 데이터는 GitHub의 우리 자동화
시스템(submissions/data/pending_queue.json)에 들어감.
```

이 메시지를 사이트 Claude에 던지면 됩니다. 단, 위 GitHub API 호출용 토큰은 우리가 만든 PAT를 사용하면 안 됨(권한 다름) — **workflow 권한이 있는 별도 PAT**가 필요하고, 그게 사이트 코드에 노출되면 안 되니까 **서버사이드(Vercel 환경변수 등)에서 처리**해야 합니다. 사이트 Claude가 이 부분도 알아서 처리할 거예요.

---

축하합니다. 여기까지 끝나면 **공식 미술관(자동) + 갤러리 제보(URL 한 줄)** 의 큐레이션 흐름이 완성됩니다.
