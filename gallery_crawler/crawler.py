"""
을지로 갤러리 자동 수집기
==========================

venues.json의 26곳 인스타그램 메인 페이지를 매일 가져와
OG 메타와 최근 캡션 일부를 Claude API에 전달, 진행중 전시 정보를 추출해
submissions/data/pending_queue.json 에 자동 적재합니다.

submissions/processor.py 와 같은 backend 로직을 공유합니다.

사용:
    python gallery_crawler/crawler.py
    python gallery_crawler/crawler.py --only euljiro_doosanartcenter_gallery
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# 같은 패키지의 submissions.processor 임포트 (없으면 직접 호출)
HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from submissions.processor import (  # type: ignore
    fetch_page, call_claude, load_queue, save_queue, upsert,
)

SLEEP = 4.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--venues", default=str(HERE / "venues.json"))
    ap.add_argument("--only", help="특정 venue_key 하나만 처리")
    ap.add_argument("--limit", type=int, default=0, help="앞 N개만 (0=전체)")
    args = ap.parse_args()

    venues = json.loads(Path(args.venues).read_text(encoding="utf-8"))["venues"]
    if args.only:
        venues = [v for v in venues if v["venue_key"] == args.only]
    if args.limit:
        venues = venues[:args.limit]

    queue = load_queue()
    ok, fail, new_pending = 0, 0, 0

    for v in venues:
        url = v.get("instagram_url") or v.get("official_url")
        if not url:
            print(f"  [skip] {v['venue_name']}: URL 없음", file=sys.stderr)
            continue
        print(f"[갤러리] {v['venue_name']} — {url}", file=sys.stderr)
        try:
            _, meta = fetch_page(url)
            extracted = call_claude(meta, url)

            # 전시 정보가 아니면 건너뜀
            if not extracted.get("is_exhibition"):
                print(f"  → 전시 정보 없음 (스킵)", file=sys.stderr)
                ok += 1
                time.sleep(SLEEP)
                continue

            # 같은 URL은 한 번만 큐에 들어가도록 id 결정 (날짜 무관)
            seed = f"gallery|{v['venue_key']}|{extracted.get('title','')}"
            sid = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
            item = {
                "id": sid,
                "source": "gallery_crawler",
                "submitted_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "submitted_by": "auto",
                "submitter_note": "매일 자동 수집",
                "source_url": url,
                "og_title": meta["og"].get("og:title", ""),
                "og_image": meta["og"].get("og:image", ""),
                "extracted": extracted,
                "status": "pending",
                "venue_key": v["venue_key"],
                "venue_name": v["venue_name"],
                "title": extracted.get("title", ""),
                "artists": extracted.get("artists", ""),
                "start_date": extracted.get("start_date") or "",
                "end_date": extracted.get("end_date") or "",
                "thumbnail": extracted.get("thumbnail") or meta["og"].get("og:image", ""),
                "lat": v.get("lat"),
                "lng": v.get("lng"),
                "region": v.get("region", "seoul"),
                "category": v.get("category", ""),
            }
            # 새 항목인지 카운트
            is_new = not any(it["id"] == sid for it in queue["items"])
            upsert(queue, item)
            if is_new:
                new_pending += 1
            ok += 1
        except Exception as e:
            print(f"  실패: {e}", file=sys.stderr)
            fail += 1
        time.sleep(SLEEP)

    save_queue(queue)
    print(f"\n[Gallery] 처리 {ok}곳, 실패 {fail}곳, 신규 pending {new_pending}건, 큐 총 {len(queue['items'])}건",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
