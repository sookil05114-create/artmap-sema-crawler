"""
서울공예박물관 (SeMoCA) 자동 수집기
====================================

소스: https://craftmuseum.seoul.go.kr
- /exhibit/plan/list/1          → 본관 기획전시 목록
- /exhibit/plan/view/{id}       → 본관 전시 상세
- /chimsm/exhibit/plan/list/1   → 어린이박물관 전시 목록
- /chimsm/exhibit/plan/view/{id}→ 어린이박물관 전시 상세
- /progrm/schedule/monthly      → 교육 프로그램 월별
- /progrm/view/{id}             → 교육 프로그램 상세

출력:
    data/exhibitions_latest.json           — 전시 평면 리스트 (본관+어린이)
    data/venues_with_exhibitions_latest.json — 분관별 그룹화
    data/programs_latest.json              — 교육 프로그램

SeMA·MMCA 크롤러와 같은 출력 스키마라 merger가 바로 통합 가능.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from datetime import datetime, date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HERE = Path(__file__).parent
DATA = HERE / "data"
DATA.mkdir(parents=True, exist_ok=True)

BASE = "https://craftmuseum.seoul.go.kr"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"}
TIMEOUT = 20
SLEEP = 1.0


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def parse_date(s: str):
    s = (s or "").strip()
    for fmt in ("%Y.%m.%d", "%Y-%m-%d", "%Y/%m/%d"):
        try: return datetime.strptime(s, fmt).date()
        except Exception: pass
    return None


def fmt_iso(d):
    return d.strftime("%Y-%m-%d") if d else ""


def compute_status(start, end, today):
    if not start or not end: return "unknown"
    if today < start: return "upcoming"
    if today > end: return "ended"
    return "active"


def prime_session(sess):
    """세션 쿠키 받기 위해 메인 페이지 1회 호출."""
    try:
        sess.get(f"{BASE}/main", timeout=TIMEOUT)
    except Exception:
        pass


def fetch(sess, url, retries=3):
    last_err = None
    for i in range(retries):
        try:
            r = sess.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last_err = e
            time.sleep(1 + i * 2)
    raise last_err


def absolute(url: str) -> str:
    if url.startswith("http"): return url
    if url.startswith("/"): return BASE + url
    return BASE + "/" + url


# ========== 전시 목록 + 상세 ==========

LIST_LINK_RE = re.compile(r"/exhibit/plan/view/(\d+)|/chimsm/exhibit/plan/view/(\d+)")
DATE_RANGE_RE = re.compile(
    r"(20\d{2}[.\-]\d{1,2}[.\-]\d{1,2})\s*[~\-]\s*(20\d{2}[.\-]\d{1,2}[.\-]\d{1,2})"
)


def parse_list_page(html: str, venue_key: str, view_prefix: str) -> list[dict]:
    """목록 페이지의 a 태그 텍스트에서 전시 항목 추출.

    텍스트 패턴 예시:
      '색유만개 : 권순형 기증특별전시2026.05.12 - 2026.08.02, 전시1동'
    """
    soup = BeautifulSoup(html, "html.parser")
    # 절대·상대 URL 둘 다 매칭하기 위해 path 부분만 사용
    view_path = view_prefix.replace(BASE, "")
    items: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if view_path not in href:
            continue
        text = a.get_text(" ", strip=True)
        # ID 추출
        m_id = re.search(r"/view/(\d+)", href)
        if not m_id: continue
        ex_id = m_id.group(1)
        if ex_id in items: continue
        # 일정 추출
        m_date = DATE_RANGE_RE.search(text)
        start_str = end_str = ""
        if m_date:
            start_str = m_date.group(1).replace("-", ".")
            end_str = m_date.group(2).replace("-", ".")
            # 제목 = 일정 이전 텍스트
            title = text[:m_date.start()].strip().rstrip(",")
        else:
            title = text.strip()
        # location 추출 (전시1동 등)
        m_loc = re.search(r"(전시\d?동|교육동|기획전시실|상설전시실)", text)
        location = m_loc.group(1) if m_loc else ""
        items[ex_id] = {
            "id_raw": ex_id,
            "href": absolute(href),
            "title": title,
            "start_str": start_str,
            "end_str": end_str,
            "location": location,
            "venue_key": venue_key,
        }
    return list(items.values())


OG_PROPS = ["og:title", "og:description", "og:image"]


def fetch_detail(sess, url: str) -> dict:
    """전시 상세 페이지에서 OG 메타·기간·썸네일 추출."""
    html = fetch(sess, url)
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for prop in OG_PROPS:
        m = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
        if m and m.get("content"):
            out[prop] = m["content"]
    # 기간을 본문에서 재확인 (목록에 없을 경우)
    body = soup.get_text(" ", strip=True)
    m_date = DATE_RANGE_RE.search(body)
    if m_date:
        out["body_start"] = m_date.group(1).replace("-", ".")
        out["body_end"] = m_date.group(2).replace("-", ".")
    return out


def build_exhibition(it: dict, detail: dict, venue: dict) -> dict:
    """list + detail 정보를 합쳐 표준 스키마."""
    today = date.today()
    # 일정 우선순위: list에서 추출한 게 있으면 우선, 없으면 상세 본문에서
    start_str = it.get("start_str") or detail.get("body_start", "")
    end_str = it.get("end_str") or detail.get("body_end", "")
    start_d = parse_date(start_str)
    end_d = parse_date(end_str)
    # title 정제: og:title 형태 "서울공예박물관의 ... 를 소개합니다." 에서 가운데 추출
    og_title = (detail.get("og:title") or "").strip()
    title = it.get("title", "")
    m = re.match(r"서울공예박물관의 (.+?)를 소개합니다\.?$", og_title)
    if m and not title:
        title = m.group(1).strip()
    elif m:
        # og 쪽이 더 풍성하면 그쪽 채택
        og_inner = m.group(1).strip()
        if len(og_inner) > len(title):
            title = og_inner
    # 썸네일
    thumb = (detail.get("og:image") or "").strip()
    if thumb and thumb.startswith("/"):
        thumb = BASE + thumb
    # 고유 id
    seed = f"craft|{venue['venue_key']}|{it['id_raw']}"
    eid = "craft_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
    return {
        "id": eid,
        "source": "seoul_craft_museum",
        "title": title,
        "artists": "",
        "venue_raw": venue["venue_name"] + (f" ({it['location']})" if it.get("location") else ""),
        "venue_key": venue["venue_key"],
        "venue_name": venue["venue_name"],
        "region": venue.get("region", "seoul"),
        "address": venue.get("address", ""),
        "lat": venue.get("lat"),
        "lng": venue.get("lng"),
        "start_date": fmt_iso(start_d),
        "end_date": fmt_iso(end_d),
        "price": "",
        "url": it["href"],
        "thumbnail": thumb,
        "status": compute_status(start_d, end_d, today),
        "collected_at": now_iso(),
        "description": (detail.get("og:description") or "").strip(),
    }


# ========== 교육 프로그램 ==========

PROGRAM_VIEW_RE = re.compile(r"/progrm/view/(\d+)")


def collect_program_ids(sess) -> list[str]:
    """월별 일정 페이지에서 프로그램 ID 추출."""
    html = fetch(sess, f"{BASE}/progrm/schedule/monthly")
    soup = BeautifulSoup(html, "html.parser")
    ids = set()
    for a in soup.find_all("a", href=True):
        m = PROGRAM_VIEW_RE.search(a["href"])
        if m: ids.add(m.group(1))
    return sorted(ids)


def fetch_program_detail(sess, pid: str) -> dict | None:
    url = f"{BASE}/progrm/view/{pid}"
    try:
        html = fetch(sess, url)
    except Exception as e:
        print(f"  [warn] program {pid} fetch 실패: {e}", file=sys.stderr)
        return None
    soup = BeautifulSoup(html, "html.parser")
    out = {"url": url, "id": pid}
    for prop in OG_PROPS:
        m = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
        if m and m.get("content"):
            out[prop] = m["content"]
    body = soup.get_text(" ", strip=True)
    m_date = DATE_RANGE_RE.search(body)
    if m_date:
        out["start"] = m_date.group(1).replace("-", ".")
        out["end"] = m_date.group(2).replace("-", ".")
    return out


def build_program(detail: dict) -> dict | None:
    today = date.today()
    title = (detail.get("og:title") or "").strip()
    m = re.match(r"서울공예박물관의 (.+?)를 소개합니다\.?$", title)
    if m: title = m.group(1).strip()
    if not title: return None
    start_d = parse_date(detail.get("start", ""))
    end_d = parse_date(detail.get("end", ""))
    thumb = (detail.get("og:image") or "").strip()
    if thumb and thumb.startswith("/"):
        thumb = BASE + thumb
    pid = detail["id"]
    return {
        "id": "craft_prog_" + pid,
        "source": "seoul_craft_museum",
        "title": title,
        "venue_key": "seoul_craft_museum",
        "venue_name": "서울공예박물관",
        "region": "seoul",
        "start_date": fmt_iso(start_d),
        "end_date": fmt_iso(end_d),
        "url": detail.get("url", ""),
        "thumbnail": thumb,
        "status": compute_status(start_d, end_d, today),
        "collected_at": now_iso(),
        "description": (detail.get("og:description") or "").strip(),
        "category": "education",
    }


# ========== 분관별 그룹화 ==========

def build_venues_grouped(exhibitions: list, venues_meta: list) -> list:
    """SeMA·MMCA와 동일한 venues_with_exhibitions 스키마."""
    by_v: dict[str, list] = {}
    for e in exhibitions:
        if e.get("status") not in ("active", "upcoming"):
            continue
        by_v.setdefault(e.get("venue_key", "unknown"), []).append(e)
    out = []
    for v in venues_meta:
        vk = v["venue_key"]
        lst = by_v.get(vk, [])
        if not lst: continue
        lst_sorted = sorted(lst, key=lambda e: e.get("start_date") or "9999")
        out.append({
            "venue_key": vk,
            "venue_name": v["venue_name"],
            "region": v["region"],
            "address": v["address"],
            "lat": v.get("lat"), "lng": v.get("lng"),
            "official_url": v.get("official_url", ""),
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
    return out


# ========== Main ==========

def main() -> int:
    venues_doc = json.loads((HERE / "venues.json").read_text(encoding="utf-8"))
    venues = venues_doc["venues"]

    sess = requests.Session()
    sess.headers.update(HEADERS)
    prime_session(sess)

    all_exs: list = []
    for venue in venues:
        list_url = venue.get("list_url") or venue.get("official_url")
        if not list_url:
            continue
        print(f"[craft] {venue['venue_name']} 목록 fetch — {list_url}", file=sys.stderr)
        try:
            html = fetch(sess, list_url)
        except Exception as e:
            print(f"  실패: {e}", file=sys.stderr)
            continue
        items = parse_list_page(html, venue["venue_key"], venue["view_url_prefix"])
        print(f"  목록 {len(items)}건", file=sys.stderr)
        for it in items:
            time.sleep(SLEEP)
            try:
                detail = fetch_detail(sess, it["href"])
            except Exception as e:
                print(f"  [warn] {it['title'][:30]!r} 상세 실패: {e}", file=sys.stderr)
                detail = {}
            ex = build_exhibition(it, detail, venue)
            all_exs.append(ex)
            print(f"    + {ex['title'][:40]!r} {ex['start_date']}~{ex['end_date']} [{ex['status']}]",
                  file=sys.stderr)

    # 교육 프로그램
    print(f"\n[craft] 교육 프로그램 수집", file=sys.stderr)
    all_progs: list = []
    try:
        pids = collect_program_ids(sess)
        print(f"  프로그램 ID {len(pids)}개", file=sys.stderr)
        for pid in pids:
            time.sleep(SLEEP)
            detail = fetch_program_detail(sess, pid)
            if not detail: continue
            prog = build_program(detail)
            if prog:
                all_progs.append(prog)
                print(f"    + [{prog['status']}] {prog['title'][:40]!r}", file=sys.stderr)
    except Exception as e:
        print(f"  교육 프로그램 수집 실패: {e}", file=sys.stderr)

    # 출력
    all_exs.sort(key=lambda e: e.get("start_date") or "9999")
    payload = {
        "generated_at": now_iso(),
        "source": "seoul_craft_museum",
        "count": len(all_exs),
        "exhibitions": all_exs,
    }
    (DATA / "exhibitions_latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    venues_grouped = build_venues_grouped(all_exs, venues)
    venues_payload = {
        "generated_at": now_iso(),
        "source": "seoul_craft_museum",
        "venue_count": len(venues_grouped),
        "venues": venues_grouped,
    }
    (DATA / "venues_with_exhibitions_latest.json").write_text(
        json.dumps(venues_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    all_progs.sort(key=lambda p: p.get("start_date") or "9999")
    progs_payload = {
        "generated_at": now_iso(),
        "source": "seoul_craft_museum",
        "count": len(all_progs),
        "programs": all_progs,
    }
    (DATA / "programs_latest.json").write_text(
        json.dumps(progs_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    active = sum(1 for e in all_exs if e["status"] == "active")
    upcoming = sum(1 for e in all_exs if e["status"] == "upcoming")
    print(f"\n[Craft Museum] 전시 {len(all_exs)}건 (진행 {active}, 예정 {upcoming}, "
          f"분관 {len(venues_grouped)}곳), 교육 {len(all_progs)}건", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
