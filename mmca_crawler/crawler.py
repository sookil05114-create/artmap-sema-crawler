"""
MMCA(국립현대미술관) 전시·교육 크롤러 — v2.1 (네트워크 견고성 강화)

수정 사항 (v2.0 → v2.1):
- User-Agent를 실제 Chrome 브라우저처럼 변경 (봇 차단 회피)
- Accept-Encoding, Accept 헤더 보강
- 연결 실패 시 자동 재시도 (5초 → 15초 → 30초 → 60초 백오프)
- TIMEOUT 25초 → 45초
- MMCA 단계가 실패해도 SeMA 데이터는 손상되지 않도록 별도 처리
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
from urllib.parse import urljoin

import requests

BASE = "https://www.mmca.go.kr"
# ★ 실제 Chrome 브라우저 흉내 (봇 차단 회피)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/121.0.0.0 Safari/537.36")
SLEEP = 4.0
TIMEOUT = 45  # 25 -> 45초로 늘림
MAX_RETRIES = 4
BACKOFF = [5, 15, 30, 60]  # 재시도 간격(초)


# ============================================================
# 공통
# ============================================================

def load_venues(path: Path) -> tuple[dict, list]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    by_code = {v["exh_pla_cd"]: v for v in raw["venues"]}
    return by_code, raw["venues"]


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
    """ConnectionReset/Timeout 시 자동 재시도."""
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


def compute_status(start_iso: str, end_iso: str, today: date) -> str:
    try:
        s = datetime.strptime(start_iso, "%Y-%m-%d").date()
        e = datetime.strptime(end_iso, "%Y-%m-%d").date()
    except Exception:
        return "unknown"
    if today < s:
        return "upcoming"
    if today > e:
        return "ended"
    return "active"


def normalize_date(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    m = re.match(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return s


# ============================================================
# 1) 전시
# ============================================================

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


EXH_AJAX = f"{BASE}/exhibitions/AjaxExhibitionList.do"


def prime_session(sess: requests.Session) -> None:
    """진짜 브라우저처럼 보이도록 메인 페이지를 먼저 GET — 쿠키·세션 확보."""
    def call():
        r = sess.get(f"{BASE}/", timeout=TIMEOUT)
        r.raise_for_status()
        return r
    try:
        retry_request(call, label="prime")
        time.sleep(2)
    except Exception as e:
        print(f"  prime failed (계속 진행): {e}", file=sys.stderr)


def fetch_exhibition_page(sess: requests.Session, exh_flag: str, page: int) -> dict:
    referer = (f"{BASE}/exhibitions/progressList.do" if exh_flag == "1"
               else f"{BASE}/exhibitions/futureProgressList.do")
    data = {
        "exhFlag": exh_flag, "searchExhPlaCd": "", "searchExhCd": "",
        "sort": "1", "pageIndex": str(page),
    }
    headers = {
        "Referer": referer, "Origin": BASE,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    def call():
        r = sess.post(EXH_AJAX, data=data, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    return retry_request(call, label=f"exh flag={exh_flag} page={page}")


def collect_exhibitions(venues_by_code: dict) -> list[Exhibition]:
    sess = http_session()
    prime_session(sess)
    today = date.today()
    out: list[Exhibition] = []

    for exh_flag, label in [("1", "진행중"), ("2", "예정")]:
        for page in range(1, 10):
            print(f"[MMCA 전시:{label}] page={page}", file=sys.stderr)
            try:
                j = fetch_exhibition_page(sess, exh_flag, page)
            except Exception as e:
                print(f"  page {page} 영구 실패: {e}", file=sys.stderr)
                break
            items = j.get("exhibitionsList", [])
            if not items:
                break
            for x in items:
                code = x.get("exhPlaCd", "")
                venue = venues_by_code.get(code, {})
                start = normalize_date(x.get("exhStDt", ""))
                end = normalize_date(x.get("exhEdDt", ""))
                eid = hashlib.sha1(f"mmca|{x.get('exhId','')}".encode()).hexdigest()[:12]
                if any(o.id == eid for o in out):
                    continue
                thumb = x.get("exhThumbImg") or x.get("exhDidImg") or ""
                if thumb and thumb.startswith("/"):
                    thumb = urljoin(BASE, thumb)
                url = (f"{BASE}/exhibitions/exhibitionsDetail.do?"
                       f"exhId={x.get('exhId','')}&exhFlag={exh_flag}")
                price_raw = (x.get("exhAdm") or "").strip()
                price = "무료" if price_raw in ("0", "0원", "") else price_raw
                out.append(Exhibition(
                    id=eid, source="mmca",
                    title=x.get("exhTitle", "").strip(),
                    artists=x.get("exhArtist", "").strip(),
                    venue_raw=x.get("exhPlaNm", ""),
                    venue_key=venue.get("venue_key", f"mmca_{code}"),
                    venue_name=venue.get("venue_name", f"국립현대미술관 {x.get('exhPlaNm','')}"),
                    region=venue.get("region", "unknown"),
                    address=venue.get("address", ""),
                    lat=venue.get("lat"), lng=venue.get("lng"),
                    start_date=start, end_date=end, price=price,
                    url=url, thumbnail=thumb,
                    status=compute_status(start, end, today),
                    collected_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
                ))
            pi = j.get("paginationInfo", {})
            if page >= pi.get("totalPageCount", 1):
                break
            time.sleep(SLEEP)
    return out


# ============================================================
# 2) 교육 프로그램
# ============================================================

@dataclass
class Program:
    id: str
    source: str
    title: str
    venue_raw: str
    venue_key: str
    venue_name: str
    venue_detail: str
    region: str
    address: str
    lat: float | None
    lng: float | None
    start_date: str
    end_date: str
    time_range: str
    target_audience: str
    target_category: str
    price: str
    capacity: str
    application_status: str
    url: str
    thumbnail: str
    status: str
    collected_at: str

    def for_csv(self) -> dict:
        d = asdict(self)
        d["lat"] = "" if self.lat is None else self.lat
        d["lng"] = "" if self.lng is None else self.lng
        return d


EDU_AJAX = f"{BASE}/educations/ajaxEduParticipation.do"


def fetch_education_page(sess: requests.Session, page: int) -> dict:
    data = {
        "pageIndex": str(page),
        "searchEduPlaCd": "",
        "searchText": "",
        "searchSttCd": "1",
        "searchEduTicket": "1",
        "eduTp": "06",
    }
    headers = {
        "Referer": f"{BASE}/educations/eduParticipation.do",
        "Origin": BASE,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    def call():
        r = sess.post(EDU_AJAX, data=data, headers=headers, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    return retry_request(call, label=f"edu page={page}")


def collect_programs(venues_by_code: dict) -> list[Program]:
    sess = http_session()
    prime_session(sess)
    today = date.today()
    out: list[Program] = []
    seen_ids = set()

    for page in range(1, 15):
        print(f"[MMCA 교육] page={page}", file=sys.stderr)
        try:
            j = fetch_education_page(sess, page)
        except Exception as e:
            print(f"  page {page} 영구 실패: {e}", file=sys.stderr)
            break
        items = j.get("eduList", [])
        if not items:
            break
        added = 0
        for x in items:
            edu_id = x.get("eduId", "")
            if edu_id in seen_ids:
                continue
            seen_ids.add(edu_id)
            code = x.get("eduPlaCd", "")
            venue = venues_by_code.get(code, {})
            start = normalize_date(x.get("eduStDt", ""))
            end = normalize_date(x.get("eduEdDt", ""))
            pid = hashlib.sha1(f"mmca-edu|{edu_id}".encode()).hexdigest()[:12]
            thumb = x.get("eduThumbImg") or ""
            if thumb and thumb.startswith("/"):
                thumb = urljoin(BASE, thumb)
            url = f"{BASE}/educations/educationsDetail.do?eduId={edu_id}"
            price_raw = (x.get("eduPrice") or "").strip()
            price = "무료" if price_raw in ("0", "0원", "") else (
                f"{price_raw}원" if price_raw.isdigit() else price_raw)
            ticket_y = x.get("eduTicketYn", "") == "Y"
            ticket_fin = x.get("eduTicketFinYn", "") == "Y"
            if ticket_y and not ticket_fin:
                app_status = "open"
            elif ticket_fin:
                app_status = "closed"
            else:
                app_status = "info_only"
            out.append(Program(
                id=pid, source="mmca",
                title=x.get("eduTitle", "").strip(),
                venue_raw=x.get("eduPlaNm", ""),
                venue_key=venue.get("venue_key", f"mmca_{code}"),
                venue_name=venue.get("venue_name", f"국립현대미술관 {x.get('eduPlaNm','')}"),
                venue_detail=x.get("eduPlaDtl", "").strip(),
                region=venue.get("region", "unknown"),
                address=venue.get("address", ""),
                lat=venue.get("lat"), lng=venue.get("lng"),
                start_date=start, end_date=end,
                time_range=x.get("eduTm", "").strip(),
                target_audience=x.get("eduTarget", "").strip(),
                target_category=x.get("eduBigNm", "").strip(),
                price=price,
                capacity=x.get("eduPersonCnt", "").strip(),
                application_status=app_status,
                url=url, thumbnail=thumb,
                status=compute_status(start, end, today),
                collected_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
            ))
            added += 1
        pi = j.get("paginationInfo", {})
        if page >= pi.get("totalPageCount", 1) or added == 0:
            break
        time.sleep(SLEEP)
    return out


# ============================================================
# 출력
# ============================================================

def build_grouped_exhibitions(exs: list[Exhibition], venues: list) -> dict:
    by_v: dict[str, list] = {}
    for e in exs:
        if e.status not in ("active", "upcoming"):
            continue
        by_v.setdefault(e.venue_key, []).append(e)
    venues_out = []
    for v in venues:
        lst = by_v.get(v["venue_key"], [])
        lst_sorted = sorted(lst, key=lambda e: (e.start_date or "9999"))
        venues_out.append({
            "venue_key": v["venue_key"],
            "venue_name": v["venue_name"],
            "region": v.get("region", "unknown"),
            "address": v.get("address", ""),
            "lat": v.get("lat"), "lng": v.get("lng"),
            "official_url": v.get("official_url", ""),
            "active_count": sum(1 for e in lst if e.status == "active"),
            "upcoming_count": sum(1 for e in lst if e.status == "upcoming"),
            "exhibitions": [
                {"id": e.id, "title": e.title, "artists": e.artists,
                 "start_date": e.start_date, "end_date": e.end_date,
                 "status": e.status, "thumbnail": e.thumbnail,
                 "url": e.url, "price": e.price}
                for e in lst_sorted
            ],
        })
    return {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "source": "mmca",
        "venue_count": sum(1 for v in venues_out if v["active_count"] + v["upcoming_count"] > 0),
        "venues": venues_out,
    }


def save_exhibitions(exs: list[Exhibition], venues: list, outdir: Path, today_iso: str) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    fields = list(Exhibition.__annotations__.keys())
    for name in [f"exhibitions_{today_iso}.csv", "exhibitions_latest.csv"]:
        with (outdir / name).open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for e in exs:
                w.writerow(e.for_csv())
    payload = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "source": "mmca",
        "count": len(exs),
        "exhibitions": [asdict(e) for e in exs],
    }
    for name in [f"exhibitions_{today_iso}.json", "exhibitions_latest.json"]:
        (outdir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    grouped = build_grouped_exhibitions(exs, venues)
    (outdir / "venues_with_exhibitions_latest.json").write_text(
        json.dumps(grouped, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def save_programs(progs: list[Program], outdir: Path, today_iso: str) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    fields = list(Program.__annotations__.keys())
    for name in [f"programs_{today_iso}.csv", "programs_latest.csv"]:
        with (outdir / name).open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for p in progs:
                w.writerow(p.for_csv())
    payload = {
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "source": "mmca",
        "count": len(progs),
        "programs": [asdict(p) for p in progs],
    }
    for name in [f"programs_{today_iso}.json", "programs_latest.json"]:
        (outdir / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# Main — 부분 실패해도 다른 카테고리는 살림
# ============================================================

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-exhibition", action="store_true")
    ap.add_argument("--skip-education", action="store_true")
    ap.add_argument("--venues", default=str(Path(__file__).parent / "venues.json"))
    ap.add_argument("--outdir", default=str(Path(__file__).parent / "data"))
    args = ap.parse_args()

    by_code, venues_meta = load_venues(Path(args.venues))
    today_iso = date.today().isoformat()
    any_success = False

    if not args.skip_exhibition:
        try:
            exs = collect_exhibitions(by_code)
            save_exhibitions(exs, venues_meta, Path(args.outdir), today_iso)
            print(f"\n[MMCA 전시] 총 {len(exs)}건", file=sys.stderr)
            if exs:
                any_success = True
        except Exception as e:
            print(f"\n[MMCA 전시] 수집 실패: {e}", file=sys.stderr)

    if not args.skip_education:
        try:
            progs = collect_programs(by_code)
            save_programs(progs, Path(args.outdir), today_iso)
            print(f"\n[MMCA 교육] 총 {len(progs)}건", file=sys.stderr)
            if progs:
                any_success = True
        except Exception as e:
            print(f"\n[MMCA 교육] 수집 실패: {e}", file=sys.stderr)

    # 둘 다 완전 실패면 exit 1, 하나라도 성공이면 0 (워크플로우 계속 진행)
    return 0 if any_success else 1


if __name__ == "__main__":
    sys.exit(main())
