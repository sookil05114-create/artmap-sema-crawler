"""
SeMA(서울시립미술관) 전시 크롤러 — v3.0 (분관별 크롤)

v2.2 → v3.0 변경 (핵심 구조 개편):
- [버그] 기존 pageIndex 파라미터는 서버가 무시 → 항상 1페이지(12건)만 수집됐음.
  실제 페이지네이션 파라미터는 `currentPage`. 이제 "N / M 페이지" 표기를 파싱해
  모든 페이지를 순회한다.
- [구조] 통합 목록에서 venue명을 텍스트로 추측하던 방식 폐기.
  사이트의 분관 필터 파라미터 `exPlace=ORG코드`로 분관별로 나눠 요청하므로
  venue_key가 요청 시점에 이미 확정된다 (오매칭 원천 차단).
  분관 코드: ORG01 서소문본관 / ORG08 북서울 / ORG50 서서울 / ORG03 남서울 /
             ORG51 사진미술관 / ORG52 미술아카이브 / ORG04 난지 / ORG10 백남준의 집 /
             ORG61 기타(외부협력·이동전시 → unknown)
- venues.json에 org_code 필드 추가 (이 파일과 세트로 교체 필요).
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
MAX_PAGES = 10  # 분관별 안전 상한

# 외부협력·이동전시(기타) — venue_key를 확정할 수 없어 unknown으로 수집
ETC_ORG_CODE = "ORG61"

ADDR_PAREN_RE = re.compile(
    r"\s*\(\s*(?:서울|경기|인천|부산|대구|광주|대전|울산|세종|강원|충북|충남|전북|전남|경북|경남|제주)\s[^)]*\)\s*$"
)
ADDR_PAREN_GENERIC_RE = re.compile(
    r"\s*\([^)]*(?:로\s*\d|길\s*\d|동\s*\d|번지|읍|면\s*\d)[^)]*\)\s*$"
)
DATE_RANGE_RE = re.compile(
    r"(\d{4})[./](\d{1,2})[./](\d{1,2})\s*~\s*(\d{4})[./](\d{1,2})[./](\d{1,2})"
)
PERMANENT_RE = re.compile(r"상시")
TOTAL_PAGES_RE = re.compile(r"(\d+)\s*/\s*(\d+)\s*페이지")


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


def load_venues(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw["venues"]


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
    return retry_request(call, label=url[-70:])


def parse_date(y, m, d):
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def parse_total_pages(soup: BeautifulSoup) -> int:
    """페이지 표기 'N / M 페이지'에서 M을 얻는다. 못 찾으면 1."""
    m = TOTAL_PAGES_RE.search(soup.get_text(" ", strip=True))
    if m:
        try:
            return max(1, int(m.group(2)))
        except ValueError:
            pass
    return 1


def parse_list_page(html: str) -> tuple[list[dict], int]:
    """전시 카드 목록 + 전체 페이지 수 반환.

    venue_raw는 참고용으로만 추출 (venue 확정은 분관 코드가 담당).
    """
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
        # 교육프로그램/문화행사/모집 카드 제외 — '전시' 카드만
        # (분관 필터 페이지에는 교육프로그램 카드도 섞여 나올 수 있음)
        if "교육프로그램" in text or "문화행사" in text or "모집" in text:
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
                cand = parts[0].strip()
                cand = re.sub(r"^전시\s*", "", cand)
                if cand and not DATE_RANGE_RE.search(cand):
                    venue = cand
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
        k = (c["title"], c["start_date"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(c)
    return uniq, parse_total_pages(soup)


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


def collect(when_types: list[str], venues_path: Path) -> list[Exhibition]:
    venues = load_venues(venues_path)
    today = date.today()
    out: list[Exhibition] = []
    seen_ids: set[str] = set()
    sess = http_session()
    prime_session(sess)

    # 분관 목록 + 기타(unknown)
    targets = [(v.get("org_code"), v) for v in venues if v.get("org_code")]
    targets.append((ETC_ORG_CODE, None))

    for org_code, vmeta in targets:
        label = vmeta["venue_name"] if vmeta else "기타(외부협력)"
        for when in when_types:
            page = 1
            total_pages = 1
            while page <= min(total_pages, MAX_PAGES):
                q = {"whatsonMenuDivList": "EX",
                     "whenType": when,
                     "exPlace": org_code,
                     "currentPage": page}
                url = f"{BASE}{LIST_PATH}?{urlencode(q)}"
                print(f"[SeMA fetch] {label} {when} page={page}", file=sys.stderr)
                try:
                    html = fetch(sess, url)
                except Exception as e:
                    print(f"  {label} page {page} 영구 실패: {e}", file=sys.stderr)
                    break
                cards, total_pages = parse_list_page(html)
                if not cards:
                    break
                added = 0
                for c in cards:
                    vk = vmeta["venue_key"] if vmeta else "unknown"
                    vname = vmeta["venue_name"] if vmeta else (c["venue_raw"] or "기타·외부 협력")
                    eid = hashlib.sha1(
                        f"sema|{c['title']}|{vk}|{c['start_date']}".encode("utf-8")
                    ).hexdigest()[:12]
                    if eid in seen_ids:
                        continue
                    seen_ids.add(eid)
                    ex = Exhibition(
                        id=eid, source="sema",
                        title=c["title"], artists="",
                        venue_raw=c["venue_raw"],
                        venue_key=vk,
                        venue_name=vname,
                        region=(vmeta.get("region", "seoul") if vmeta else "unknown"),
                        address=(vmeta.get("address", "") if vmeta else ""),
                        lat=(vmeta.get("lat") if vmeta else None),
                        lng=(vmeta.get("lng") if vmeta else None),
                        start_date=c["start_date"], end_date=c["end_date"],
                        price="무료",
                        url=c["url"], thumbnail=c["thumbnail"],
                        status=compute_status(c["start_date"], c["end_date"], today),
                        collected_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    )
                    out.append(ex)
                    added += 1
                if added == 0 and page >= total_pages:
                    break
                page += 1
                time.sleep(SLEEP_SECONDS)
        time.sleep(1)
    return out


def build_grouped(exhibitions: list[Exhibition], venues: list) -> dict:
    by_venue: dict[str, list] = {}
    for e in exhibitions:
        if e.status not in ("active", "upcoming", "permanent"):
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
    venues_meta = load_venues(Path(args.venues))
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
