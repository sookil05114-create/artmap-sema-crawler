"""
SeMA + MMCA + 승인된 제보 통합 merger (v4 — 자동 좌표 폴백)

입력:
    ../sema_crawler/data/exhibitions_latest.json
    ../mmca_crawler/data/exhibitions_latest.json
    ../mmca_crawler/data/programs_latest.json
    ../submissions/data/pending_queue.json   ← approved 제보·갤러리 자동 수집
    ../gallery_crawler/venues.json           ← 갤러리 메타
    ../gallery_crawler/coords_cache.json     ← (선택) 자동 좌표 캐시 — venues.json 좌표 누락 시 폴백
    ../sema_crawler/venues.json, ../mmca_crawler/venues.json (메타)

출력:
    data/all_exhibitions_latest.json
    data/all_venues_latest.json
    data/all_venues_seoul_only.json    ★ 사이트 메인
    data/all_exhibitions_seoul_only.json
    data/all_programs_latest.json

v6 변경점:
  - submission_to_exhibition: pending item 자체의 lat/lng/address 우선, venues.json은 fallback
  - build_venues_grouped: venues.json 좌표 누락 시 그 분관에 속한 첫 전시의 좌표를 사용
  - load_coords_cache: 좌표 캐시 파일도 로드해서, 전시 평면화 직전에 모든 item의 lat/lng 보강
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, date
from pathlib import Path


HERE = Path(__file__).parent
ROOT = HERE.parent


def load_json(p: Path):
    if not p.exists():
        print(f"[skip] {p} 없음", file=sys.stderr)
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def parse_iso(s: str):
    try: return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception: return None


def compute_status(start: str, end: str, today: date) -> str:
    s, e = parse_iso(start), parse_iso(end)
    if not s or not e: return "unknown"
    if today < s: return "upcoming"
    if today > e: return "ended"
    return "active"


def resolve_coords_for_venue(vk: str, venue_meta: dict | None, coords_cache: dict) -> tuple[float | None, float | None, str]:
    """venues.json > coords_cache 순으로 좌표·주소 결정."""
    if venue_meta:
        lat = venue_meta.get("lat")
        lng = venue_meta.get("lng")
        addr = venue_meta.get("address", "")
        if lat is not None and lng is not None:
            return lat, lng, addr
    cached = coords_cache.get(vk)
    if cached:
        return cached.get("lat"), cached.get("lng"), cached.get("address", "") or (venue_meta or {}).get("address", "")
    return None, None, (venue_meta or {}).get("address", "")


def submission_to_exhibition(it: dict, gv_by_key: dict, coords_cache: dict) -> dict | None:
    """pending_queue 의 approved 1건을 통합 전시 스키마로 변환."""
    if it.get("status") != "approved":
        return None
    if it.get("extracted", {}).get("is_exhibition") is False:
        return None
    title = it.get("title") or ""
    if not title:
        return None
    today = date.today()
    start = it.get("start_date") or ""
    end = it.get("end_date") or start

    vk = it.get("venue_key") or ""
    venue = gv_by_key.get(vk, {})
    if not venue and it.get("venue_name"):
        vn = it["venue_name"].replace(" ", "")
        for k, v in gv_by_key.items():
            if v.get("venue_name", "").replace(" ", "") == vn:
                venue = v
                vk = k
                break

    # 좌표·주소 결정 순서:
    #  1) pending item 자체의 lat/lng (crawler가 자동 추정한 값 또는 사용자 수정)
    #  2) venues.json
    #  3) coords_cache (gallery_crawler가 만든 캐시)
    lat = it.get("lat")
    lng = it.get("lng")
    addr = it.get("address", "")
    if lat is None or lng is None:
        vlat, vlng, vaddr = resolve_coords_for_venue(vk, venue, coords_cache)
        if lat is None: lat = vlat
        if lng is None: lng = vlng
        if not addr: addr = vaddr

    return {
        "id": it["id"],
        "source": it.get("source", "submission"),
        "title": title,
        "artists": it.get("artists", ""),
        "venue_raw": it.get("venue_name", ""),
        "venue_key": vk or "unknown_submission",
        "venue_name": venue.get("venue_name") or it.get("venue_name", ""),
        "region": venue.get("region", "seoul"),
        "address": addr,
        "lat": lat,
        "lng": lng,
        "start_date": start,
        "end_date": end,
        "price": "",
        "url": it.get("source_url", ""),
        "thumbnail": it.get("thumbnail", ""),
        "status": compute_status(start, end, today) if start else "active",
        "collected_at": it.get("submitted_at", now_iso()),
    }


def build_venues_grouped(exhibitions: list, all_venues_meta: list, coords_cache: dict) -> list:
    """전시 평면 리스트를 분관별로 그룹화.
    v6: venues.json 좌표가 비어 있으면 분관 첫 전시의 좌표 또는 coords_cache로 폴백.
    """
    by_v: dict[str, list] = {}
    for e in exhibitions:
        if e.get("status") not in ("active", "upcoming"):
            continue
        by_v.setdefault(e.get("venue_key", "unknown"), []).append(e)

    venues_out = []
    seen_keys = set()
    for v in all_venues_meta:
        vk = v["venue_key"]
        seen_keys.add(vk)
        lst = by_v.get(vk, [])
        if not lst:
            continue
        lst_sorted = sorted(lst, key=lambda e: e.get("start_date") or "9999")
        sample = lst_sorted[0]

        # 좌표 폴백 사다리
        lat = v.get("lat")
        lng = v.get("lng")
        addr = v.get("address", "")
        if lat is None or lng is None:
            cached = coords_cache.get(vk, {})
            if lat is None: lat = sample.get("lat") if sample.get("lat") is not None else cached.get("lat")
            if lng is None: lng = sample.get("lng") if sample.get("lng") is not None else cached.get("lng")
            if not addr:
                addr = sample.get("address") or cached.get("address", "")

        venues_out.append({
            "venue_key": vk,
            "venue_name": v.get("venue_name", ""),
            "region": v.get("region", "unknown"),
            "address": addr,
            "lat": lat, "lng": lng,
            "official_url": v.get("official_url", v.get("instagram_url", "")),
            "category": v.get("category", ""),
            "active_count": sum(1 for e in lst if e.get("status") == "active"),
            "upcoming_count": sum(1 for e in lst if e.get("status") == "upcoming"),
            "exhibitions": [
                {"id": e["id"], "title": e["title"], "artists": e.get("artists", ""),
                 "start_date": e.get("start_date", ""), "end_date": e.get("end_date", ""),
                 "status": e.get("status"), "thumbnail": e.get("thumbnail", ""),
                 "url": e.get("url", ""), "price": e.get("price", "")}
                for e in lst_sorted
            ],
        })

    # 메타에 없지만 데이터에 있는 venue (외부 협력 등)
    for vk, lst in by_v.items():
        if vk in seen_keys: continue
        lst_sorted = sorted(lst, key=lambda e: e.get("start_date") or "9999")
        sample = lst[0]
        cached = coords_cache.get(vk, {})
        venues_out.append({
            "venue_key": vk,
            "venue_name": sample.get("venue_name", "(미분류)"),
            "region": sample.get("region", "unknown"),
            "address": sample.get("address") or cached.get("address", ""),
            "lat": sample.get("lat") if sample.get("lat") is not None else cached.get("lat"),
            "lng": sample.get("lng") if sample.get("lng") is not None else cached.get("lng"),
            "official_url": "",
            "category": "기타",
            "active_count": sum(1 for e in lst if e.get("status") == "active"),
            "upcoming_count": sum(1 for e in lst if e.get("status") == "upcoming"),
            "exhibitions": [
                {"id": e["id"], "title": e["title"], "artists": e.get("artists", ""),
                 "start_date": e.get("start_date", ""), "end_date": e.get("end_date", ""),
                 "status": e.get("status"), "thumbnail": e.get("thumbnail", ""),
                 "url": e.get("url", ""), "price": e.get("price", "")}
                for e in lst_sorted
            ],
        })
    return venues_out


def main() -> int:
    sema_exh = load_json(ROOT / "sema_crawler" / "data" / "exhibitions_latest.json")
    mmca_exh = load_json(ROOT / "mmca_crawler" / "data" / "exhibitions_latest.json")
    mmca_prog = load_json(ROOT / "mmca_crawler" / "data" / "programs_latest.json")
    queue = load_json(ROOT / "submissions" / "data" / "pending_queue.json")
    gallery_venues_doc = load_json(ROOT / "gallery_crawler" / "venues.json")
    sema_venues_doc = load_json(ROOT / "sema_crawler" / "venues.json")
    mmca_venues_doc = load_json(ROOT / "mmca_crawler" / "venues.json")
    coords_cache_doc = load_json(ROOT / "gallery_crawler" / "coords_cache.json")

    coords_cache = (coords_cache_doc or {}).get("venues", {})

    outdir = HERE / "data"
    outdir.mkdir(parents=True, exist_ok=True)

    # 1) 통합 전시 평면 — SeMA + MMCA + 승인된 제보
    all_exs: list = []
    sources: list = []
    if sema_exh: all_exs.extend(sema_exh.get("exhibitions", [])); sources.append("sema")
    if mmca_exh: all_exs.extend(mmca_exh.get("exhibitions", [])); sources.append("mmca")

    gv_by_key = {}
    if gallery_venues_doc:
        for v in gallery_venues_doc.get("venues", []):
            gv_by_key[v["venue_key"]] = v

    approved_count = 0
    if queue:
        for it in queue.get("items", []):
            ex = submission_to_exhibition(it, gv_by_key, coords_cache)
            if ex:
                if not any(e.get("id") == ex["id"] for e in all_exs):
                    all_exs.append(ex)
                    approved_count += 1
        if approved_count: sources.append("submissions")

    all_exs.sort(key=lambda e: e.get("start_date") or "9999")

    # 2) 전체 venues 메타
    all_venues_meta: list = []
    for doc in [sema_venues_doc, mmca_venues_doc, gallery_venues_doc]:
        if doc:
            all_venues_meta.extend(doc.get("venues", []))

    # 3) 분관별 그룹화
    venues_grouped = build_venues_grouped(all_exs, all_venues_meta, coords_cache)
    active_venues = [v for v in venues_grouped if v["active_count"] + v["upcoming_count"] > 0]

    # 4) 출력
    payload_exs = {
        "generated_at": now_iso(),
        "sources": sources,
        "count": len(all_exs),
        "exhibitions": all_exs,
    }
    (outdir / "all_exhibitions_latest.json").write_text(
        json.dumps(payload_exs, ensure_ascii=False, indent=2), encoding="utf-8")

    seoul_exs = [e for e in all_exs if e.get("region") == "seoul"]
    (outdir / "all_exhibitions_seoul_only.json").write_text(
        json.dumps({**payload_exs, "count": len(seoul_exs), "filter": "region=seoul",
                    "exhibitions": seoul_exs}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    payload_venues = {
        "generated_at": now_iso(),
        "sources": sources,
        "venue_count": len(active_venues),
        "venues": active_venues,
    }
    (outdir / "all_venues_latest.json").write_text(
        json.dumps(payload_venues, ensure_ascii=False, indent=2), encoding="utf-8")

    seoul_venues = [v for v in active_venues if v.get("region") == "seoul"]
    (outdir / "all_venues_seoul_only.json").write_text(
        json.dumps({**payload_venues, "venue_count": len(seoul_venues),
                    "filter": "region=seoul", "venues": seoul_venues},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")

    # 교육
    all_progs: list = []
    prog_sources: list = []
    if mmca_prog:
        all_progs.extend(mmca_prog.get("programs", []))
        prog_sources.append("mmca")
    all_progs.sort(key=lambda p: p.get("start_date") or "9999")
    (outdir / "all_programs_latest.json").write_text(
        json.dumps({"generated_at": now_iso(), "sources": prog_sources,
                    "count": len(all_progs), "programs": all_progs},
                   ensure_ascii=False, indent=2),
        encoding="utf-8")

    # 좌표 보정 통계
    seoul_marker_with_xy = sum(1 for v in seoul_venues if v.get("lat") and v.get("lng"))
    seoul_marker_no_xy = len(seoul_venues) - seoul_marker_with_xy

    print(f"\n[Merger v4] 통합 완료", file=sys.stderr)
    print(f"  전시 평면 총 {len(all_exs)}건 (서울 {len(seoul_exs)}건)", file=sys.stderr)
    print(f"  분관 마커 {len(active_venues)}곳 (서울 {len(seoul_venues)}곳) — "
          f"좌표있음 {seoul_marker_with_xy} / 좌표없음 {seoul_marker_no_xy}", file=sys.stderr)
    print(f"  승인된 제보 통합: {approved_count}건", file=sys.stderr)
    print(f"  좌표 캐시 적용: {len(coords_cache)}곳", file=sys.stderr)
    print(f"  교육: {len(all_progs)}건", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
