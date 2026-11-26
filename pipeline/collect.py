"""올림픽공원 2025 입출차 / 연계 데이터 수집 스크립트 (표준 라이브러리만 사용).

사용법:
  py collect.py probe                 # 키·응답 형식 확인 (1페이지 5건)
  py collect.py linked                # 연계 데이터(API_CPM_009) 전체 → data/linked.csv
  py collect.py showdays              # linked.csv에서 공연 있는 날짜 목록 출력
  py collect.py parking 2025-11-08 2025-11-09 ...   # 지정 날짜의 입출차 원본 → data/parking_YYYY-MM-DD.csv

API 키는 상위 폴더의 .env 파일(KCISA_API_KEY=...)에서 읽습니다.
"""
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("TJ_DATA") or os.path.join(HERE, "data")
BASE = "https://api.kcisa.kr/openapi/{api}/request"
API_PARKING = "API_CPM_008"   # 올림픽공원 2025 입출차정보 (차량별)
API_LINKED = "API_CPM_009"    # 차량입출차·공연·날씨 연계 (시간대별)
ROWS = 1000


def load_key():
    """API별 키를 dict로 반환 (.env: KCISA_API_KEY=연계용, KCISA_PARKING_KEY=입출차용)."""
    env = {}
    for p in (os.path.join(HERE, "..", ".env"), os.path.join(HERE, ".env")):
        if os.path.exists(p):
            for line in open(p, encoding="utf-8-sig"):
                if "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    # GitHub Actions 등에서는 .env 대신 환경변수(Secrets)로 받음
    for k in ("KCISA_API_KEY", "KCISA_PARKING_KEY"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    if "KCISA_API_KEY" not in env:
        sys.exit("KCISA_API_KEY를 .env 파일에서 찾지 못했습니다.")
    return {API_LINKED: env["KCISA_API_KEY"],
            API_PARKING: env.get("KCISA_PARKING_KEY", env["KCISA_API_KEY"])}


KEY = {}


def fetch(api, page, rows=ROWS, retries=6):
    q = urllib.parse.urlencode({"serviceKey": KEY[api], "numOfRows": rows, "pageNo": page})
    url = BASE.format(api=api) + "?" + q
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return parse(r.read().decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            if i == retries - 1:
                raise
            print(f"  재시도 {i + 1} ({e})")
            time.sleep(3 * (i + 1))


def parse(text):
    """JSON 또는 XML 응답을 (items, totalCount, resultCode)로 변환."""
    t = text.strip()
    if t.startswith("{"):
        d = json.loads(t)
        resp = d.get("response", d)
        header = resp.get("header", {})
        body = resp.get("body", {})
        items = body.get("items", {})
        if isinstance(items, dict):
            items = items.get("item", [])
        if isinstance(items, dict):
            items = [items]
        return items or [], int(body.get("totalCount", 0) or 0), header.get("resultCode")
    root = ET.fromstring(t)
    code = root.findtext(".//resultCode")
    total = int(root.findtext(".//totalCount") or 0)
    items = [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("item")]
    return items, total, code


def kv(desc):
    """'주차대수:19,방문객:57, 기온:-3.4' → dict"""
    out = {}
    for part in re.split(r",\s*(?=[^,:]+:)", desc or ""):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def probe():
    for api in (API_LINKED, API_PARKING):
        try:
            items, total, code = fetch(api, 1, rows=5, retries=1)
        except Exception as e:  # noqa: BLE001
            print(f"[{api}] 실패: {e}")
            continue
        print(f"[{api}] resultCode={code} totalCount={total}")
        for it in items[:3]:
            print("  ", it)


def linked():
    os.makedirs(DATA, exist_ok=True)
    _, total, _ = fetch(API_LINKED, 1, rows=1)
    pages = (total + ROWS - 1) // ROWS
    rows, raw_all = [], []
    for p in range(1, pages + 1):
        items, _, _ = fetch(API_LINKED, p)
        raw_all.extend(items)
        for it in items:
            d = kv(it.get("TITLE") or "")
            d.update(kv(it.get("DESCRIPTION") or ""))
            d.update(kv(it.get("SUB_DESCRIPTION") or ""))
            d["시각"] = it.get("ISSUED_DATE", "")
            d["ID"] = it.get("LOCAL_ID", "")
            rows.append(d)
        print(f"  {p}/{pages}")
    json.dump(raw_all, open(os.path.join(DATA, "linked_raw.json"), "w", encoding="utf-8"), ensure_ascii=False)
    cols = ["ID", "시각"] + sorted({k for r in rows for k in r} - {"ID", "시각"})
    path = os.path.join(DATA, "linked.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"저장: {path} ({len(rows)}행, 전체 {total})")


def showdays():
    path = os.path.join(DATA, "linked.csv")
    days = {}
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        if r.get("공연명"):
            day = r["시각"][:10]
            n = int(float(r.get("공연관람객수") or 0))
            name, best = days.get(day, (r["공연명"], 0))
            days[day] = (r["공연명"], max(best, n))
    for day, (name, n) in sorted(days.items(), key=lambda x: -x[1][1]):
        print(f"{day}\t관람객 {n}\t{name}")


def page_date(page):
    items, _, _ = fetch(API_PARKING, page)
    if not items:
        return None, None
    ds = [it.get("ISSUED_DATE", "")[:10] for it in items]
    return max(ds), min(ds)  # 응답은 최신순 정렬로 보임


def find_first_page(target, total_pages):
    """target 날짜(YYYY-MM-DD) 데이터가 처음 나오는 페이지를 이분 탐색 (최신순 가정)."""
    lo, hi = 1, total_pages
    while lo < hi:
        mid = (lo + hi) // 2
        newest, oldest = page_date(mid)
        if oldest is None or oldest > target:
            lo = mid + 1
        else:
            hi = mid
    return lo


def parking(days):
    os.makedirs(DATA, exist_ok=True)
    _, total, _ = fetch(API_PARKING, 1, rows=1)
    total_pages = (total + ROWS - 1) // ROWS
    print(f"입출차 전체 {total}건, {total_pages}페이지")
    for day in days:
        start = find_first_page(day, total_pages)
        rows, p = [], start
        while p <= total_pages:
            items, _, _ = fetch(API_PARKING, p)
            ds = [it.get("ISSUED_DATE", "")[:10] for it in items]
            for it in items:
                if it.get("ISSUED_DATE", "")[:10] == day:
                    d = kv(it.get("DESCRIPTION", ""))
                    d["ID"] = it.get("LOCAL_ID", "")
                    rows.append(d)
            if not ds or min(ds) < day:
                break
            p += 1
        path = os.path.join(DATA, f"parking_{day}.csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["ID", "입구", "입차시간", "출구", "출차시간"], extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print(f"저장: {path} ({len(rows)}건, 페이지 {start}~{p})")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    KEY = load_key()
    cmd = sys.argv[1]
    if cmd == "probe":
        probe()
    elif cmd == "linked":
        linked()
    elif cmd == "showdays":
        showdays()
    elif cmd == "parking":
        parking(sys.argv[2:])
    else:
        sys.exit(__doc__)
