"""
제보 URL 처리기 (v2 — 멀티 URL 지원)
====================================

URL 한 줄을 받아 →
  1) OG 메타 + 본문 일부 추출 (인스타는 Facebook bot UA, 일반 사이트는 Chrome UA)
  2) Claude Haiku API로 전시 정보 구조화
  3) submissions/data/pending_queue.json 에 추가 (status=pending)

v2 변경점:
  - 일반 사이트(갤러리 홈페이지)에서도 OG 메타 + 본문 텍스트(최대 4000자) 추출
  - 갤러리 크롤러용 헬퍼 `fetch_combined()` 와 `call_claude_multi()` 추가
    → 한 갤러리의 인스타 + 홈페이지를 둘 다 fetch해서 Claude 한 번 호출로 통합 추출
  - 기존 단일-URL 흐름(call_claude / fetch_page)은 그대로 — 사용자 제보 등에서 사용

검수 단계(admin_review.html)에서 본인이 [승인] 누르면 status=approved 로 변경되어
merger가 통합 데이터에 합쳐 사이트에 노출.

사용:
    # CLI — 사람이 직접 URL 던지기
    python submissions/processor.py "https://www.instagram.com/p/XXXX/"

    # 또는 새로 들어온 제보 파일 일괄 처리
    python submissions/processor.py --from-file urls.txt
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urlparse

import requests

HERE = Path(__file__).parent
DATA = HERE / "data"
DATA.mkdir(parents=True, exist_ok=True)

# Facebook bot UA → 인스타도 통과시킴 (자기네 봇이라 OG 메타 정상 반환)
FB_BOT_UA = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
CHROME_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
             "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")

TIMEOUT = 30
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
CLAUDE_API = "https://api.anthropic.com/v1/messages"


# ========== 1) URL 종류 판별 + OG 메타 fetch ==========

def is_instagram(url: str) -> bool:
    return "instagram.com" in urlparse(url).netloc


def fetch_page(url: str) -> tuple[str, dict]:
    """페이지를 받아 HTML과 OG 메타 dict 반환.

    반환 dict 구조:
        {
          "og":       {og:title, og:description, og:image, og:type, og:url, twitter:title, twitter:description},
          "body":     "본문 텍스트 (인스타 외 4000자 컷)",
          "final_url": 리다이렉트 후 최종 URL,
          "source":   "instagram" | "homepage",
        }
    """
    ua = FB_BOT_UA if is_instagram(url) else CHROME_UA
    headers = {"User-Agent": ua, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"}
    r = requests.get(url, headers=headers, timeout=TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    html = r.text

    og = {}
    for prop in ["og:title", "og:description", "og:image", "og:type", "og:url",
                 "twitter:title", "twitter:description"]:
        m = re.search(rf'<meta\s+property="{prop}"\s+content="([^"]+)"', html)
        if not m:
            m = re.search(rf'<meta\s+name="{prop}"\s+content="([^"]+)"', html)
        if m:
            og[prop] = unescape_entities(m.group(1))

    # 본문 텍스트 일부 (인스타 외 일반 사이트에서 도움)
    body_text = ""
    if not is_instagram(url):
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
                tag.decompose()
            body_text = soup.get_text(" ", strip=True)
            # 공백 압축
            body_text = re.sub(r"\s+", " ", body_text)[:4000]
        except Exception:
            body_text = re.sub(r"<[^>]+>", " ", html)
            body_text = re.sub(r"\s+", " ", body_text)[:4000]
    return html, {
        "og": og,
        "body": body_text,
        "final_url": r.url,
        "source": "instagram" if is_instagram(url) else "homepage",
    }


def unescape_entities(s: str) -> str:
    """&#x...; 같은 HTML 엔티티를 풀어줌."""
    import html as html_module
    return html_module.unescape(s)


# ========== 2) Claude API 호출 ==========

def call_claude(meta: dict, source_url: str) -> dict:
    """단일 URL 메타에서 전시 정보 추출 (제보 1건용)."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다")

    og = meta["og"]
    prompt = f"""다음은 갤러리 또는 미술 공간의 인스타그램 게시물 또는 웹페이지에서 추출한 정보입니다.
이 페이지에 전시 정보가 있다면 아래 JSON 스키마에 맞춰 정확히 한 건만 추출해 주세요.

[원본 URL]
{source_url}

[OG 메타데이터]
title: {og.get('og:title') or og.get('twitter:title') or ''}
description: {og.get('og:description') or og.get('twitter:description') or ''}
image: {og.get('og:image') or ''}

[본문 일부 (인스타가 아닌 경우)]
{meta.get('body', '')[:3000]}

[추출 규칙]
- 전시 정보가 명확히 없으면 "is_exhibition": false 로만 반환.
- 일정이 명확하지 않으면 해당 필드는 null.
- 캡션의 줄임표·이모지·해시태그는 무시하고 사실 정보만 뽑기.
- 작가가 여러 명이면 콤마로 구분.

[응답 형식 — JSON만, 다른 텍스트 금지]
{{
  "is_exhibition": true 또는 false,
  "title": "전시명",
  "artists": "작가명",
  "venue_name": "공간명 (추정 가능하면)",
  "start_date": "YYYY-MM-DD 또는 null",
  "end_date": "YYYY-MM-DD 또는 null",
  "thumbnail": "이미지 URL",
  "description_summary": "한두 문장 요약",
  "confidence": 0.0 ~ 1.0
}}"""

    return _claude_request(prompt)


def call_claude_multi(metas: list[dict], source_urls: list[str], venue_name: str = "") -> dict:
    """여러 URL(인스타 + 홈페이지)의 메타를 한 번에 전달해 통합 추출.

    같은 갤러리의 인스타와 공식 홈페이지를 동시에 보여줘서
    Claude가 양쪽을 교차 확인해 정확도를 높이는 용도.
    """
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다")

    # 소스별 블록 구성
    blocks = []
    for url, meta in zip(source_urls, metas):
        if not meta:
            continue
        og = meta.get("og", {})
        src = meta.get("source", "unknown")
        blocks.append(
            f"--- [{src}] {url} ---\n"
            f"title: {og.get('og:title') or og.get('twitter:title') or ''}\n"
            f"description: {og.get('og:description') or og.get('twitter:description') or ''}\n"
            f"image: {og.get('og:image') or ''}\n"
            f"body_excerpt:\n{meta.get('body', '')[:2500]}"
        )
    combined = "\n\n".join(blocks)

    prompt = f"""다음은 한 갤러리/미술공간의 **두 가지 URL** (인스타그램 메인 페이지 + 공식 홈페이지)에서 추출한 데이터입니다.
두 데이터를 교차 확인해서 **현재 진행중이거나 곧 시작하는 전시 한 건**을 정확히 추출하세요.

[갤러리 이름]
{venue_name or '(미지정)'}

[수집된 데이터]
{combined}

[추출 규칙]
- 두 소스의 정보가 충돌하면 **더 구체적이고 최신인 정보**를 우선 (보통 홈페이지가 정식 표기, 인스타는 캡션이라 약식).
- 한 페이지에는 여러 전시가 언급될 수 있지만, **가장 현재 진행중이거나 가장 곧 시작하는 단 한 건**만 뽑기.
- 일정이 명확하지 않으면 해당 필드는 null.
- 캡션의 이모지·해시태그·줄임말은 사실 정보가 아니면 무시.
- 작가가 여러 명이면 콤마로 구분.
- 전시 정보가 양쪽 어디에도 명확히 없으면 "is_exhibition": false 로만 반환.
- "thumbnail" 은 OG image 중 더 화질이 좋아 보이는 것을 선택.

[응답 형식 — JSON만, 다른 텍스트 금지]
{{
  "is_exhibition": true 또는 false,
  "title": "전시명",
  "artists": "작가명",
  "venue_name": "공간명",
  "start_date": "YYYY-MM-DD 또는 null",
  "end_date": "YYYY-MM-DD 또는 null",
  "thumbnail": "이미지 URL",
  "description_summary": "한두 문장 요약",
  "confidence": 0.0 ~ 1.0,
  "sources_used": ["instagram" 또는 "homepage" 중 어디서 정보가 왔는지]
}}"""

    return _claude_request(prompt)


def _claude_request(prompt: str) -> dict:
    """공통 Claude API 호출 + JSON 추출."""
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 700,
        "messages": [{"role": "user", "content": prompt}],
    }
    r = requests.post(CLAUDE_API, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    text = r.json()["content"][0]["text"].strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError(f"Claude 응답에서 JSON을 찾지 못함: {text[:200]}")
    return json.loads(m.group(0))


def fetch_combined(instagram_url: str = "", official_url: str = "") -> tuple[list[str], list[dict]]:
    """한 갤러리의 인스타 + 홈페이지를 둘 다 fetch.

    빈 URL은 자동 스킵. 둘 중 하나만 있어도 동작. 둘 다 비어 있으면 빈 리스트.
    """
    urls: list[str] = []
    metas: list[dict] = []
    for url in [instagram_url, official_url]:
        url = (url or "").strip()
        if not url:
            continue
        try:
            _, meta = fetch_page(url)
            urls.append(url)
            metas.append(meta)
        except Exception as e:
            print(f"  [warn] {url} fetch 실패: {e}", file=sys.stderr)
    return urls, metas


# ========== 3) pending 큐 적재 ==========

def load_queue() -> dict:
    p = DATA / "pending_queue.json"
    if not p.exists():
        return {"generated_at": "", "items": []}
    return json.loads(p.read_text(encoding="utf-8"))


def save_queue(q: dict) -> None:
    q["generated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    (DATA / "pending_queue.json").write_text(
        json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def process_url(url: str, submitted_by: str = "auto", note: str = "") -> dict:
    """URL 1건을 처리해 pending 큐 적재용 item 반환."""
    print(f"[제보] {url}", file=sys.stderr)
    _, meta = fetch_page(url)
    extracted = call_claude(meta, url)

    sid = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    item = {
        "id": sid,
        "source": "submission",
        "submitted_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "submitted_by": submitted_by,
        "submitter_note": note,
        "source_url": url,
        "og_title": meta["og"].get("og:title") or meta["og"].get("twitter:title", ""),
        "og_image": meta["og"].get("og:image", ""),
        "extracted": extracted,
        "status": "pending",
        "venue_key": "",
        "venue_name": extracted.get("venue_name", ""),
        "title": extracted.get("title", ""),
        "artists": extracted.get("artists", ""),
        "start_date": extracted.get("start_date", ""),
        "end_date": extracted.get("end_date", ""),
        "thumbnail": extracted.get("thumbnail") or meta["og"].get("og:image", ""),
    }
    return item


def upsert(queue: dict, item: dict) -> None:
    for i, existing in enumerate(queue["items"]):
        if existing["id"] == item["id"]:
            if existing["status"] in ("approved", "rejected"):
                return
            queue["items"][i] = item
            return
    queue["items"].insert(0, item)


# ========== Main ==========

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?", help="처리할 URL (제보 1건)")
    ap.add_argument("--from-file", help="URL이 줄마다 적힌 텍스트 파일")
    ap.add_argument("--submitted-by", default="cli")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    urls: list[str] = []
    if args.url:
        urls.append(args.url)
    if args.from_file:
        urls.extend(
            l.strip() for l in Path(args.from_file).read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.strip().startswith("#")
        )
    if not urls:
        ap.error("URL을 지정하세요 (인자 또는 --from-file)")

    queue = load_queue()
    ok, fail = 0, 0
    for u in urls:
        try:
            item = process_url(u, submitted_by=args.submitted_by, note=args.note)
            upsert(queue, item)
            ok += 1
            time.sleep(1.5)
        except Exception as e:
            print(f"  실패: {e}", file=sys.stderr)
            fail += 1
    save_queue(queue)
    print(f"\n[Submissions] 성공 {ok}건, 실패 {fail}건, 큐 총 {len(queue['items'])}건", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
