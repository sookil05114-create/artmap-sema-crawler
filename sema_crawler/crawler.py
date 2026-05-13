"""
SeMA(서울시립미술관) 전시 크롤러 — v2.2

v2.1 → v2.2 변경:
- venue_raw에서 괄호 안 주소 자동 제거
  예: "충무아트센터 갤러리(서울 중구 퇴계로 287)" → "충무아트센터 갤러리"
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlencode

import requests
from bs4 import BeautifulSoup

BASE = "https://sema.seoul.go.kr"
LIST_PATH = "/kr/whatson/landing"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/121.0.0.0 Safari/537.36")
SLEEP_SECONDS = 4.0
TIMEOUT = 45
MAX_RETRIES = 4
BACKOFF = [5, 15, 30, 60]

ADDR_PAREN_RE = re.compile(
    r"\s*\(\s*(?:서울|경기|인천|부산|대구|광주|대전|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주)\s[^)]*\)\s*$"
)
ADDR_PAREN_GENERIC_RE = re.compile(
    r"\s*\([^)]*(?:로\s*\d|길\s*\d|동\s*\d|번지|읍|면\s*\d)[^)]*\)\s*$"
)


def clean_venue_name(raw: str) -> str:
    if not raw:
        return raw
    s = ADDR_PAREN_RE.sub("", raw)
    s = ADDR_PAREN_GENERIC_RE.sub("", s)
    return s.strip()


@dataclass
class Exhibition:
    id: str
    source: str
    title: str
    artists: str
    venue_raw: str
    venue_key: str
    venue_name: str
    region: str
    address: str
    lat: float | None
    lng: float | None
    start_date: str
    end_date: str
    price: str
    url: str
    thumbnail: str
    status: str
    collected_at: str

    def for_csv(self) -> dict:
        d = asdict(self)
        d["lat"] = "" if self.lat is None else self.lat
        d["lng"] = "" if self.lng is None else self.lng
        return d


def load_venues(path: Path) -> tuple[dict, list]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    lookup = {}
    for v in raw["venues"]:
        for n in [v["venue_name"]] + v.get("aliases", []):
            lookup[n.replace(" ", "")] = v
    return lookup, raw["venues"]


def match_venue(venue_raw: str, lookup: dict) -> dict | None:
    key = venue_raw.replace(" ", "")
    if key in lookup:
        return lookup[key]
    for cand_key, v in lookup.items():
        if cand_key in key or key in cand_key:
            return v
    return None


def http_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    return s


def retry_request(fn, label: str):
    last_err = None
    for i in range(MAX_RETRIES):
        try:
            return fn()
        except (requests.ConnectionError, requests.Timeout,
                requests.exceptions.ChunkedEncodingError) as e:
            last_err = e
            if i == MAX_RETRIES - 1:
                break
            wait = BACKOFF[i]
            print(f"  [{label}] 재시도 {i+1}/{MAX_RETRIES} "
                  f"({e.__class__.__name__}) — {wait}초 대기",
                  file=sys.stderr)
            time.sleep(wait)
    print(f"  [{label}] 최종 실패: {last_err}", file=sys.stderr)
    raise last_err


def prime_session(sess: requests.Session) -> None:
    def call():
        r = sess.get(f"{BASE}/", timeout=TIMEOUT)
        r.raise_for_status()
        return r
    try:
        retry_request(call, label="prime")
        time.sleep(2)
    except Exception as e:
        print(f"  prime failed (계속 진행): {e}", file=sys.stderr)


def fetch(sess: requests.Session, url: str) -> str:
    def call():
        r = sess.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        return r.text
    return retry_request(call, label=url[-60:])


DATE_RANGE_RE = re.compile(r"(\d{4})[./](\d{1,2})[./](\d{1,2})\s*~\s*(\d{4})[./](\d{1,2})[./](\d{1,2})")
PERMANENT_RE = re.compile(r"상시")


def parse_date(y, m, d):
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def parse_list_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    cards = []
    for a in soup.select("a"):
        text = a.get_text(" ", strip=True)
        if not text:
            continue
        m = DATE_RANGE_RE.search(text) or PERMANENT_RE.search(text)
        if not m:
            continue
        title_el = a.find("strong") or a.find("b")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title or len(title) < 2:
            continue
        img = a.find("img")
        thumbnail = urljoin(BASE, img["src"]) if img and img.get("src") else ""
        venue = ""
        spans = [s.get_text(" ", strip=True) for s in a.find_all(["span", "p", "em"])]
        for s in spans:
            if s.endswith(",") and "전시" not in s and "프로그램" not in s:
                venue = s.rstrip(",").strip()
                break
        if not venue:
            after = text.split(title, 1)[1].strip() if title in text else text
            parts = re.split(r"[,\n]", after, maxsplit=2)
            if len(parts) >= 2:
                venue = parts[1].strip()
        venue = clean_venue_name(venue)

        if isinstance(m, re.Match) and m.re is DATE_RANGE_RE:
            start = parse_date(m.group(1), m.group(2), m.group(3))
            end = parse_date(m.group(4), m.group(5), m.group(6))
        else:
            start = "permanent"
            end = "permanent"
        href = a.get("href", "")
        if href and href.startswith("/"):
            href = urljoin(BASE, href)
        cards.append({
            "title": title, "venue_raw": venue,
            "start_date": start, "end_date": end,
            "thumbnail": thumbnail,
            "url": href if href and not href.startswith("javascript:") else "",
        })
    seen = set()
    uniq = []
    for c in cards:
        k = (c["title"], c["venue_raw"], c["start_date"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(c)
    return uniq


def compute_status(start: str, end: str, today: date) -> str:
    if start == "permanent":
        return "permanent"
    try:
        s = datetime.strptime(start, "%Y-%m-%d").date()
        e = datetime.strptime(end, "%Y-%m-%d").date()
    except ValueError:
        return "unknown"
    if today < s:
        return "upcoming"
    if today > e:
        return "ended"
    return "active"


def collect(when_types: Iterable[str], venues_path: Path) -> list[Exhibition]:
    lookup, _ = load_venues(venues_path)
    today = date.today()
    out: list[Exhibition] = []
    sess = http_session()
    prime_session(sess)

    for when in when_types:
        for page in range(1, 6):
            q = {"whatsonMenuDivList": "EX", "whatChoice2": "N", "whatChoice3": "N",
                 "whatChoice4": "N", "whenType": when, "pageIndex": page}
            url = f"{BASE}{LIST_PATH}?{urlencode(q)}"
            print(f"[SeMA fetch] {when} page={page}", file=sys.stderr)
            try:
                html = fetch(sess, url)
            except Exception as e:
                print(f"  page {page} 영구 실패: {e}", file=sys.stderr)
                break
            cards = parse_list_page(html)
            if not cards:
                break
            added = 0
            for c in cards:
                v = match_venue(c["venue_raw"], lookup) or {}
                eid = hashlib.sha1(
                    f"sema|{c['title']}|{c['venue_raw']}|{c['start_date']}".encode("utf-8")
                ).hexdigest()[:12]
                if any(o.id == eid for o in out):
                    continue
                ex = Exhibition(
                    id=eid, source="sema",
                    title=c["title"], artists="",
                    venue_raw=c["venue_raw"],
                    venue_key=v.get("venue_key", "unknown"),
                    venue_name=v.get("venue_name", c["venue_raw"]),
                    region=v.get("region", "seoul"),
                    address=v.get("address", ""),
                    lat=v.get("lat"), lng=v.get("lng"),
                    start_date=c["start_date"], end_date=c["end_date"],
                    price="무료",
                    url=c["url"], thumbnail=c["thumbnail"],
                    status=compute_status(c["start_date"], c["end_date"], today),
                    collected_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
                )
                out.append(ex)
                added += 1
            if added == 0:
                break
            time.sleep(SLEEP_SECONDS)
    return out


def build_grouped(exhibitions: list[Exhibition], venues: list) -> dict:
    by_venue: dict[str, list] = {}
    for e in exhibitions:
        if e.status not in ("active", "upcoming"):
            continue
        by_venue.setdefault(e.venue_key, []).append(e)

    venues_out = []
    for v in venues:
        lst = by_venue.get(v["venue_key"], [])
        lst_sorted = sorted(lst, key=lambda e: (e.start_date or "9999"))
        venues_out.append({
            "venue_key": v["venue_key"],
            "venue_name": v["venue_name"],
            "region": v.get("region", "seoul"),
            "address": v.get("address", ""),
            "lat": v.get("lat"), "lng": v.get("lng"),
            "official_url": v.get("official_url", ""),
            "active_count": sum(1 for e in lst if e.status == "active"),
            "upcoming_count": sum(1 for e in lst if e.status == "upcoming"),
            "exhibitions": [
                {"id": e.id, "title": e.title, "start_date": e.start_date,
                 "end_date": e.end_date, "status": e.status,
                 "thumbnail": e.thumbnail, "url": e.url, "price": e.price}
                for e in lst_sorted
            ],
        })
    unknown = by_venue.get("unknown", [])
    if unknown:
        venues_out.append({
            "venue_key": "unknown",
            "venue_name": "기타·외부 협력",
            "region": "unknown",
            "address": "", "lat": None, "lng": None,
            "official_url": "",
            "active_count": sum(1 for e in unknown if e.status == "active"),
            "upcoming_count": sum(1 for e in unknown if e.status == "upcoming"),
            "exhibitions": [
                {"id": e.id, "title": e.title, "venue_raw": e.venue_raw,
                 "start_date": e.start_date, "end_date": e.end_date,
                 "status": e.status, "thumbnail": e.thumbnail, "url": e.url, "price": e.price}
                for e in sorted(unknown, key=lambda x: x.start_date or "9999")
            ],
        })

    return {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "source": "sema",
        "venue_count": sum(1 for v in venues_out if v["active_count"] + v["upcoming_count"] > 0),
        "venues": venues_out,
    }


def save(exhibitions: list[Exhibition], venues: list, outdir: Path, today_iso: str) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    fields = list(Exhibition.__annotations__.keys())
    for name in [f"exhibitions_{today_iso}.csv", "exhibitions_latest.csv"]:
        with (outdir / name).open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for e in exhibitions:
                w.writerow(e.for_csv())
    payload = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "source": "sema",
        "count": len(exhibitions),
        "exhibitions": [asdict(e) for e in exhibitions],
    }
    for name in [f"exhibitions_{today_iso}.json", "exhibitions_latest.json"]:
        (outdir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    grouped = build_grouped(exhibitions, venues)
    (outdir / "venues_with_exhibitions_latest.json").write_text(
        json.dumps(grouped, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--current-only", action="store_true")
    ap.add_argument("--venues", default=str(Path(__file__).parent / "venues.json"))
    ap.add_argument("--outdir", default=str(Path(__file__).parent / "data"))
    args = ap.parse_args()

    when_types = ["FROM_TODAY"] if args.current_only else ["FROM_TODAY", "PLAN_DAY"]
    _, venues_meta = load_venues(Path(args.venues))
    try:
        exhibitions = collect(when_types, Path(args.venues))
    except Exception as e:
        print(f"\n[SeMA] 수집 실패: {e}", file=sys.stderr)
        return 1
    save(exhibitions, venues_meta, Path(args.outdir), date.today().isoformat())

    by_venue: dict[str, int] = {}
    for e in exhibitions:
        by_venue[e.venue_name] = by_venue.get(e.venue_name, 0) + 1
    print(f"\n[SeMA] 수집 완료: {len(exhibitions)}건", file=sys.stderr)
    for v, n in sorted(by_venue.items(), key=lambda kv: -kv[1]):
        print(f"  {v}: {n}건", file=sys.stderr)
    return 0 if exhibitions else 1


if __name__ == "__main__":
    sys.exit(main())
