"""
SeMA + MMCA 데이터 통합 스크립트
================================

각 크롤러가 만든 결과를 하나의 파일로 합칩니다.
사이트는 단일 URL만 알면 모든 데이터를 받아볼 수 있게 됩니다.

입력:
    ../sema_crawler/data/exhibitions_latest.json
    ../sema_crawler/data/venues_with_exhibitions_latest.json
    ../mmca_crawler/data/exhibitions_latest.json
    ../mmca_crawler/data/venues_with_exhibitions_latest.json
    ../mmca_crawler/data/programs_latest.json

출력:
    data/all_exhibitions_latest.json   ← 전체 전시 (SeMA + MMCA, 평면)
    data/all_venues_latest.json        ← 전체 분관별 그룹화 (마커별 리스트)
    data/all_programs_latest.json      ← 전체 교육프로그램
    data/all_exhibitions_seoul_only.json   ← 서울만 필터링한 편의 버전
    data/all_venues_seoul_only.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


HERE = Path(__file__).parent
ROOT = HERE.parent


def load_json(p: Path) -> dict | None:
    if not p.exists():
        print(f"[skip] {p} 없음", file=sys.stderr)
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def main() -> int:
    sema_exh = load_json(ROOT / "sema_crawler" / "data" / "exhibitions_latest.json")
    sema_grp = load_json(ROOT / "sema_crawler" / "data" / "venues_with_exhibitions_latest.json")
    mmca_exh = load_json(ROOT / "mmca_crawler" / "data" / "exhibitions_latest.json")
    mmca_grp = load_json(ROOT / "mmca_crawler" / "data" / "venues_with_exhibitions_latest.json")
    mmca_prog = load_json(ROOT / "mmca_crawler" / "data" / "programs_latest.json")

    outdir = HERE / "data"
    outdir.mkdir(parents=True, exist_ok=True)

    # 1) 통합 전시 (평면)
    all_exs = []
    sources = []
    if sema_exh:
        all_exs.extend(sema_exh.get("exhibitions", []))
        sources.append("sema")
    if mmca_exh:
        all_exs.extend(mmca_exh.get("exhibitions", []))
        sources.append("mmca")
    # 시작일 빠른 순
    all_exs.sort(key=lambda e: (e.get("start_date") or "9999"))

    payload_exs = {
        "generated_at": now_iso(),
        "sources": sources,
        "count": len(all_exs),
        "exhibitions": all_exs,
    }
    (outdir / "all_exhibitions_latest.json").write_text(
        json.dumps(payload_exs, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 서울만 필터
    seoul_exs = [e for e in all_exs if e.get("region") == "seoul"]
    (outdir / "all_exhibitions_seoul_only.json").write_text(
        json.dumps({**payload_exs, "count": len(seoul_exs),
                    "filter": "region=seoul", "exhibitions": seoul_exs},
                   ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # 2) 통합 분관별 그룹 (지도 마커용)
    all_venues = []
    if sema_grp:
        all_venues.extend(sema_grp.get("venues", []))
    if mmca_grp:
        all_venues.extend(mmca_grp.get("venues", []))
    # 빈 분관은 제외
    all_venues_active = [v for v in all_venues
                         if (v.get("active_count", 0) + v.get("upcoming_count", 0)) > 0]

    payload_venues = {
        "generated_at": now_iso(),
        "sources": sources,
        "venue_count": len(all_venues_active),
        "venues": all_venues_active,
    }
    (outdir / "all_venues_latest.json").write_text(
        json.dumps(payload_venues, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 서울만
    seoul_venues = [v for v in all_venues_active if v.get("region") == "seoul"]
    (outdir / "all_venues_seoul_only.json").write_text(
        json.dumps({**payload_venues, "venue_count": len(seoul_venues),
                    "filter": "region=seoul", "venues": seoul_venues},
                   ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # 3) 통합 교육 프로그램
    all_progs = []
    prog_sources = []
    if mmca_prog:
        all_progs.extend(mmca_prog.get("programs", []))
        prog_sources.append("mmca")
    all_progs.sort(key=lambda p: (p.get("start_date") or "9999"))

    payload_progs = {
        "generated_at": now_iso(),
        "sources": prog_sources,
        "count": len(all_progs),
        "programs": all_progs,
    }
    (outdir / "all_programs_latest.json").write_text(
        json.dumps(payload_progs, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 요약
    print(f"\n[Merger] 통합 완료", file=sys.stderr)
    print(f"  전시 전체: {len(all_exs)}건 (서울만: {len(seoul_exs)}건)", file=sys.stderr)
    print(f"  분관 마커: {len(all_venues_active)}곳 (서울만: {len(seoul_venues)}곳)", file=sys.stderr)
    print(f"  교육 전체: {len(all_progs)}건", file=sys.stderr)

    by_src = {}
    for e in all_exs:
        s = e.get("source", "?")
        by_src[s] = by_src.get(s, 0) + 1
    print(f"\n  소스별 전시: {by_src}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
