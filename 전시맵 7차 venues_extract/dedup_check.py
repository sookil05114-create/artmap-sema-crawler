"""기존 venues.json (gallery_crawler + craft_museum_crawler)과 신규 venues_new.json 충돌 점검.

매칭 기준 (느슨한 매칭):
1. instagram_handle / instagram_url 동일
2. venue_name 유사 (정규화 후 일치)
3. official_url 도메인 일치
"""
import json
import re
import unicodedata
from urllib.parse import urlparse

NEW_PATH = "venues_new.json"
EXISTING = [
    ("gallery_crawler", "existing/gallery_crawler_venues.json"),
    ("craft_museum_crawler", "existing/craft_museum_venues.json"),
]


def normalize_name(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s).strip()
    s = re.sub(r"[\(\[\{].*?[\)\]\}]", "", s)
    s = re.sub(r"\s+", "", s)
    s = s.lower()
    return s


def insta_handle(url: str) -> str | None:
    if not url:
        return None
    m = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", url)
    return m.group(1).rstrip("/").lower() if m else None


def domain(url: str) -> str | None:
    if not url:
        return None
    try:
        d = urlparse(url).netloc.lower().lstrip("www.")
        return d or None
    except Exception:
        return None


def load_existing():
    pool = []
    for src, path in EXISTING:
        with open(path) as f:
            data = json.load(f)
        venues = data.get("venues", []) if isinstance(data, dict) else data
        for v in venues:
            pool.append({
                "_src": src,
                "venue_key": v.get("venue_key"),
                "venue_name": v.get("venue_name"),
                "norm_name": normalize_name(v.get("venue_name") or ""),
                "insta": (v.get("instagram_handle") or insta_handle(v.get("instagram_url") or "")),
                "domain": domain(v.get("official_url") or ""),
                "aliases": [normalize_name(a) for a in (v.get("aliases") or [])],
            })
    return pool


def match(new_v, existing_pool):
    nname = normalize_name(new_v.get("venue_name", ""))
    naliases = [normalize_name(a) for a in new_v.get("aliases", [])]
    ninsta = insta_handle(new_v.get("instagram_url") or "")
    ndomain = domain(new_v.get("official_url") or "")

    matches = []
    for ex in existing_pool:
        score = 0
        reasons = []
        if ninsta and ex["insta"] and ninsta == ex["insta"]:
            score += 3
            reasons.append(f"insta={ninsta}")
        if ndomain and ex["domain"] and ndomain == ex["domain"]:
            score += 2
            reasons.append(f"domain={ndomain}")
        if nname and (nname == ex["norm_name"] or nname in ex["aliases"]):
            score += 2
            reasons.append(f"name={new_v['venue_name']}≈{ex['venue_name']}")
        # alias 교차
        for a in naliases:
            if a and (a == ex["norm_name"] or a in ex["aliases"]):
                score += 1
                reasons.append(f"alias={a}")
                break
        if score >= 2:
            matches.append((score, ex, reasons))
    matches.sort(key=lambda x: -x[0])
    return matches


def main():
    new_venues = json.load(open(NEW_PATH))
    existing_pool = load_existing()
    print(f"기존 venue: {len(existing_pool)}곳 ({', '.join(set(e['_src'] for e in existing_pool))})")
    print(f"신규 venue: {len(new_venues)}곳\n")

    dup_list = []
    for nv in new_venues:
        ms = match(nv, existing_pool)
        if ms:
            dup_list.append((nv, ms))

    print(f"=== 중복 후보 {len(dup_list)}건 ===")
    for nv, ms in dup_list:
        top = ms[0]
        print(f"\n[NEW] {nv['venue_key']:35s} | {nv['venue_name']}")
        for score, ex, reasons in ms[:2]:
            print(f"  ↔ ({ex['_src']}/score={score}) {ex['venue_key']} | {ex['venue_name']}")
            print(f"     reasons: {', '.join(reasons)}")

    # 신규 내부 중복도 점검
    print("\n=== 신규 내부 중복 점검 ===")
    by_insta = {}
    by_name = {}
    for v in new_venues:
        ih = insta_handle(v.get("instagram_url") or "")
        if ih:
            by_insta.setdefault(ih, []).append(v["venue_key"])
        nm = normalize_name(v.get("venue_name", ""))
        if nm:
            by_name.setdefault(nm, []).append(v["venue_key"])
    for k, keys in by_insta.items():
        if len(keys) > 1:
            print(f"  insta @{k}: {keys}")
    for k, keys in by_name.items():
        if len(keys) > 1:
            print(f"  name '{k}': {keys}")


if __name__ == "__main__":
    main()
