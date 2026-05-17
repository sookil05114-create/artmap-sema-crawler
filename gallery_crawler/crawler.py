"""
갤러리 자동 수집기 (v3 — 듀얼 fetch + 자동 좌표 추정)
======================================================

venues.json의 갤러리 각 곳에 대해:

  1) `instagram_url` 과 `official_url` 둘 다 있으면 → 양쪽 fetch → Claude 통합 추출
  2) 한쪽만 있으면 → 그쪽만 fetch → Claude 단일 추출
  3) 둘 다 비어있으면 → 스킵

v6 신규: lat/lng 가 비어있으면 Naver 지역 검색 API로 자동 추정.
  - 결과는 `gallery_crawler/coords_cache.json` 에 저장 (다음 실행 시 즉시 사용)
  - venues.json은 손대지 않음 (사용자가 손으로 편집하는 파일)
  - 추정된 좌표는 pending 큐 아이템의 lat/lng/address 필드에 채워서 저장
  - 사이트 지도 마커는 큐 아이템 → merger → all_venues_seoul_only.json 으로 흘러감

각 갤러리에 대해 그 시점에 가장 진행중이거나 임박한 전시 1건을 뽑아
`submissions/data/pending_queue.json` 에 자동 적재.

사용:
    python gallery_crawler/crawler.py
    python gallery_crawler/crawler.py --only euljiro_doosanartcenter_gallery
    python gallery_crawler/crawler.py --limit 3
    python gallery_crawler/crawler.py --geocode-only   # fetch 없이 좌표 캐시만 갱신
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from submissions.processor import (  # type: ignore
    fetch_page,
    fetch_combined,
    call_claude,
    call_claude_multi,
    geocode_naver,
    load_queue,
    save_queue,
    upsert,
)

SLEEP = 4.0
GEO_SLEEP = 0.3       # Naver 검색 API rate limit 여유 (초당 ~10건 제한)
COORDS_CACHE_PATH = HERE / "coords_cache.json"


def load_coords_cache() -> dict:
    if not COORDS_CACHE_PATH.exists():
        return {"generated_at": "", "venues": {}}
    try:
        return json.loads(COORDS_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"generated_at": "", "venues": {}}


def save_coords_cache(cache: dict) -> None:
    cache["generated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    COORDS_CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def resolve_coords(v: dict, cache: dict, force: bool = False) -> dict:
    """venue 한 곳의 좌표·주소 결정. 우선순위:
       1) venues.json 의 lat/lng/address (사람이 직접 채운 값 최우선)
       2) coords_cache 에 저장된 값
       3) Naver 지역 검색으로 즉석 추정 → cache 에 저장
    실패하면 {"lat": None, "lng": None, "address": ""} 반환.
    """
    vk = v["venue_key"]

    # 1) venues.json 값 우선
    if v.get("lat") is not None and v.get("lng") is not None:
        return {
            "lat": v.get("lat"),
            "lng": v.get("lng"),
            "address": v.get("address", ""),
            "source": "venues.json",
        }

    # 2) cache
    cached = cache["venues"].get(vk)
    if cached and not force:
        return {
            "lat": cached.get("lat"),
            "lng": cached.get("lng"),
            "address": cached.get("address", ""),
            "source": "cache",
        }

    # 3) Naver 지역 검색 — venue_name + 지역 hint
    queries = []
    name = v.get("venue_name", "").strip()
    subregion = v.get("subregion", "").strip()
    region = v.get("region", "").strip()
    if name:
        # 가장 정확한 쿼리부터 폴백
        if subregion and subregion != "euljiro":
            queries.append(f"{name} {subregion}")
        queries.append(f"{name} 서울")
        queries.append(name)
    queries.append(v.get("address", ""))
    seen = set()
    for q in queries:
        q = (q or "").strip()
        if not q or q in seen:
            continue
        seen.add(q)
        result = geocode_naver(q)
        time.sleep(GEO_SLEEP)
        if result:
            entry = {
                "lat": result["lat"],
                "lng": result["lng"],
                "address": result["address"],
                "name_matched": result.get("name_matched", ""),
                "query": q,
                "cached_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            }
            cache["venues"][vk] = entry
            print(f"  [geo] {v['venue_name']} → ({result['lat']}, {result['lng']}) "
                  f"[{result.get('name_matched', '')}]", file=sys.stderr)
            return {
                "lat": entry["lat"],
                "lng": entry["lng"],
                "address": entry["address"],
                "source": "naver_geocode",
            }

    print(f"  [geo] {v['venue_name']} → 좌표 추정 실패", file=sys.stderr)
    return {"lat": None, "lng": None, "address": v.get("address", ""), "source": "none"}


def process_venue(
    v: dict,
    cache: dict,
    homepage_only: bool = False,
    instagram_only: bool = False,
    skip_fetch: bool = False,
) -> tuple[str | None, dict | None]:
    """venue 한 곳을 처리해 (상태, item or None) 반환.

    상태: "added" / "skipped_no_url" / "skipped_no_exhibition" / "error" / "geocode_only"
    """
    # 좌표 먼저 확보 (실패해도 fetch 진행)
    coords = resolve_coords(v, cache)

    if skip_fetch:
        return "geocode_only", None

    insta = "" if homepage_only else (v.get("instagram_url") or "").strip()
    homepage = "" if instagram_only else (v.get("official_url") or "").strip()

    if not insta and not homepage:
        print(f"  [skip] {v['venue_name']}: URL 없음", file=sys.stderr)
        return "skipped_no_url", None

    sources_label = []
    if insta: sources_label.append("instagram")
    if homepage: sources_label.append("homepage")
    print(f"[갤러리] {v['venue_name']} — {'+'.join(sources_label)}", file=sys.stderr)

    urls, metas = fetch_combined(insta, homepage)
    if not metas:
        print(f"  → 양쪽 fetch 모두 실패", file=sys.stderr)
        return "error", None

    if len(metas) == 1:
        extracted = call_claude(metas[0], urls[0])
        source_url_for_item = urls[0]
        og_for_item = metas[0]["og"]
    else:
        extracted = call_claude_multi(metas, urls, venue_name=v.get("venue_name", ""))
        source_url_for_item = homepage or urls[0]
        og_for_item = metas[1]["og"] if metas[1]["og"] else metas[0]["og"]

    if not extracted.get("is_exhibition"):
        print(f"  → 전시 정보 없음 (스킵)", file=sys.stderr)
        return "skipped_no_exhibition", None

    seed = f"gallery|{v['venue_key']}|{extracted.get('title','')}"
    sid = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]

    item = {
        "id": sid,
        "source": "gallery_crawler",
        "submitted_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "submitted_by": "auto",
        "submitter_note": f"자동 수집 ({'+'.join(sources_label)}; 좌표={coords.get('source','none')})",
        "source_url": source_url_for_item,
        "source_urls": urls,
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
        # 좌표·주소는 venues.json > cache > naver geocode 순으로 결정된 값
        "lat": coords["lat"],
        "lng": coords["lng"],
        "address": coords["address"] or v.get("address", ""),
        "region": v.get("region", "seoul"),
        "category": v.get("category", ""),
    }
    return "added", item


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--venues", default=str(HERE / "venues.json"))
    ap.add_argument("--only", help="특정 venue_key 하나만 처리")
    ap.add_argument("--limit", type=int, default=0, help="앞 N개만 (0=전체)")
    ap.add_argument("--homepage-only", action="store_true")
    ap.add_argument("--instagram-only", action="store_true")
    ap.add_argument("--geocode-only", action="store_true",
                    help="fetch·Claude 호출 없이 좌표 캐시만 갱신")
    args = ap.parse_args()

    venues = json.loads(Path(args.venues).read_text(encoding="utf-8"))["venues"]
    if args.only:
        venues = [v for v in venues if v["venue_key"] == args.only]
    if args.limit:
        venues = venues[:args.limit]

    queue = load_queue()
    cache = load_coords_cache()
    counters = {
        "added_new": 0, "added_updated": 0, "skipped_no_url": 0,
        "skipped_no_exhibition": 0, "error": 0, "geocode_only": 0,
    }

    for v in venues:
        try:
            status, item = process_venue(
                v, cache,
                homepage_only=args.homepage_only,
                instagram_only=args.instagram_only,
                skip_fetch=args.geocode_only,
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
        if not args.geocode_only:
            time.sleep(SLEEP)

    save_coords_cache(cache)
    save_queue(queue)
    total = sum(counters.values())
    geo_total = len(cache.get("venues", {}))
    print(f"\n[Gallery v3] 처리 {total}곳 — "
          f"신규 {counters['added_new']}, 갱신 {counters['added_updated']}, "
          f"전시없음 {counters['skipped_no_exhibition']}, URL없음 {counters['skipped_no_url']}, "
          f"오류 {counters['error']}, geo-only {counters['geocode_only']} — "
          f"큐 총 {len(queue['items'])}건, 좌표 캐시 {geo_total}곳",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
