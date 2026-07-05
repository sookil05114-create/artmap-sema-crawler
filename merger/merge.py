"""
SeMA + MMCA + 승인된 제보 + 아트위크 통합 merger (v13 — 날짜 없는 전시 필터)

v13 변경점:
  - [정제] 날짜 없는 전시 (start_date, end_date 둘 다 빈값) 자동 필터
    "9월초 오픈" 같은 자유텍스트 전시는 사이트에 노출 안 함
  - [정제] 국제갤러리 박서보/김세은 케이스처럼 미확정 전시가 active로 잘못 표시되는 문제 방지

v12 변경점 (crawler_fix_prompt.md 대응):
  - [정제] venue 간 전역 dedup 추가 — 제목 정규화 완전 일치 + 기간 겹침 → 같은 전시로 병합
  - [정제] 같은 작가 + 기간 유사 → 제목 다르더라도 병합 (Living vs Living Living Artist 케이스)
  - [정제] 병합 시 정보 풍부도 우선순위: artists 있음 > thumbnail 있음 > 상세 URL(홈 아님) 있음 > 좌표 있음, 동점이면 제목 짧은 쪽
  - [정제] 제목에 3회 연속 동일 단어 감지 시 stderr 로그 (자동 수정 안 함 — 오탐 위험)

v11 변경점:
  - VENUE_KEY_ALIAS — 별도 공간을 상위 venue로 통합 (예: mmca_children → mmca_seoul)
  - 어린이미술관 전시는 국립현대미술관 서울본관 안에 통합 표시
  - 별칭 매핑된 venue 메타는 venues_out에서 제외

v22 변경점:
  - VENUE_KEY_ALIAS에 SeMA 분관 자동생성 키 5개 → 정식 키(bukseoul 등) 매핑 추가
  - dedup 대표 선정 시 source=='sema' 가산점 (+2000) — 분관 확정 소스 우선

v10 변경점:
  - venue_name이 날짜 패턴/숫자만이면 "(미분류 - 이동전시)"로 정상화
  - 폐관 venue 자동 필터 (DEAD_VENUE_KEYS 리스트)
  - 너무 짧거나 의미 없는 venue_name 정리

v9 변경점:
  - 같은 venue 내 중복 전시 dedup (gallery_crawler 듀얼 fetch 결과 보정)
  - 기준: 같은 artists + 기간 거의 일치 (start_date ±3일, end_date ±7일)
  - 또는 제목 normalize 후 한쪽이 다른쪽 포함 + 같은 기간
  - 정보 많은 쪽 유지 (artists 더 풍부, thumbnail 있음, url 있음)

v8 변경점:
  - venue 메타에 image_url(og:image) 전파
  - image_cache.json 폴백 지원 (gallery_crawler/image_cache.json)
  - venue.image_url이 없으면 image_cache에서 조회, 둘 다 없으면 빈 문자열

v7 변경점:
  - build_venues_grouped: lst가 비어 있어도 venue를 결과에 포함 (전시 정보만 빈 배열)
  - active_venues 필터 제거: 마커는 일단 다 찍히고, 프론트에서 필터 가능
  - art_week 소스 추가: ../art_week/exhibitions.json (선택, 있으면 로드)

입력:
    ../sema_crawler/data/exhibitions_latest.json
    ../mmca_crawler/data/exhibitions_latest.json
    ../mmca_crawler/data/programs_latest.json
    ../submissions/data/pending_queue.json
    ../gallery_crawler/venues.json
    ../gallery_crawler/coords_cache.json
    ../sema_crawler/venues.json, ../mmca_crawler/venues.json
    ../art_week/exhibitions.json   ← 신규 (v7, 선택)
출력:
    data/all_exhibitions_latest.json
    data/all_venues_latest.json
    data/all_venues_seoul_only.json    ★ 사이트 메인
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
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def compute_status(start: str, end: str, today: date) -> str:
    s, e = parse_iso(start), parse_iso(end)
    if not s or not e:
        return "unknown"
    if today < s:
        return "upcoming"
    if today > e:
        return "ended"
    return "active"


def resolve_coords_for_venue(vk: str, venue_meta: dict | None, coords_cache: dict) -> tuple[float | None, float | None, str]:
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
    lat = it.get("lat")
    lng = it.get("lng")
    addr = it.get("address", "")
    if lat is None or lng is None:
        vlat, vlng, vaddr = resolve_coords_for_venue(vk, venue, coords_cache)
        if lat is None:
            lat = vlat
        if lng is None:
            lng = vlng
        if not addr:
            addr = vaddr
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


def art_week_to_exhibition(it: dict, gv_by_key: dict, coords_cache: dict) -> dict | None:
    """art_week/exhibitions.json 의 1건을 통합 전시 스키마로 변환.
    active/upcoming만 받아들임.
    """
    today = date.today()
    title = it.get("title") or ""
    if not title:
        return None
    start = it.get("start_date") or ""
    end = it.get("end_date") or start
    status = compute_status(start, end, today) if start else "active"
    if status not in ("active", "upcoming"):
        return None
    vk = it.get("venue_key") or ""
    venue = gv_by_key.get(vk, {})
    if not venue and it.get("venue_name"):
        vn = it["venue_name"].replace(" ", "")
        for k, v in gv_by_key.items():
            if v.get("venue_name", "").replace(" ", "") == vn:
                venue = v
                vk = k
                break
    lat, lng, addr = resolve_coords_for_venue(vk, venue, coords_cache)
    return {
        "id": it.get("id") or hashlib.md5(f"{title}|{start}|{vk}".encode()).hexdigest()[:12],
        "source": "art_week",
        "title": title,
        "artists": it.get("artists", ""),
        "venue_raw": it.get("venue_name", ""),
        "venue_key": vk or "unknown_artweek",
        "venue_name": venue.get("venue_name") or it.get("venue_name", ""),
        "region": venue.get("region", "seoul"),
        "address": addr,
        "lat": lat,
        "lng": lng,
        "start_date": start,
        "end_date": end,
        "price": "",
        "url": it.get("url", ""),
        "thumbnail": it.get("thumbnail", ""),
        "status": status,
        "collected_at": now_iso(),
    }


def resolve_image_url(vk: str, venue_meta: dict, image_cache: dict) -> str:
    """venues.json의 image_url 우선, 없으면 image_cache, 없으면 빈 문자열."""
    if venue_meta:
        img = venue_meta.get("image_url")
        if img:
            return img
    cached = image_cache.get(vk, {})
    return cached.get("image_url", "") or ""


# ──────────────────────────────────────────────────────────────────
# v10: 폐관 venue 필터 + venue_name 정상화
# ──────────────────────────────────────────────────────────────────
# 폐관/이전 등 더 이상 운영하지 않는 venue_key 리스트
DEAD_VENUE_KEYS = {
    "bunker",      # SeMA 벙커 (영등포 여의대로 76) — 폐관
    "warehouse",   # SeMA 창고 (은평 통일로 684) — 폐관
}

# ──────────────────────────────────────────────────────────────────
# v11: venue_key 별칭 — 별도 공간을 상위 venue에 통합
# ──────────────────────────────────────────────────────────────────
# {별칭_key: 정본_key} — 별칭 venue의 전시는 정본 venue에 통합되고,
# 별칭 venue 자체는 venues_out에서 제외됨.
VENUE_KEY_ALIAS = {
    "mmca_children": "mmca_seoul",  # 어린이미술관 → 국립현대미술관 서울본관
    "mmca_140": "mmca_seoul",       # mmca_crawler fallback 키도 같이 처리
    # [v22] gallery_crawler가 자동 생성한 SeMA 분관 키 → sema_crawler 정식 키 통합
    #       (과거 데이터/캐시에 남아있을 수 있는 키의 안전망. gallery_crawler
    #        venues.json에서 SeMA 분관 자체를 제거했지만 이중 방어)
    "seongbuk_v_4d7461f17f": "bukseoul",           # 서울시립 북서울미술관
    "gwanak_v_4903d075a2": "namseoul",             # 서울시립 남서울미술관
    "geumcheon_v_75b99b9f74": "seoseoul",          # 서울시립 서서울미술관
    "dobong_v_dd23d120a3": "photosema",            # 서울시립 사진미술관
    "jongno_seoulsirip_misurakaibeu": "art_archive",  # 서울시립 미술아카이브
}


def resolve_venue_key(vk: str) -> str:
    """별칭이 있으면 정본 key 반환, 없으면 원본 그대로."""
    return VENUE_KEY_ALIAS.get(vk, vk)

# venue_name이 날짜 패턴인지 검사
import re as _re
_DATE_PATTERNS = [
    _re.compile(r"^\s*\d{4}[/.\-]\d{1,2}[/.\-]\d{1,2}\s*[~\-–—]\s*\d{4}[/.\-]\d{1,2}[/.\-]\d{1,2}\s*$"),  # 2026/06/15~2026/06/28
    _re.compile(r"^\s*\d{4}[/.\-]\d{1,2}[/.\-]\d{1,2}\s*$"),  # 2026/06/15
    _re.compile(r"^\s*\d{1,2}[/.\-]\d{1,2}[~\-–—]\d{1,2}[/.\-]\d{1,2}\s*$"),  # 6/15~6/28
    _re.compile(r"^[\d\s./\-:~,]+$"),  # 숫자/구두점만
]


def is_date_pattern(s: str) -> bool:
    """venue_name이 날짜/숫자 패턴인지"""
    if not s:
        return True
    s = s.strip()
    if not s:
        return True
    for pat in _DATE_PATTERNS:
        if pat.match(s):
            return True
    return False


def normalize_venue_name(name: str, fallback: str = "(미분류 - 이동전시)") -> str:
    """venue_name 정상화 — 날짜 패턴/빈값이면 fallback"""
    if not name or is_date_pattern(name):
        return fallback
    # 너무 길거나 줄바꿈 있으면 첫 줄만
    name = name.split("\n")[0].strip()
    if len(name) > 80:
        name = name[:80] + "…"
    return name


# ──────────────────────────────────────────────────────────────────
# v9: 전시 dedup
# ──────────────────────────────────────────────────────────────────
def _norm_artists(s: str) -> str:
    """작가명 정규화 — 구두점/공백 제거, 소문자, 정렬"""
    import re
    if not s:
        return ""
    # 쉼표/슬래시/&로 분리
    parts = re.split(r"[,/&]|및|and|with", s)
    norm_parts = []
    for p in parts:
        p = re.sub(r"[\s\-·().\"']", "", p).lower()
        if p:
            norm_parts.append(p)
    return "|".join(sorted(norm_parts))


def _norm_title(s: str) -> str:
    """제목 정규화"""
    import re
    if not s:
        return ""
    s = re.sub(r"[《》<>\"'\[\]【】（）()\s\-·:,.]+", "", s).lower()
    return s


# [정제] 문제 4번 대응 — 홈페이지 루트 URL(개별 전시 상세 아님) 판별
def _is_generic_home_url(url: str) -> bool:
    """전시 상세가 아닌 홈페이지 루트 URL 판별 (dedup 병합 우선순위에서 감점)"""
    import re
    if not url:
        return True
    # 쿼리·해시 있으면 상세 페이지 가능성 높음
    if "?" in url or "#" in url:
        return False
    # path가 없거나 '/'만 있으면 홈
    m = re.match(r"^https?://[^/]+(/.*)?$", url)
    if not m:
        return True
    path = m.group(1) or ""
    if path in ("", "/", "/main", "/index", "/index.html", "/home"):
        return True
    # 매우 짧은 path (e.g. "/kr")도 홈으로 취급
    if len(path.strip("/").split("/")) == 1 and len(path.strip("/")) <= 4:
        return True
    return False


# [정제] 문제 2번 대응 — 제목에 같은 단어 3회 이상 연속 반복 감지 (자동 수정 X, 로그만)
_REPEAT_RE = _re.compile(r"\b(\w+)(\s+\1){2,}\b", _re.IGNORECASE)


def _detect_title_repeat(title: str) -> str:
    """제목에 3회+ 연속 반복 단어 있으면 그 단어 반환, 없으면 빈문자열"""
    if not title:
        return ""
    m = _REPEAT_RE.search(title)
    return m.group(1) if m else ""


def _days_between(d1: str, d2: str) -> int:
    """ISO 날짜 두 개 차이 (절댓값). 파싱 실패 시 9999."""
    a, b = parse_iso(d1), parse_iso(d2)
    if not a or not b:
        return 9999
    return abs((a - b).days)


def _exhibition_score(e: dict) -> int:
    """정보량 점수 — dedup 시 더 풍부한 쪽 우선.
    [정제] 사용자 요청 우선순위: artists 있음 > thumbnail 있음 > 전시 상세 URL(홈 아님) 있음 > 좌표 있음.
    동점이면 제목이 더 간결한 쪽 (= 점수 낮게 = title 길이 감점)
    """
    s = 0
    # [v22] 공식 크롤러(sema) 우선 — SeMA 분관 전시는 sema_crawler가 분관 확정
    #       수집하므로, 타 소스(gallery_crawler 등)와 중복 시 sema 쪽을 대표로.
    if e.get("source") == "sema":
        s += 2000
    if e.get("artists"):
        s += 1000  # 최우선
    if e.get("thumbnail"):
        s += 500
    url = e.get("url", "")
    if url and not _is_generic_home_url(url):
        s += 300  # 전시 상세 URL만 가산
    elif url:
        s += 30   # 홈 URL은 약간만
    if e.get("lat") is not None and e.get("lng") is not None:
        s += 100
    if e.get("price"):
        s += 10
    # 동점이면 제목 짧은 쪽 우선 → 긴 제목은 감점
    s -= min(len(e.get("title", "")), 100)
    if e.get("price"):
        s += 5
    # 제목이 더 풍부한 쪽
    s += min(len(e.get("title", "")), 50)
    return s


def dedup_exhibitions_in_venue(exhibitions: list) -> tuple[list, int]:
    """같은 venue 내 중복 전시 합치기.
    조건:
      A) 같은 artists 정규화 + 시작일 ±3일 + 종료일 ±7일 → 같은 전시
      B) 같은 artists + 같은 기간 + 제목 정규화 시 한쪽이 다른쪽 포함 → 같은 전시
    """
    n = len(exhibitions)
    if n <= 1:
        return exhibitions, 0

    # 사전 계산
    items = []
    for e in exhibitions:
        items.append({
            "raw": e,
            "norm_artists": _norm_artists(e.get("artists", "")),
            "norm_title": _norm_title(e.get("title", "")),
            "start": e.get("start_date", ""),
            "end": e.get("end_date", ""),
            "score": _exhibition_score(e),
        })

    # Union-Find로 그룹화
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        for j in range(i + 1, n):
            a, b = items[i], items[j]
            same_artists = a["norm_artists"] and a["norm_artists"] == b["norm_artists"]
            ds = _days_between(a["start"], b["start"])
            de = _days_between(a["end"], b["end"])
            same_period_loose = ds <= 3 and de <= 7
            # 같은 작가일 때만 적용할 더 느슨한 기준 (전시 일정 변경/수정 흡수)
            same_period_artist_loose = ds <= 5 and de <= 14
            same_period_strict = ds == 0 and de == 0

            t_a, t_b = a["norm_title"], b["norm_title"]
            title_overlap = bool(t_a and t_b and (t_a in t_b or t_b in t_a))

            # 조건 A: 같은 작가 + 기간 유사 (보수)
            cond_A = same_artists and same_period_loose
            # 조건 A': 같은 작가 + 기간 비슷 (느슨, 동일 venue + 동일 작가는 거의 같은 전시)
            cond_A_artist = same_artists and same_period_artist_loose
            # 조건 B: 같은 작가 + 같은 기간 + 제목 포함 관계
            cond_B = same_artists and same_period_strict and title_overlap
            # 조건 C: 같은 기간 + 제목 포함 관계 (작가 정보 없을 때)
            no_artists = not a["norm_artists"] and not b["norm_artists"]
            cond_C = no_artists and same_period_strict and title_overlap

            if cond_A or cond_A_artist or cond_B or cond_C:
                union(i, j)

    # 그룹별 대표 선택 (score 최댓값)
    groups = {}
    for i in range(n):
        r = find(i)
        groups.setdefault(r, []).append(i)

    survivors = []
    duplicates = 0
    for root, idxs in groups.items():
        if len(idxs) == 1:
            survivors.append(items[idxs[0]]["raw"])
        else:
            # 최고 score 선택
            best_idx = max(idxs, key=lambda x: items[x]["score"])
            best = dict(items[best_idx]["raw"])
            # 보조 정보 보강: artists/title 더 긴 쪽 머지
            for x in idxs:
                if x == best_idx:
                    continue
                other = items[x]["raw"]
                if not best.get("artists") and other.get("artists"):
                    best["artists"] = other["artists"]
                if not best.get("thumbnail") and other.get("thumbnail"):
                    best["thumbnail"] = other["thumbnail"]
                if not best.get("url") and other.get("url"):
                    best["url"] = other["url"]
            survivors.append(best)
            duplicates += len(idxs) - 1

    # 시작일 순 재정렬
    survivors.sort(key=lambda e: e.get("start_date") or "9999")
    return survivors, duplicates


# ──────────────────────────────────────────────────────────────────
# v12: 전역 dedup (venue 간 중복 제거) + 데이터 정제
# ──────────────────────────────────────────────────────────────────

def dedup_exhibitions_global(exhibitions: list) -> tuple[list, int, list]:
    """[정제] venue 상관없이 전역 dedup.

    조건 (사용자 요청 A에 따름):
      1차: 제목 정규화 완전 일치 + 기간 겹침 (start ±14일 또는 end ±14일)
      2차: 같은 작가 + 시작일 ±5일 + 종료일 ±14일 (제목 달라도 같은 전시)
           (단, 작가 정보가 있을 때만 — 없으면 오판 위험)

    병합 시 정보 풍부한 쪽 유지 (artists > thumbnail > 상세 URL > 좌표, 동점이면 제목 짧은 쪽).
    병합된 venue_key는 대표(정보 풍부한 쪽)의 것을 따름.

    부수효과: 제목에 3회+ 연속 반복 단어 발견 시 warnings 리스트에 추가 (자동 수정 X).

    반환: (survivors, dup_count, warnings)
    """
    n = len(exhibitions)
    if n <= 1:
        return exhibitions, 0, []

    warnings = []

    # 사전 계산
    items = []
    for e in exhibitions:
        title = e.get("title", "")
        # [정제] 문제 2번 — 반복 단어 감지 (자동 수정 X, 로그만)
        repeat_word = _detect_title_repeat(title)
        if repeat_word:
            warnings.append({
                "title": title,
                "repeat_word": repeat_word,
                "venue_key": e.get("venue_key", ""),
                "id": e.get("id", ""),
            })
        items.append({
            "raw": e,
            "norm_artists": _norm_artists(e.get("artists", "")),
            "norm_title": _norm_title(title),
            "start": e.get("start_date", ""),
            "end": e.get("end_date", ""),
            "score": _exhibition_score(e),
        })

    # Union-Find
    parent = list(range(n))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        for j in range(i + 1, n):
            a, b = items[i], items[j]
            ds = _days_between(a["start"], b["start"])
            de = _days_between(a["end"], b["end"])

            # 1차: 제목 정규화 완전 일치 + 기간 겹침 (관대)
            same_title = bool(a["norm_title"]) and a["norm_title"] == b["norm_title"]
            period_overlap = ds <= 14 or de <= 14
            cond_1 = same_title and period_overlap

            # 2차: 같은 작가(있을 때만) + 기간 유사
            same_artists = bool(a["norm_artists"]) and a["norm_artists"] == b["norm_artists"]
            close_period = ds <= 5 and de <= 14
            cond_2 = same_artists and close_period

            if cond_1 or cond_2:
                union(i, j)

    # 그룹별 대표 선택
    groups = {}
    for i in range(n):
        r = find(i)
        groups.setdefault(r, []).append(i)

    survivors = []
    duplicates = 0
    for _, idxs in groups.items():
        if len(idxs) == 1:
            survivors.append(items[idxs[0]]["raw"])
        else:
            best_idx = max(idxs, key=lambda x: items[x]["score"])
            best = dict(items[best_idx]["raw"])
            # 부족한 필드는 다른 항목에서 보강
            for x in idxs:
                if x == best_idx:
                    continue
                other = items[x]["raw"]
                if not best.get("artists") and other.get("artists"):
                    best["artists"] = other["artists"]
                if not best.get("thumbnail") and other.get("thumbnail"):
                    best["thumbnail"] = other["thumbnail"]
                # URL: 홈이 아닌 상세 URL로 교체
                if _is_generic_home_url(best.get("url", "")) and other.get("url") and not _is_generic_home_url(other["url"]):
                    best["url"] = other["url"]
                elif not best.get("url") and other.get("url"):
                    best["url"] = other["url"]
            survivors.append(best)
            duplicates += len(idxs) - 1

    survivors.sort(key=lambda e: e.get("start_date") or "9999")
    return survivors, duplicates, warnings


def build_venues_grouped(exhibitions: list, all_venues_meta: list, coords_cache: dict, image_cache: dict) -> list:
    """전시 평면 리스트를 분관별로 그룹화.
    v9: 같은 venue 내 전시 dedup.
    v8: image_url 필드 추가.
    v7: 전시 없는 venue도 결과에 포함 (마커는 찍히고 전시 정보만 빈 배열).
    """
    # [정제] v13: status active/upcoming + 날짜 유효 + venue_key 별칭 적용
    active_exs = []
    aliased_count = 0
    dropped_no_date = 0
    for e in exhibitions:
        if e.get("status") not in ("active", "upcoming"):
            continue
        # [정제] v13: 날짜가 완전히 없는 전시는 제외 (미확정 전시 → 사이트에 잘못 표시 방지)
        start = e.get("start_date", "") or ""
        end = e.get("end_date", "") or ""
        if not start and not end:
            dropped_no_date += 1
            continue
        raw_vk = e.get("venue_key", "unknown")
        vk = resolve_venue_key(raw_vk)
        if vk != raw_vk:
            aliased_count += 1
        e2 = dict(e)
        e2["venue_key"] = vk
        active_exs.append(e2)
    if aliased_count:
        print(f"  [alias] 전시 {aliased_count}건 별칭 venue_key 통합", file=sys.stderr)
    if dropped_no_date:
        print(f"  [정제] 날짜 없는 전시 {dropped_no_date}건 제외 (미확정 → active/upcoming 잘못 표시 방지)", file=sys.stderr)

    # [정제] v12: 전역 dedup (venue 상관없이 제목+기간 또는 작가+기간 매치)
    active_exs, global_dups, title_warnings = dedup_exhibitions_global(active_exs)
    if global_dups:
        print(f"  [정제] 전역 dedup: 중복 전시 {global_dups}건 제거 (제목+기간 or 작가+기간)", file=sys.stderr)
    if title_warnings:
        print(f"  [정제] 제목 반복 단어 감지 {len(title_warnings)}건 (자동 수정 X, 검수 필요):", file=sys.stderr)
        for w in title_warnings[:10]:
            print(f"    - '{w['title'][:60]}' (반복: '{w['repeat_word']}', venue={w['venue_key']})", file=sys.stderr)
        if len(title_warnings) > 10:
            print(f"    ... 외 {len(title_warnings)-10}건", file=sys.stderr)

    # venue별 그룹화
    by_v: dict[str, list] = {}
    for e in active_exs:
        by_v.setdefault(e.get("venue_key", "unknown"), []).append(e)

    # v9: 같은 venue 내 중복 dedup
    total_dups = 0
    for vk in list(by_v.keys()):
        deduped, n_dups = dedup_exhibitions_in_venue(by_v[vk])
        by_v[vk] = deduped
        total_dups += n_dups
    if total_dups:
        print(f"  [dedup] 중복 전시 {total_dups}건 제거 (venue 내 같은 작가·기간)", file=sys.stderr)

    venues_out = []
    seen_keys = set()
    dead_filtered = 0
    alias_filtered = 0
    for v in all_venues_meta:
        vk = v["venue_key"]
        if vk in seen_keys:
            continue
        seen_keys.add(vk)
        # v10: 폐관 venue 필터
        if vk in DEAD_VENUE_KEYS:
            dead_filtered += 1
            continue
        # v11: 별칭 venue는 정본에 통합되므로 자체 venue로 출력하지 않음
        if vk in VENUE_KEY_ALIAS:
            alias_filtered += 1
            continue
        lst = by_v.get(vk, [])
        lst_sorted = sorted(lst, key=lambda e: e.get("start_date") or "9999")
        sample = lst_sorted[0] if lst_sorted else {}

        # 좌표 폴백 사다리
        lat = v.get("lat")
        lng = v.get("lng")
        addr = v.get("address", "")
        if lat is None or lng is None:
            cached = coords_cache.get(vk, {})
            if lat is None:
                lat = (sample.get("lat") if sample.get("lat") is not None else cached.get("lat"))
            if lng is None:
                lng = (sample.get("lng") if sample.get("lng") is not None else cached.get("lng"))
            if not addr:
                addr = sample.get("address") or cached.get("address", "")

        venues_out.append({
            "venue_key": vk,
            "venue_name": v.get("venue_name", ""),
            "region": v.get("region", "unknown"),
            "address": addr,
            "lat": lat,
            "lng": lng,
            "official_url": v.get("official_url", v.get("instagram_url", "")),
            "instagram_url": v.get("instagram_url", ""),
            "image_url": resolve_image_url(vk, v, image_cache),
            "category": v.get("category", ""),
            "active_count": sum(1 for e in lst if e.get("status") == "active"),
            "upcoming_count": sum(1 for e in lst if e.get("status") == "upcoming"),
            "exhibitions": [
                {"id": e["id"], "title": e["title"], "artists": e.get("artists", ""),
                 "start_date": e.get("start_date", ""), "end_date": e.get("end_date", ""),
                 "status": e.get("status"), "thumbnail": e.get("thumbnail", ""),
                 "url": e.get("url", ""), "price": e.get("price", ""),
                 "source": e.get("source", "")}
                for e in lst_sorted
            ],
        })

    # 메타에 없지만 전시에는 있는 venue (외부 협력 등)
    for vk, lst in by_v.items():
        if vk in seen_keys:
            continue
        seen_keys.add(vk)
        # v10: 폐관 venue 필터
        if vk in DEAD_VENUE_KEYS:
            dead_filtered += 1
            continue
        # v11: 별칭 venue는 정본에 통합되므로 자체 venue로 출력하지 않음 (이미 위에서 처리됐을 것)
        if vk in VENUE_KEY_ALIAS:
            alias_filtered += 1
            continue
        lst_sorted = sorted(lst, key=lambda e: e.get("start_date") or "9999")
        sample = lst[0]
        cached = coords_cache.get(vk, {})
        # v10: venue_name 정상화 (날짜 패턴 등 잘못된 이름 → "(미분류 - 이동전시)")
        raw_name = sample.get("venue_name") or sample.get("venue_raw") or ""
        normalized_name = normalize_venue_name(raw_name, fallback="(미분류 - 이동전시)")
        venues_out.append({
            "venue_key": vk,
            "venue_name": normalized_name,
            "region": sample.get("region", "unknown"),
            "address": sample.get("address") or cached.get("address", ""),
            "lat": sample.get("lat") if sample.get("lat") is not None else cached.get("lat"),
            "lng": sample.get("lng") if sample.get("lng") is not None else cached.get("lng"),
            "official_url": "",
            "instagram_url": "",
            "image_url": resolve_image_url(vk, {}, image_cache),
            "category": "기타",
            "active_count": sum(1 for e in lst if e.get("status") == "active"),
            "upcoming_count": sum(1 for e in lst if e.get("status") == "upcoming"),
            "exhibitions": [
                {"id": e["id"], "title": e["title"], "artists": e.get("artists", ""),
                 "start_date": e.get("start_date", ""), "end_date": e.get("end_date", ""),
                 "status": e.get("status"), "thumbnail": e.get("thumbnail", ""),
                 "url": e.get("url", ""), "price": e.get("price", ""),
                 "source": e.get("source", "")}
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
    # coords_cache는 두 가지 형식 모두 지원: {"venues": {...}} 또는 {key: {...}} 직접
    if coords_cache_doc and "venues" in coords_cache_doc:
        coords_cache = coords_cache_doc["venues"]
    else:
        coords_cache = coords_cache_doc or {}

    # 신규 v8: image_cache (og:image 캐시)
    image_cache_doc = load_json(ROOT / "gallery_crawler" / "image_cache.json")
    image_cache = image_cache_doc or {}

    # 신규 v7: art_week 데이터 (선택)
    art_week_doc = load_json(ROOT / "art_week" / "exhibitions.json")

    outdir = HERE / "data"
    outdir.mkdir(parents=True, exist_ok=True)

    # 1) 통합 전시 평면
    all_exs: list = []
    sources: list = []
    if sema_exh:
        all_exs.extend(sema_exh.get("exhibitions", []))
        sources.append("sema")
    if mmca_exh:
        all_exs.extend(mmca_exh.get("exhibitions", []))
        sources.append("mmca")

    gv_by_key = {}
    if gallery_venues_doc:
        for v in gallery_venues_doc.get("venues", []):
            gv_by_key[v["venue_key"]] = v

    # 승인된 제보 통합
    approved_count = 0
    if queue:
        for it in queue.get("items", []):
            ex = submission_to_exhibition(it, gv_by_key, coords_cache)
            if ex:
                if not any(e.get("id") == ex["id"] for e in all_exs):
                    all_exs.append(ex)
                    approved_count += 1
        if approved_count:
            sources.append("submissions")

    # 아트위크 통합 (v7)
    art_week_count = 0
    if art_week_doc:
        for it in art_week_doc.get("exhibitions", []):
            ex = art_week_to_exhibition(it, gv_by_key, coords_cache)
            if ex:
                if not any(e.get("id") == ex["id"] for e in all_exs):
                    all_exs.append(ex)
                    art_week_count += 1
        if art_week_count:
            sources.append("art_week")

    all_exs.sort(key=lambda e: e.get("start_date") or "9999")

    # 2) 전체 venues 메타 (dedup by venue_key)
    all_venues_meta: list = []
    seen = set()
    for doc in [sema_venues_doc, mmca_venues_doc, gallery_venues_doc]:
        if doc:
            for v in doc.get("venues", []):
                vk = v.get("venue_key")
                if vk and vk not in seen:
                    seen.add(vk)
                    all_venues_meta.append(v)

    # 3) 분관별 그룹화 (v8: image_url 포함, v7: 전시 없는 venue도 포함)
    venues_grouped = build_venues_grouped(all_exs, all_venues_meta, coords_cache, image_cache)

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
        "venue_count": len(venues_grouped),
        "venues": venues_grouped,
    }
    (outdir / "all_venues_latest.json").write_text(
        json.dumps(payload_venues, ensure_ascii=False, indent=2), encoding="utf-8")
    seoul_venues = [v for v in venues_grouped if v.get("region") == "seoul"]
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

    # 통계
    seoul_marker_with_xy = sum(1 for v in seoul_venues if v.get("lat") and v.get("lng"))
    seoul_marker_no_xy = len(seoul_venues) - seoul_marker_with_xy
    seoul_with_exh = sum(1 for v in seoul_venues if v["active_count"] + v["upcoming_count"] > 0)
    seoul_with_img = sum(1 for v in seoul_venues if v.get("image_url"))
    print(f"\n[Merger v13] 통합 완료", file=sys.stderr)
    print(f"  전시 평면 총 {len(all_exs)}건 (서울 {len(seoul_exs)}건)", file=sys.stderr)
    print(f"  분관 마커 {len(venues_grouped)}곳 (서울 {len(seoul_venues)}곳)", file=sys.stderr)
    print(f"    └ 좌표 있음 {seoul_marker_with_xy} / 좌표 없음 {seoul_marker_no_xy}", file=sys.stderr)
    print(f"    └ 전시 있음 {seoul_with_exh} / 전시 없음 {len(seoul_venues) - seoul_with_exh}", file=sys.stderr)
    print(f"    └ image_url 보유 {seoul_with_img} / 누락 {len(seoul_venues) - seoul_with_img}", file=sys.stderr)
    print(f"  승인된 제보 통합: {approved_count}건", file=sys.stderr)
    print(f"  아트위크 전시 통합: {art_week_count}건", file=sys.stderr)
    print(f"  좌표 캐시 적용: {len(coords_cache)}곳", file=sys.stderr)
    print(f"  이미지 캐시 적용: {len(image_cache)}곳", file=sys.stderr)
    print(f"  교육: {len(all_progs)}건", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
