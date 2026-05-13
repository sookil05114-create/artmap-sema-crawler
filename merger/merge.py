"""
SeMA + MMCA + 승인된 제보를 통합하는 merger (v3)

입력:
    ../sema_crawler/data/exhibitions_latest.json
    ../sema_crawler/data/venues_with_exhibitions_latest.json
    ../mmca_crawler/data/exhibitions_latest.json
    ../mmca_crawler/data/venues_with_exhibitions_latest.json
    ../mmca_crawler/data/programs_latest.json
    ../submissions/data/pending_queue.json   ← ★ 새 입력: 승인된 제보·갤러리 자동 수집
    ../gallery_crawler/venues.json           ← ★ 갤러리 분관 메타 (좌표 등)

출력:
    data/all_exhibitions_latest.json
    data/all_venues_latest.json
    data/all_venues_seoul_only.json        ★ 사이트 메인
    data/all_exhibitions_seoul_only.json
    data/all_programs_latest.json
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


def submission_to_exhibition(it: dict, gallery_venues_by_key: dict) -> dict | None:
    """submissions/pending_queue.json 의 approved 1건을 통합 전시 스키마로 변환."""
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
    venue = gallery_venues_by_key.get(vk, {})
    # venue_key가 비어있으면 venue_name으로 매칭 시도
    if not venue and it.get("venue_name"):
        vn = it["venue_name"].replace(" ", "")
        for k, v in gallery_venues_by_key.items():
            if v.get("venue_name", "").replace(" ", "") == vn:
                venue = v
                vk = k
                break
    return {
        "id": it["id"],
        "source": it.get("source", "submission"),
        "title": title,
        "artists": it.get("artists", ""),
        "venue_raw": it.get("venue_name", ""),
        "venue_key": vk or "unknown_submission",
        "venue_name": venue.get("venue_name") or it.get("venue_name", ""),
        "region": venue.get("region", "seoul"),  # 제보는 기본 seoul로
        "address": venue.get("address", ""),
        "lat": venue.get("lat"),
        "lng": venue.get("lng"),
        "start_date": start,
        "end_date": end,
        "price": "",
        "url": it.get("source_url", ""),
        "thumbnail": it.get("thumbnail", ""),
        "status": compute_status(start, end, today) if start else "active",
        "collected_at": it.get("submitted_at", now_iso()),
    }


def build_venues_grouped(exhibitions: list, all_venues_meta: list) -> list:
    """전시 평면 리스트를 분관별로 그룹화 (이미 grouped인 SeMA·MMCA 출력과 형식 통일)."""
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
        venues_out.append({
            "venue_key": vk,
            "venue_name": v.get("venue_name", ""),
            "region": v.get("region", "unknown"),
            "address": v.get("address", ""),
            "lat": v.get("lat"), "lng": v.get("lng"),
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
    # 메타에 없지만 데이터에 있는 venue들 (예: unknown_submission, 외부 협력)
    for vk, lst in by_v.items():
        if vk in seen_keys: continue
        lst_sorted = sorted(lst, key=lambda e: e.get("start_date") or "9999")
        sample = lst[0]
        venues_out.append({
            "venue_key": vk,
            "venue_name": sample.get("venue_name", "(미분류)"),
            "region": sample.get("region", "unknown"),
            "address": sample.get("address", ""),
            "lat": sample.get("lat"), "lng": sample.get("lng"),
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

    outdir = HERE / "data"
    outdir.mkdir(parents=True, exist_ok=True)

    # 1) 통합 전시 평면 — SeMA + MMCA + 승인된 제보
    all_exs: list = []
    sources: list = []
    if sema_exh: all_exs.extend(sema_exh.get("exhibitions", [])); sources.append("sema")
    if mmca_exh: all_exs.extend(mmca_exh.get("exhibitions", [])); sources.append("mmca")

    # 갤러리 venues 키 인덱스
    gv_by_key = {}
    if gallery_venues_doc:
        for v in gallery_venues_doc.get("venues", []):
            gv_by_key[v["venue_key"]] = v

    approved_count = 0
    if queue:
        for it in queue.get("items", []):
            ex = submission_to_exhibition(it, gv_by_key)
            if ex:
                # 중복 체크 (같은 id면 스킵)
                if not any(e.get("id") == ex["id"] for e in all_exs):
                    all_exs.append(ex)
                    approved_count += 1
        if approved_count: sources.append("submissions")

    all_exs.sort(key=lambda e: e.get("start_date") or "9999")

    # 2) 전체 venues 메타 모음 (그룹화용)
    all_venues_meta: list = []
    for doc in [sema_venues_doc, mmca_venues_doc, gallery_venues_doc]:
        if doc:
            all_venues_meta.extend(doc.get("venues", []))

    # 3) 분관별 그룹화
    venues_grouped = build_venues_grouped(all_exs, all_venues_meta)
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

    # 교육 — 그대로
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

    # 요약
    print(f"\n[Merger v3] 통합 완료", file=sys.stderr)
    print(f"  전시 평면 총 {len(all_exs)}건 (서울 {len(seoul_exs)}건)", file=sys.stderr)
    print(f"  분관 마커 {len(active_venues)}곳 (서울 {len(seoul_venues)}곳)", file=sys.stderr)
    print(f"  승인된 제보 통합: {approved_count}건", file=sys.stderr)
    print(f"  교육: {len(all_progs)}건", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
