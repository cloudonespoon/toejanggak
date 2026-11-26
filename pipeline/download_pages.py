"""입출차 API 페이지 범위를 받아 data/parking_raw/pXXXXX.csv 로 저장 (이어받기 가능).

사용법: py -u download_pages.py START END [ROWS]
"""
import csv
import os
import sys
import time

import collect

collect.KEY = collect.load_key()
start, end = int(sys.argv[1]), int(sys.argv[2])
rows = int(sys.argv[3]) if len(sys.argv) > 3 else collect.ROWS
outdir = os.path.join(collect.DATA, f"parking_raw_{rows}")
os.makedirs(outdir, exist_ok=True)
FIELDS = ["ID", "입구", "입차시간", "출구", "출차시간"]

t_all = time.time()
done = 0
# DEADLINE="2026-11-27 13:00" 처럼 주면 그 시각이 지나면 멈춤
DEADLINE = os.environ.get("DEADLINE")
deadline_ts = time.mktime(time.strptime(DEADLINE, "%Y-%m-%d %H:%M")) if DEADLINE else None
for p in range(start, end + 1):
    if deadline_ts and time.time() >= deadline_ts:
        print(f"마감 시각 {DEADLINE} 도달 → 중단", flush=True)
        sys.exit(3)
    path = os.path.join(outdir, f"p{p:05d}.csv")
    if os.path.exists(path):
        continue
    t0 = time.time()
    try:
        items, _, _ = collect.fetch(collect.API_PARKING, p, rows=rows, retries=3)
    except Exception as e:  # noqa: BLE001  (깊은 페이지 504 → 건너뛰고 다음 바퀴에 재시도)
        print(f"p{p} 실패: {e}", flush=True)
        time.sleep(30)
        continue
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for it in items:
            d = collect.kv(it.get("DESCRIPTION") or "")
            d["ID"] = it.get("LOCAL_ID", "")
            w.writerow(d)
    os.replace(tmp, path)
    done += 1
    months = sorted({(it.get("ISSUED_DATE") or "")[:7] for it in items})
    print(f"p{p} {len(items)}건 {months} {time.time() - t0:.1f}s (누적 {done}p, {time.time() - t_all:.0f}s)", flush=True)
    time.sleep(1.0)
