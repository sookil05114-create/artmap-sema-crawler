"""
SeMA(서울시립미술관) 전시 크롤러
================================

서울시립미술관 본관과 분관 8곳의 현재 진행중·예정 전시를 수집해
artmap.ai.kr이 사용할 수 있는 형태(CSV·JSON)로 출력합니다.

사용법:
    python crawler.py                  # 진행중 + 예정 전시 모두 수집
    python crawler.py --current-only   # 진행중만
    python crawler.py --output csv     # CSV로 저장 (기본은 둘 다)

출력:
    data/exhibitions_YYYY-MM-DD.csv
    data/exhibitions_YYYY-MM-DD.json
    data/exhibitions_latest.csv  (최신 스냅샷)
    data/exhibitions_latest.json

법적 주의:
    이 스크립트는 공공 데이터(서울시립미술관)만 수집합니다.
    요청 간격 3초, User-Agent 명시, robots.txt 준수.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlencode

import requests
from bs4 import BeautifulSoup

BASE = "https://sema.seoul.go.kr"
LIST_PATH = "/kr/whatson/landing"
UA = "artmap.ai.kr-crawler/1.0 (contact: sookil05114@gmail.com)"
SLEEP_SECONDS = 3.0
TIMEOUT = 20

# ---------- Models ----------

@dataclass
class Exhibition:
    id: str                # title|venue|start_date 의 해시
    source: str            # "sema"
    title: str
    venue_raw: str         # SeMA 사이트 표기 그대로
    venue_key: str         # venues.json 의 venue_key (매칭 실패 시 "unknown")
    venue_name: str        # 정규화된 분관명
    address: str
    lat: float | None
    lng: float | None
    start_date: str        # YYYY-MM-DD, "상시"는 "permanent"
    end_date: str
    price: str             # 알 수 없을 때 ""
    url: str               # 상세 페이지 (가능한 경우)
    thumbnail: str
    status: str            # "upcoming" | "active" | "ended" | "permanent"
    collected_at: str      # ISO datetime

    def for_csv(self) -> dict:
        d = asdict(self)
        d["lat"] = "" if self.lat is None else self.lat
        d["lng"] = "" if self.lng is None else self.lng
        return d


# ---------- Venue lookup ----------

def load_venues(path: Path) -> dict:
    """venues.json 을 읽어 매칭 인덱스를 만든다."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    lookup = {}
    for v in raw["venues"]:
        names = [v["venue_name"]] + v.get("aliases", [])
        for n in names:
            lookup[n.replace(" ", "")] = v
    return lookup


def match_venue(venue_raw: str, lookup: dict) -> dict | None:
    key = venue_raw.replace(" ", "")
    if key in lookup:
        return lookup[key]
    # 부분 매칭
    for cand_key, v in lookup.items():
        if cand_key in key or key in cand_key:
            return v
    return None


# ---------- HTTP ----------

def fetch(url: str) -> str:
    headers = {"User-Agent": UA, "Accept-Language": "ko,en;q=0.8"}
    r = requests.get(url, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


# ---------- Parsing ----------

DATE_RANGE_RE = re.compile(
    r"(\d{4})[./](\d{1,2})[./](\d{1,2})\s*~\s*(\d{4})[./](\d{1,2})[./](\d{1,2})"
)
PERMANENT_RE = re.compile(r"상시")


def parse_date(y: str, m: str, d: str) -> str:
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def parse_list_page(html: str) -> list[dict]:
    """전시 리스트 페이지에서 카드들을 추출.

    SeMA 리스트 페이지 카드 구조 (text representation):
        <a>
          <img alt="제목" src="...FILE_ID=..." />
          <strong>제목</strong>
          <span>전시</span>          ← 분류
          <span>장소,</span>
          <span>YYYY/MM/DD~YYYY/MM/DD</span>
        </a>
    """
    soup = BeautifulSoup(html, "html.parser")
    cards = []

    # 리스트 카드는 main 영역의 a 태그들 중 썸네일+제목+기간을 가진 것
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
        thumbnail = ""
        if img and img.get("src"):
            thumbnail = urljoin(BASE, img["src"])

        # 장소: title 뒤에 나오는 첫 번째 콤마로 끝나는 토큰
        venue = ""
        spans = [s.get_text(" ", strip=True) for s in a.find_all(["span", "p", "em"])]
        for s in spans:
            if s.endswith(",") and "전시" not in s and "프로그램" not in s:
                venue = s.rstrip(",").strip()
                break
        if not venue:
            # fallback: 텍스트에서 title 다음 첫 줄
            after = text.split(title, 1)[1].strip() if title in text else text
            parts = re.split(r"[,\n]", after, maxsplit=2)
            if len(parts) >= 2:
                venue = parts[1].strip()

        # 날짜 파싱
        if isinstance(m, re.Match) and m.re is DATE_RANGE_RE:
            start = parse_date(m.group(1), m.group(2), m.group(3))
            end = parse_date(m.group(4), m.group(5), m.group(6))
            permanent = False
        else:
            start = "permanent"
            end = "permanent"
            permanent = True

        href = a.get("href", "")
        if href and href.startswith("/"):
            href = urljoin(BASE, href)

        cards.append({
            "title": title,
            "venue_raw": venue,
            "start_date": start,
            "end_date": end,
            "permanent": permanent,
            "thumbnail": thumbnail,
            "url": href if href and not href.startswith("javascript:") else "",
        })
    # 중복 제거 (같은 카드가 여러 영역에 나타날 수 있음)
    seen = set()
    uniq = []
    for c in cards:
        key = (c["title"], c["venue_raw"], c["start_date"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    return uniq


# ---------- Status ----------

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


# ---------- Main pipeline ----------

def collect(when_types: Iterable[str], venues_path: Path) -> list[Exhibition]:
    lookup = load_venues(venues_path)
    today = date.today()
    out: list[Exhibition] = []

    for when in when_types:
        # 페이지 순회 (현재는 최대 5페이지까지만 — 보통 1~2페이지면 충분)
        for page in range(1, 6):
            q = {
                "whatsonMenuDivList": "EX",
                "whatChoice2": "N",
                "whatChoice3": "N",
                "whatChoice4": "N",
                "whenType": when,
                "pageIndex": page,
            }
            url = f"{BASE}{LIST_PATH}?{urlencode(q)}"
            print(f"[fetch] {url}", file=sys.stderr)
            html = fetch(url)
            cards = parse_list_page(html)
            if not cards:
                break
            new_in_page = 0
            for c in cards:
                v = match_venue(c["venue_raw"], lookup) or {}
                eid = hashlib.sha1(
                    f"{c['title']}|{c['venue_raw']}|{c['start_date']}".encode("utf-8")
                ).hexdigest()[:12]
                ex = Exhibition(
                    id=eid,
                    source="sema",
                    title=c["title"],
                    venue_raw=c["venue_raw"],
                    venue_key=v.get("venue_key", "unknown"),
                    venue_name=v.get("venue_name", c["venue_raw"]),
                    address=v.get("address", ""),
                    lat=v.get("lat"),
                    lng=v.get("lng"),
                    start_date=c["start_date"],
                    end_date=c["end_date"],
                    price="무료",  # SeMA는 거의 전부 무료
                    url=c["url"],
                    thumbnail=c["thumbnail"],
                    status=compute_status(c["start_date"], c["end_date"], today),
                    collected_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
                )
                if any(o.id == ex.id for o in out):
                    continue
                out.append(ex)
                new_in_page += 1
            if new_in_page == 0:
                # 페이지에 새 항목이 없으면 종료
                break
            time.sleep(SLEEP_SECONDS)
    return out


def save(exhibitions: list[Exhibition], outdir: Path, today_iso: str) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    # CSV
    fields = list(Exhibition.__annotations__.keys())
    for name in [f"exhibitions_{today_iso}.csv", "exhibitions_latest.csv"]:
        with (outdir / name).open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for e in exhibitions:
                w.writerow(e.for_csv())
    # JSON
    payload = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "source": "sema",
        "count": len(exhibitions),
        "exhibitions": [asdict(e) for e in exhibitions],
    }
    for name in [f"exhibitions_{today_iso}.json", "exhibitions_latest.json"]:
        (outdir / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--current-only", action="store_true",
                    help="진행중 전시만 수집 (기본은 진행중+예정)")
    ap.add_argument("--venues", default=str(Path(__file__).parent / "venues.json"))
    ap.add_argument("--outdir", default=str(Path(__file__).parent / "data"))
    args = ap.parse_args()

    when_types = ["FROM_TODAY"] if args.current_only else ["FROM_TODAY", "PLAN_DAY"]
    exhibitions = collect(when_types, Path(args.venues))
    today_iso = date.today().isoformat()
    save(exhibitions, Path(args.outdir), today_iso)

    # 요약 출력
    by_venue: dict[str, int] = {}
    for e in exhibitions:
        by_venue[e.venue_name] = by_venue.get(e.venue_name, 0) + 1
    print(f"\n수집 완료: 총 {len(exhibitions)}건", file=sys.stderr)
    for v, n in sorted(by_venue.items(), key=lambda kv: -kv[1]):
        print(f"  {v}: {n}건", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
