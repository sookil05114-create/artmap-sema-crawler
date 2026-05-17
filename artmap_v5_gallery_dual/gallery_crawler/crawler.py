"""
을지로 갤러리 자동 수집기 (v2 — 인스타 + 홈페이지 듀얼 fetch)
=============================================================

venues.json의 갤러리 26곳에 대해 다음 순서로 작동:

  1) `instagram_url` 과 `official_url` 둘 다 있으면 → 양쪽 fetch → Claude 통합 추출
  2) 한쪽만 있으면 → 그쪽만 fetch → Claude 단일 추출
  3) 둘 다 비어있으면 → 스킵 (warn 출력)

각 갤러리에 대해 그 시점에 가장 진행중이거나 임박한 전시 1건을 뽑아
`submissions/data/pending_queue.json` 에 자동 적재.

검수 화면(admin_review.html)에서 본인이 [승인]을 누르면 status=approved 로 변경되어
merger가 통합 데이터에 합쳐 사이트에 노출.

사용:
    python gallery_crawler/crawler.py
    python gallery_crawler/crawler.py --only euljiro_doosanartcenter_gallery
    python gallery_crawler/crawler.py --limit 3
    python gallery_crawler/crawler.py --homepage-only  # 인스타 무시 (홈페이지만)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# 같은 패키지의 submissions.processor 임포트
HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from submissions.processor import (  # type: ignore
    fetch_page,
    fetch_combined,
    call_claude,
    call_claude_multi,
    load_queue,
    save_queue,
    upsert,
)

SLEEP = 4.0


def process_venue(v: dict, homepage_only: bool = False, instagram_only: bool = False) -> tuple[str | None, dict | None]:
    """venue 한 곳을 처리해 (상태, item or None) 반환.

    상태: "added" / "skipped_no_url" / "skipped_no_exhibition" / "error"
    """
    insta = "" if homepage_only else (v.get("instagram_url") or "").strip()
    homepage = "" if instagram_only else (v.get("official_url") or "").strip()

    if not insta and not homepage:
        print(f"  [skip] {v['venue_name']}: URL 없음 (instagram·official 둘 다 빔)", file=sys.stderr)
        return "skipped_no_url", None

    sources_label = []
    if insta: sources_label.append("instagram")
    if homepage: sources_label.append("homepage")
    print(f"[갤러리] {v['venue_name']} — {'+'.join(sources_label)}", file=sys.stderr)

    # fetch
    urls, metas = fetch_combined(insta, homepage)
    if not metas:
        print(f"  → 양쪽 fetch 모두 실패", file=sys.stderr)
        return "error", None

    # 추출
    if len(metas) == 1:
        extracted = call_claude(metas[0], urls[0])
        source_url_for_item = urls[0]
        og_for_item = metas[0]["og"]
    else:
        extracted = call_claude_multi(metas, urls, venue_name=v.get("venue_name", ""))
        # 대표 URL: 홈페이지 우선
        source_url_for_item = homepage or urls[0]
        og_for_item = metas[1]["og"] if metas[1]["og"] else metas[0]["og"]

    if not extracted.get("is_exhibition"):
        print(f"  → 전시 정보 없음 (스킵)", file=sys.stderr)
        return "skipped_no_exhibition", None

    # id: 같은 venue + 같은 title이면 한 번만
    seed = f"gallery|{v['venue_key']}|{extracted.get('title','')}"
    sid = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]

    item = {
        "id": sid,
        "source": "gallery_crawler",
        "submitted_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "submitted_by": "auto",
        "submitter_note": f"자동 수집 ({'+'.join(sources_label)})",
        "source_url": source_url_for_item,
        "source_urls": urls,            # ← 인스타 + 홈페이지 둘 다 보관 (검수 시 참고)
        "og_title": og_for_item.get("og:title", "") or og_for_item.get("twitter:title", ""),
        "og_image": og_for_item.get("og:image", ""),
        "extracted": extracted,
        "status": "pending",
        "venue_key": v["venue_key"],
        "venue_name": v["venue_name"],
        "title": extracted.get("title", ""),
        "artists": extracted.get("artists", ""),
        "start_date": extracted.get("start_date") or "",
        "end_date": extracted.get("end_date") or "",
        "thumbnail": extracted.get("thumbnail") or og_for_item.get("og:image", ""),
        "lat": v.get("lat"),
        "lng": v.get("lng"),
        "region": v.get("region", "seoul"),
        "category": v.get("category", ""),
    }
    return "added", item


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--venues", default=str(HERE / "venues.json"))
    ap.add_argument("--only", help="특정 venue_key 하나만 처리")
    ap.add_argument("--limit", type=int, default=0, help="앞 N개만 (0=전체)")
    ap.add_argument("--homepage-only", action="store_true", help="인스타 무시, 홈페이지만")
    ap.add_argument("--instagram-only", action="store_true", help="홈페이지 무시, 인스타만")
    args = ap.parse_args()

    venues = json.loads(Path(args.venues).read_text(encoding="utf-8"))["venues"]
    if args.only:
        venues = [v for v in venues if v["venue_key"] == args.only]
    if args.limit:
        venues = venues[:args.limit]

    queue = load_queue()
    counters = {"added_new": 0, "added_updated": 0, "skipped_no_url": 0,
                "skipped_no_exhibition": 0, "error": 0}

    for v in venues:
        try:
            status, item = process_venue(
                v,
                homepage_only=args.homepage_only,
                instagram_only=args.instagram_only,
            )
            if status == "added" and item:
                is_new = not any(it["id"] == item["id"] for it in queue["items"])
                upsert(queue, item)
                if is_new:
                    counters["added_new"] += 1
                else:
                    counters["added_updated"] += 1
            else:
                counters[status] = counters.get(status, 0) + 1
        except Exception as e:
            print(f"  ★ 예외: {e}", file=sys.stderr)
            counters["error"] += 1
        time.sleep(SLEEP)

    save_queue(queue)
    total = sum(counters.values())
    print(f"\n[Gallery v2] 처리 {total}곳 — "
          f"신규 {counters['added_new']}건, 갱신 {counters['added_updated']}건, "
          f"전시없음 {counters['skipped_no_exhibition']}, "
          f"URL없음 {counters['skipped_no_url']}, "
          f"오류 {counters['error']} — 큐 총 {len(queue['items'])}건",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
