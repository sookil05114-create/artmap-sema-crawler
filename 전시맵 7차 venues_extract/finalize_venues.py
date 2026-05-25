"""최종 dedup + venue_key 권역 접두어 적용.

입력:
- venues_new.json (130곳)
- existing/gallery_crawler_venues.json (34곳)
- existing/craft_museum_venues.json (2곳)

출력:
- venues_new_final.json  (gallery_crawler/venues.json 머지용)
- dedup_decisions.md     (제외/유지 결정 리포트)
"""
import json
import re
import unicodedata
from urllib.parse import urlparse

NEW_PATH = "venues_new.json"
EXISTING_PATHS = [
    "existing/gallery_crawler_venues.json",
    "existing/craft_museum_venues.json",
]

# 별도 daily 크롤러가 처리하므로 venues.json에 등록하면 안 되는 것들
# (sema_daily.yml: SeMA crawler, MMCA crawler — 자체 venue 출력)
DAILY_CRAWLER_EXCLUDE_NAMES = [
    "서울시립미술관",       # sema_daily → SeMA crawler
    "sema",
    "국립현대미술관",       # sema_daily → MMCA crawler (서울관 + 덕수궁관)
    "mmca",
]


# 인스타·주소를 공유하지만 별개 공간으로 인정해야 하는 venue (사용자 결정)
# 매칭은 venue_name에 포함되는 키워드로 — 정규화된 한쪽 venue가 살아남고 이 키워드를 가진 venue도 유지
FORCE_KEEP_NAMES = [
    "한가람디자인미술관",  # 한가람미술관과 별개 공간 (예술의전당 캠퍼스)
]


def is_force_keep(name: str) -> bool:
    if not name:
        return False
    n = re.sub(r"\s+", "", name)
    for kw in FORCE_KEEP_NAMES:
        if re.sub(r"\s+", "", kw) in n:
            return True
    return False


def is_daily_crawler_target(name: str) -> bool:
    if not name:
        return False
    low = name.lower()
    for kw in DAILY_CRAWLER_EXCLUDE_NAMES:
        if kw.lower() in low:
            return True
    return False


def normalize_name(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s).strip()
    s = re.sub(r"[\(\[\{].*?[\)\]\}]", "", s)
    s = re.sub(r"\s+", "", s)
    return s.lower()


def insta_handle(url: str):
    if not url:
        return None
    m = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", url)
    return m.group(1).rstrip("/").lower() if m else None


def domain_of(url: str):
    if not url:
        return None
    try:
        d = urlparse(url).netloc.lower()
        if d.startswith("www."):
            d = d[4:]
        return d or None
    except Exception:
        return None


def load_existing():
    pool = []
    for path in EXISTING_PATHS:
        with open(path) as f:
            data = json.load(f)
        venues = data.get("venues", []) if isinstance(data, dict) else data
        for v in venues:
            pool.append({
                "src": path,
                "venue_key": v.get("venue_key"),
                "venue_name": v.get("venue_name"),
                "norm_name": normalize_name(v.get("venue_name") or ""),
                "insta": (v.get("instagram_handle") or insta_handle(v.get("instagram_url") or "")),
                "domain": domain_of(v.get("official_url") or ""),
                "aliases_norm": [normalize_name(a) for a in (v.get("aliases") or [])],
            })
    return pool


def match_existing(nv, pool):
    nname = normalize_name(nv.get("venue_name", ""))
    naliases = [normalize_name(a) for a in nv.get("aliases", [])]
    ninsta = insta_handle(nv.get("instagram_url") or "")
    ndomain = domain_of(nv.get("official_url") or "")
    best = None
    best_score = 0
    for ex in pool:
        s = 0
        reasons = []
        if ninsta and ex["insta"] and ninsta == ex["insta"]:
            s += 3; reasons.append(f"insta={ninsta}")
        if ndomain and ex["domain"] and ndomain == ex["domain"]:
            s += 2; reasons.append(f"domain={ndomain}")
        if nname and (nname == ex["norm_name"] or nname in ex["aliases_norm"]):
            s += 2; reasons.append("name_match")
        for a in naliases:
            if a and (a == ex["norm_name"] or a in ex["aliases_norm"]):
                s += 1; reasons.append("alias_match"); break
        if s > best_score:
            best_score = s
            best = (ex, reasons)
    if best_score >= 2:
        return best
    return None


SUBREGION_PREFIX = {
    "jongno": "jongno",
    "junggu": "junggu",
    "gangnam": "gangnam",
    "seocho": "seocho",
    "seongdong": "seongdong",
    "yongsan": "yongsan",
    "mapo": "mapo",
}


try:
    from korean_romanizer.romanizer import Romanizer
    _HAS_ROMANIZER = True
except ImportError:
    _HAS_ROMANIZER = False


def slugify_base(name: str) -> str:
    """venue_name → ASCII snake_case 슬러그. 한글은 로마자 변환."""
    if not name:
        return "unknown"
    s = unicodedata.normalize("NFKC", name).strip()
    s = re.sub(r"[\(\[\{].*?[\)\]\}]", "", s).strip()
    # 한글이 포함되면 로마자 변환
    if _HAS_ROMANIZER and re.search(r"[ㄱ-힝]", s):
        s = Romanizer(s).romanize()
    s = s.lower()
    s = re.sub(r"[\s\-·\./+&]+", "_", s)
    s = re.sub(r"[^0-9a-z_]", "", s)  # ASCII만
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "unknown"


def english_alias(name: str):
    if not name:
        return None
    m = re.search(r"[\(\[]([A-Za-z][A-Za-z0-9 \-_\.&']+)[\)\]]", name)
    return m.group(1).strip() if m else None


def prefixed_key(nv: dict, taken: set) -> str:
    """권역 접두어 + 슬러그. 영문 별칭 우선 → 한국어 베이스."""
    name = nv["venue_name"]
    en = english_alias(name) or next((a for a in nv.get("aliases", []) if re.match(r"^[A-Za-z]", a)), None)
    base = slugify_base(en) if en else slugify_base(name)
    prefix = SUBREGION_PREFIX.get(nv["subregion"], nv["subregion"])
    key = f"{prefix}_{base}"
    orig = key
    suffix = 2
    while key in taken:
        key = f"{orig}_{suffix}"
        suffix += 1
    taken.add(key)
    return key


def main():
    new_venues = json.load(open(NEW_PATH))
    existing_pool = load_existing()

    # 0) daily 크롤러 처리 대상 제외 (sema, mmca)
    excluded_daily = []
    after_daily = []
    for nv in new_venues:
        if is_daily_crawler_target(nv["venue_name"]):
            excluded_daily.append({
                "new_name": nv["venue_name"],
                "reason": "sema_daily.yml (SeMA/MMCA crawler)에서 별도 처리",
            })
        else:
            after_daily.append(nv)

    # 1) 기존 gallery_crawler/craft venues.json과 중복 식별
    excluded_existing = []
    kept = []
    for nv in after_daily:
        m = match_existing(nv, existing_pool)
        if m:
            ex, reasons = m
            excluded_existing.append({
                "new_key_old": nv["venue_key"],
                "new_name": nv["venue_name"],
                "existing_key": ex["venue_key"],
                "existing_name": ex["venue_name"],
                "reasons": reasons,
                "verification_status": nv.get("verification_status"),
                "verified_extras": {
                    k: nv.get(k) for k in ("address", "phone", "email", "hours", "exhibit_channel")
                    if nv.get(k)
                },
            })
        else:
            kept.append(nv)

    # 2) 신규 내부 중복: insta + subregion + (address OR 정규화된 name) 모두 일치해야 중복으로 간주
    #    (단순 insta만으로는 한가람미술관/디자인미술관 같은 분관을 잘못 합침)
    def addr_norm(a):
        a = (a or "").strip()
        a = re.sub(r"\s+", " ", a)
        return a.lower()

    seen = {}  # key: (insta, subregion, addr_or_name_norm) → first venue
    excluded_internal = []
    deduped = []
    for nv in kept:
        # FORCE_KEEP는 dedup 검사 건너뛰고 무조건 유지
        if is_force_keep(nv["venue_name"]):
            deduped.append(nv)
            continue
        ih = insta_handle(nv.get("instagram_url") or "")
        addr = addr_norm(nv.get("address"))
        name_n = normalize_name(nv.get("venue_name"))
        if ih:
            # 1차: insta + subregion + 주소
            sig = (ih, nv["subregion"], addr) if addr else None
            if sig and sig in seen:
                excluded_internal.append({
                    "kept_key_old": seen[sig]["venue_key"],
                    "kept_name": seen[sig]["venue_name"],
                    "removed_key_old": nv["venue_key"],
                    "removed_name": nv["venue_name"],
                    "reason": f"동일 subregion + insta @{ih} + 동일 주소",
                    "verification_status_removed": nv.get("verification_status"),
                })
                continue
            if sig:
                seen[sig] = nv
            # 2차: insta + subregion + 정규화 이름 (주소가 없거나 미스매치 시)
            sig2 = (ih, nv["subregion"], name_n)
            if sig2 in seen and not addr:
                excluded_internal.append({
                    "kept_key_old": seen[sig2]["venue_key"],
                    "kept_name": seen[sig2]["venue_name"],
                    "removed_key_old": nv["venue_key"],
                    "removed_name": nv["venue_name"],
                    "reason": f"동일 subregion + insta @{ih} + 동일 이름",
                    "verification_status_removed": nv.get("verification_status"),
                })
                continue
            seen[sig2] = nv
        deduped.append(nv)

    # 3) venue_key 권역 접두어 적용
    taken = set()
    for nv in deduped:
        nv["venue_key"] = prefixed_key(nv, taken)

    # 4) 출력 (기존 스키마에 맞춰 {"_comment", "venues":[]} wrapper)
    out = {
        "_comment": "종로/중구/강남·서초 알바 검증 표본에서 추출 (130곳 → 기존 dedup 21건 + 내부 dedup 후 최종)",
        "source_doc": "서울미술공간_표본300_알바작업시트.xlsx (시트: 종로, 중구, 강남·서초)",
        "venues": deduped,
    }
    with open("venues_new_final.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # 5) dedup_decisions.md 리포트
    lines = []
    lines.append("# Dedup 결정 리포트\n")
    lines.append(f"- 입력 신규 venue: **{len(new_venues)}곳**")
    lines.append(f"- daily 크롤러 처리 대상 (sema/mmca) → 제외: **{len(excluded_daily)}곳**")
    lines.append(f"- 기존(gallery_crawler + craft_museum_crawler)과 중복 → 제외: **{len(excluded_existing)}곳**")
    lines.append(f"- 신규 내부 중복 → 제외: **{len(excluded_internal)}곳**")
    lines.append(f"- 최종 신규 추가: **{len(deduped)}곳**\n")

    if excluded_daily:
        lines.append("## daily 크롤러 처리 대상 (별도 워크플로우)\n")
        for e in excluded_daily:
            lines.append(f"- {e['new_name']} — {e['reason']}")
        lines.append("")

    lines.append("## 기존과 중복 (신규에서 제외)\n")
    lines.append("| 신규 이름 | 기존 venue_key | 매칭 근거 | 검증 결과로 보완 가능한 필드 |")
    lines.append("|---|---|---|---|")
    for e in excluded_existing:
        extras = ", ".join(f"{k}={v[:30]}..." if len(str(v)) > 30 else f"{k}={v}" for k, v in e["verified_extras"].items()) or "—"
        reasons = ", ".join(e["reasons"])
        lines.append(f"| {e['new_name']} | `{e['existing_key']}` | {reasons} | {extras} |")
    lines.append("\n> 💡 이 21곳의 알바 검증 정보 (주소/전화/이메일/운영시간/전시갱신채널)는 "
                 "기존 venues.json에 부분 보완할 수 있습니다. 별도 PR로 따로 작업 권장.\n")

    lines.append("## 신규 내부 중복 (제거)\n")
    lines.append("| 유지 | 제거 | 이유 |")
    lines.append("|---|---|---|")
    for e in excluded_internal:
        lines.append(f"| {e['kept_name']} | {e['removed_name']} ({e.get('verification_status_removed','?')}) | {e['reason']} |")
    if not excluded_internal:
        lines.append("| (없음) | | |")
    lines.append("")

    lines.append("## 최종 venue_key 목록 (권역 접두어 적용)\n")
    by_sub = {}
    for v in deduped:
        by_sub.setdefault(v["subregion"], []).append(v)
    for sub in sorted(by_sub):
        lines.append(f"### {sub} ({len(by_sub[sub])}곳)\n")
        for v in by_sub[sub]:
            flag = " 🟡pending" if v.get("verification_status") == "pending" else ""
            flag += " 📍수동좌표" if v.get("manual_coord_needed") else ""
            lines.append(f"- `{v['venue_key']}` — {v['venue_name']}{flag}")
        lines.append("")

    with open("dedup_decisions.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # 출력 요약
    print(f"신규 입력:        {len(new_venues)}곳")
    print(f"daily 처리 제외:  {len(excluded_daily)}곳")
    print(f"기존과 중복 제외: {len(excluded_existing)}곳")
    print(f"내부 중복 제외:   {len(excluded_internal)}곳")
    print(f"최종 추가:        {len(deduped)}곳")
    print(f"\n→ venues_new_final.json (gallery_crawler/venues.json에 머지)")
    print(f"→ dedup_decisions.md (사용자 검토용 리포트)")

    print("\n=== subregion 분포 ===")
    for sub in sorted(by_sub):
        print(f"  {sub:12s}: {len(by_sub[sub])}곳")

    print("\n=== verification_status ===")
    by_v = {}
    for v in deduped:
        s = v.get("verification_status", "?")
        by_v[s] = by_v.get(s, 0) + 1
    for k, c in by_v.items():
        print(f"  {k}: {c}곳")


if __name__ == "__main__":
    main()
