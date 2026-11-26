"""입출차(차량별) + 연계(공연·관람객) 데이터를 분석해
  - web/data.js                                    (시연 웹용)
  - report/shows.json, model.json, stats.json      (기획서·그래프용)
을 만든다.

정의
  주 주차장  : 동2문·남2문·북2문 (서로 연결되어 있어 출구 선택 가능)
  추정 종료시각(t0): 공연일 출차 급증이 시작된 시각 (5분 이동합이 기준선+30%*(피크-기준선)을 처음 넘는 분)
  공연 후 출차   : t0 ~ t0+150분 동안 주 주차장 출차 - 평소 출차(기준선)
  퇴장 소요(T80) : t0부터 공연 후 출차의 80%가 빠져나갈 때까지 걸린 분
"""
import glob
import json
import os
import re

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
# 경로는 환경변수로 바꿀 수 있음 (GitHub Actions 자동 갱신용)
DATA = os.environ.get("TJ_DATA") or os.path.join(HERE, "data")
SITE = os.environ.get("TJ_SITE") or os.path.join(HERE, "web")
REP = os.environ.get("TJ_REPORT") or os.path.join(HERE, "report")
os.makedirs(REP, exist_ok=True)
MAIN = ["동2문", "남2문", "북2문"]
WIN_BEFORE, WIN_AFTER = 60, 150  # 분
BUCKETS = [(0, 5000), (5000, 10000), (10000, 15000), (15000, 100000)]  # 웹 '공연 규모' 선택지와 같음


# ---------- 1. 로드 ----------
def load_parking():
    cache = os.path.join(DATA, "parking_all.parquet")
    fs = sorted(glob.glob(os.path.join(DATA, "parking_raw_10000", "p*.csv")))
    if os.path.exists(cache) and os.path.getmtime(cache) > max(os.path.getmtime(f) for f in fs):
        return pd.read_parquet(cache)
    df = pd.concat([pd.read_csv(f, dtype=str) for f in fs], ignore_index=True)
    df = df.drop_duplicates("ID")
    df["in"] = pd.to_datetime(df["입차시간"], errors="coerce")
    df["out"] = pd.to_datetime(df["출차시간"], errors="coerce")
    df["ig"] = df["입구"].str[:3]
    df["og"] = df["출구"].str[:3]
    df["olane"] = df["출구"]
    df = df.dropna(subset=["in", "out"])
    df["seq"] = df["ID"].str.split("-").str[1].astype(int)
    df = df[["ID", "seq", "ig", "og", "olane", "in", "out"]]
    try:
        df.to_parquet(cache)
    except Exception:  # noqa: BLE001  (pyarrow 없으면 캐시 생략)
        pass
    return df


TOTAL_IDS = 2_411_225   # API 전체 건수 (ID B050-1 ~ B050-2411225)
TRUNC = 65_534          # 원본이 엑셀 행 제한(65,535-머리글)에서 잘린 달의 건수


def coverage(df):
    """받은 기록이 원본의 몇 %인지 달별로 계산해, 기록마다 가중치 w(=1/표본비율)를 붙인다.

    - ID는 달별로 연속 구간. 1~9월은 달 안에서 순서가 무작위 → 받은 기록 = 그 달의 무작위 표본.
    - 10~12월은 달 안에서 시간순 → 받은 날은 '완전', 못 받은 날은 '없음' (경계일은 제외).
    - 8·9·11·12월은 원본 자체가 65,534건에서 잘려 있음 → 8·9월은 다른 달의 하루 평균 건수로 보정.
    """
    df = df.copy()
    df["m"] = df["in"].dt.month
    s = np.sort(df["seq"].values)
    gi = np.where(np.diff(s) > 1000)[0]
    gaps = [(int(s[i]), int(s[i + 1])) for i in gi]  # (받은 마지막 ID, 다음 받은 ID)
    if s[-1] < TOTAL_IDS:
        gaps.append((int(s[-1]), TOTAL_IDS + 1))
    info = {}
    for m, g in df.groupby("m"):
        x = g["seq"]
        rho = np.corrcoef(pd.Series(x.values).rank(), pd.Series(g["in"].values.astype("int64")).rank())[0, 1]
        info[m] = {"lo": int(x.min()), "hi": int(x.max()), "have": int(len(g)), "ordered": bool(rho > 0.9),
                   "days": int(g["in"].dt.day.nunique())}
    ms = sorted(info)
    # 달 경계에 걸친 빈 구간은 두 달의 '하루당 기록 수'가 같아지도록 나눔
    for a, b in zip(ms, ms[1:]):
        for g0, g1 in gaps:
            if g0 == info[a]["hi"] and g1 == info[b]["lo"]:
                gap = g1 - g0 - 1
                da, db = info[a]["days"], info[b]["days"]
                sa = info[a]["hi"] - info[a]["lo"] + 1
                sb = info[b]["hi"] - info[b]["lo"] + 1
                xa = min(max((da * (sb + gap) - db * sa) / (da + db), 0), gap)
                info[a]["hi_est"] = info[a]["hi"] + xa
                info[b]["lo_est"] = info[b]["lo"] - (gap - xa)
    full_rates = []
    for m in ms:
        i = info[m]
        i["total_est"] = i.get("hi_est", i["hi"]) - i.get("lo_est", i["lo"]) + 1
        i["truncated"] = (i["hi"] - i["lo"] + 1) == TRUNC
        if not i["truncated"] and not i["ordered"] and "hi_est" not in i and "lo_est" not in i:
            full_rates.append(i["total_est"] / i["days"])
    day_rate = float(np.mean(full_rates))
    valid_days = set()
    for m in ms:
        i = info[m]
        if i["ordered"]:
            # 시간순 달: 빈 구간·잘린 끝에 닿은 날은 불완전 → 제외
            g = df[df["m"] == m]
            cut = set()
            for g0, g1 in gaps:
                for sid in (g0, g1):
                    hit = g[g["seq"] == sid]
                    if len(hit):
                        cut.add(hit["in"].iloc[0].normalize())
            if i["truncated"]:
                cut.add(g.loc[g["seq"].idxmax(), "in"].normalize())
            days = set(g["in"].dt.normalize().unique()) - cut
            valid_days |= days
            i["frac"] = 1.0
            i["complete_days"] = sorted(d.strftime("%m-%d") for d in days)
        else:
            if i["truncated"]:
                i["total_est"] = day_rate * i["days"]
            i["frac"] = min(1.0, i["have"] / i["total_est"])
            valid_days |= set(df.loc[df["m"] == m, "in"].dt.normalize().unique())
    df["w"] = df["m"].map({m: 1.0 / info[m]["frac"] for m in ms})
    return df.drop(columns="m"), info, valid_days


def load_shows():
    raw = json.load(open(os.path.join(DATA, "linked_raw.json"), encoding="utf-8"))
    rows = []
    for x in raw:
        m = re.match(r"공연명:(.*?)\s*,공연관람객수:(\d+)", x["TITLE"], re.S)
        if not m:
            continue
        rows.append({"t": pd.Timestamp(x["ISSUED_DATE"]), "name": m.group(1).strip(), "aud": int(m.group(2))})
    h = pd.DataFrame(rows)
    h = h[h["name"] != ""]
    h["date"] = h["t"].dt.normalize()

    def split_names(s):
        segs = [x.strip() for x in re.split(r"\s*,\s*", s.replace("\n", " ")) if x.strip()]
        out = []
        for x in segs:  # '정승환의 안녕, 겨울' 처럼 짧은 조각은 앞 이름에 붙임
            if out and len(x) <= 4:
                out[-1] = out[-1] + ", " + x
            else:
                out.append(x)
        return out

    g = h.groupby("date").agg(aud=("aud", "max"), h_first=("t", "min"), h_last=("t", "max"))
    names = {}
    for d, sub in h.sort_values("t").groupby("date"):
        seen = []
        for s in sub["name"]:
            for n in split_names(s):
                if n not in seen:
                    seen.append(n)
        names[d] = seen
    g["names"] = pd.Series(names)
    g["name"] = g["names"].apply(lambda l: l[0])
    return g.reset_index()


# ---------- 2. 분 단위 출차 시계열 ----------
def minute_series(df_main, start, end):
    idx = pd.date_range(start, end, freq="1min", inclusive="left")
    s = df_main[(df_main["out"] >= start) & (df_main["out"] < end)]
    k = s["out"].dt.floor("1min")
    tot = s["w"].groupby(k).sum().reindex(idx, fill_value=0.0)  # 표본 가중치로 원본 규모 추정
    per = {g: s.loc[s["og"] == g, "w"].groupby(k[s["og"] == g]).sum().reindex(idx, fill_value=0.0) for g in MAIN}
    return tot, per


def analyze_show(df_main, show, cars_in_before):
    d = show["date"]
    lo = show["h_first"] + pd.Timedelta(minutes=60)          # 공연 시작 1시간 후부터
    hi = show["h_last"] + pd.Timedelta(hours=3)               # 마지막 공연시간대 + 3시간까지
    tot, per = minute_series(df_main, lo - pd.Timedelta(minutes=120), hi + pd.Timedelta(minutes=WIN_AFTER))
    r5 = tot.rolling(5).sum()
    search = r5[(r5.index >= lo) & (r5.index <= hi)]
    if search.empty or search.max() < 25:
        return None
    t_peak = search.idxmax()
    peak = float(search.max())
    base_win = r5[(r5.index >= t_peak - pd.Timedelta(minutes=120)) & (r5.index <= t_peak - pd.Timedelta(minutes=40))]
    base = float(base_win.median()) if len(base_win) else 0.0
    thr = base + 0.3 * (peak - base)
    pre = r5[(r5.index <= t_peak) & (r5.index >= t_peak - pd.Timedelta(minutes=60))]
    below = pre[pre < thr]
    t0 = (below.index[-1] + pd.Timedelta(minutes=1)) if len(below) else t_peak - pd.Timedelta(minutes=10)
    t0 = t0 - pd.Timedelta(minutes=4)  # 5분 이동합의 시작점 보정
    if t0.hour < 15:  # 종일 페스티벌 등: 오전·이른 오후 급증은 '공연 종료'로 보기 어려움
        return None
    base_rate = base / 5.0

    after = tot[(tot.index >= t0) & (tot.index < t0 + pd.Timedelta(minutes=WIN_AFTER))]
    excess = (after - base_rate).clip(lower=0)
    total_excess = float(excess.sum())
    if total_excess < 100:
        return None
    n_sampled = int(((df_main["out"] >= t0) & (df_main["out"] < t0 + pd.Timedelta(minutes=WIN_AFTER))).sum())
    if n_sampled < 150:  # 표본이 너무 적으면 곡선이 흔들려 제외
        return None
    cum = excess.cumsum() / total_excess
    t50 = int((cum >= 0.5).idxmax().value - t0.value) // 60_000_000_000
    t80 = int((cum >= 0.8).idxmax().value - t0.value) // 60_000_000_000
    t90 = int((cum >= 0.9).idxmax().value - t0.value) // 60_000_000_000

    # 출구별
    gates = {}
    for g in MAIN:
        a = per[g][(per[g].index >= t0) & (per[g].index < t0 + pd.Timedelta(minutes=WIN_AFTER))]
        n = int(round(a.sum()))
        if n == 0:
            gates[g] = {"n": 0}
            continue
        c = a.cumsum() / n
        r5g = a.rolling(5).sum()
        gates[g] = {
            "n": n,
            "share": None,
            "peak5": int(round(r5g.max())),
            "t80": int((c >= 0.8).idxmax().value - t0.value) // 60_000_000_000,
        }
    s = sum(v["n"] for v in gates.values()) or 1
    for g in MAIN:
        gates[g]["share"] = round(gates[g]["n"] / s, 3)

    # 공연 전 입차 → 종료 후 출차 차량의 '종료 후 출차까지 걸린 분' (출구별 중앙값)
    cars = cars_in_before[(cars_in_before["in"] < show["h_last"]) & (cars_in_before["in"] >= d)
                          & (cars_in_before["out"] >= t0) & (cars_in_before["out"] < t0 + pd.Timedelta(minutes=WIN_AFTER))]
    wait = {}
    for g in MAIN:
        w = (cars[cars["og"] == g]["out"] - t0).dt.total_seconds() / 60
        wait[g] = {"median": round(float(w.median()), 1) if len(w) else None,
                   "p80": round(float(w.quantile(0.8)), 1) if len(w) else None, "n": int(len(w))}

    # 들어온 문(≈주차 위치)별로: 어느 출구로 나갔고, 종료 후 몇 분 걸렸는지 → '내 주차 위치' 맞춤 추천
    entry = {}
    for ig in MAIN:
        ci = cars[cars["ig"] == ig]
        if len(ci) < 20:
            continue
        out = {}
        for og in MAIN:
            w = (ci[ci["og"] == og]["out"] - t0).dt.total_seconds() / 60
            out[og] = {"share": round(len(w) / len(ci), 3),
                       "median": round(float(w.median()), 1) if len(w) >= 8 else None, "n": int(len(w))}
        entry[ig] = {"n": int(len(ci)), "out": out}

    # 5분 단위 곡선 (t0-60 ~ t0+150)
    s_idx = pd.date_range(t0 - pd.Timedelta(minutes=WIN_BEFORE), t0 + pd.Timedelta(minutes=WIN_AFTER), freq="5min", inclusive="left")
    def bin5(series):
        sub = series[(series.index >= s_idx[0]) & (series.index < s_idx[-1] + pd.Timedelta(minutes=5))]
        return sub.resample("5min", origin=s_idx[0]).sum().reindex(s_idx, fill_value=0).round().astype(int).tolist()
    curve = {"total": bin5(tot), **{g: bin5(per[g]) for g in MAIN}}

    # 추천 출발 시각: 전체 출차율이 피크의 35% 이하로 떨어지는 첫 시점(피크 이후)
    after5 = pd.Series(curve["total"], index=s_idx)
    i0 = WIN_BEFORE // 5  # t0 위치
    pk_i = i0 + int(np.argmax(after5.values[i0:]))
    pk = after5.values[pk_i]
    # 잠깐 줄었다가 다시 몰리는 날(두 번째 물결)이 있어, 15분(3칸) 연속으로 낮게 유지될 때를 '한산'으로 봄
    thr_c = max(0.35 * pk, base)
    v5 = after5.values
    calm = next((i for i in range(pk_i, len(v5)) if all(v <= thr_c for v in v5[i:i + 3])), len(v5) - 1)
    calm_min = int((s_idx[calm] - t0).total_seconds() // 60)

    return {
        "date": d.strftime("%Y-%m-%d"),
        "weekday": "월화수목금토일"[d.weekday()],
        "name": show["name"],
        "names": show["names"],
        "aud": int(show["aud"]),
        "frac": round(float(show["frac"]), 3),   # 이 날 기록 중 실제로 받은 비율(1=전수)
        "n_sampled": n_sampled,
        "show_hours": [show["h_first"].hour, show["h_last"].hour],
        "t0": t0.strftime("%H:%M"),
        "t0_iso": t0.isoformat(),
        "peak5": int(peak),
        "base_per_min": round(base_rate, 2),
        "excess": int(total_excess),
        "t50": t50, "t80": t80, "t90": t90,
        "calm_after": calm_min,
        "gates": gates,
        "wait": wait,
        "entry": entry,
        "curve_start": s_idx[0].strftime("%H:%M"),
        "curve": curve,
    }


def lane_capacity(df_main, show_days):
    """출구 차로별 '1분 최대 처리량' (전수 기록이 있는 공연일의 분당 출차 99퍼센타일)"""
    sd = set(show_days)
    s = df_main[df_main["out"].dt.normalize().isin(sd) & (df_main["w"] == 1.0)]
    m = s.groupby([s["olane"], s["out"].dt.floor("1min")]).size()
    return {lane: float(v.quantile(0.99)) for lane, v in m.groupby(level=0)}


def wmed(a):
    """웹(app.js)과 같은 중앙값: 정렬 후 가운데(짝수면 위쪽) 값"""
    a = sorted(a)
    return a[len(a) // 2] if a else None


def bucket_of(aud):
    return next(i for i, (lo, hi) in enumerate(BUCKETS) if lo <= aud < hi)


def is_weekend(r):
    return r["weekday"] in ("토", "일")


def pool_for(r, results, exclude=True):
    """웹 '지금 퇴장'과 같은 규칙: 같은 규모 구간·같은 요일 구분(3회 미만이면 규모만)"""
    b = bucket_of(r["aud"])
    others = [x for x in results if (x is not r or not exclude) and bucket_of(x["aud"]) == b]
    same = [x for x in others if is_weekend(x) == is_weekend(r)]
    return same if len(same) >= 3 else others


def best_gate_pool(pool):
    meds = {}
    for g in MAIN:
        ws = [x["wait"][g]["median"] for x in pool if x["wait"][g]["median"] is not None]
        if len(ws) >= 3:
            meds[g] = wmed(ws)
    return min(meds, key=meds.get) if meds else None


def best_gate_actual(r):
    c = {g: r["wait"][g]["median"] for g in MAIN if r["wait"][g]["median"] is not None and r["wait"][g]["n"] >= 30}
    return min(c, key=c.get) if c else None


SPLIT_WITHIN = 5  # 가장 빠른 출구와 중앙값 차이가 5분 이내인 출구끼리 나눠 안내


def split_plan(waits):
    """{출구: 종료 후 출차 시간 중앙값} → {출구: 배정 비율}.
    모두에게 한 출구만 알려주면 그 출구가 다시 막히므로, 가장 빠른 출구와 5분 이내로 비슷한 출구끼리
    '가장 느린 출구 대비 아끼는 시간'에 비례해 나눠 배정한다. (app.js splitPlan과 같은 규칙)"""
    w = {g: v for g, v in waits.items() if v is not None}
    if not w:
        return {}
    best, worst = min(w.values()), max(w.values())
    cand = {g: v for g, v in w.items() if v <= best + SPLIT_WITHIN}
    if len(cand) == 1 or worst == best:
        return {min(cand, key=cand.get): 1.0}
    gain = {g: worst - v for g, v in cand.items()}
    s = sum(gain.values())
    if s <= 0:
        return {min(cand, key=cand.get): 1.0}
    return {g: round(v / s, 3) for g, v in gain.items() if v > 0}


def entry_waits(pool, ig):
    out = {}
    for og in MAIN:
        ws = [x["entry"][ig]["out"][og]["median"] for x in pool
              if ig in x.get("entry", {}) and x["entry"][ig]["out"][og]["median"] is not None]
        out[og] = wmed(ws) if len(ws) >= 3 else None
    return out


def backtest(results):
    """한 공연씩 빼고(leave-one-out) 나머지 2025 공연으로 '지금 퇴장' 안내를 만들어 실제와 비교"""
    i0 = WIN_BEFORE // 5
    rows, split_rows = [], []
    for r in results:
        pool = pool_for(r, results)
        if len(pool) < 3:
            continue
        calm_p = wmed([x["calm_after"] for x in pool])
        t80_p = wmed([x["t80"] for x in pool])
        shape = np.mean([np.array(x["curve"]["total"]) / max(1, x["excess"]) for x in pool], axis=0)
        peak_p = int(np.argmax(shape[i0:])) * 5
        tot = np.array(r["curve"]["total"])
        peak_a = int(np.argmax(tot[i0:])) * 5
        pb, ab = best_gate_pool(pool), best_gate_actual(r)
        busiest = max(MAIN, key=lambda g: r["gates"][g]["share"])
        save = None
        if pb and r["wait"][pb]["median"] is not None and r["wait"][busiest]["median"] is not None \
                and r["wait"][pb]["n"] >= 30 and r["wait"][busiest]["n"] >= 30:
            save = r["wait"][busiest]["median"] - r["wait"][pb]["median"]
        idx = i0 + int(round(calm_p / 5))
        level = float(tot[idx] / max(1, tot[i0:].max())) if idx < len(tot) else 0.0
        base_calm = wmed([x["calm_after"] for x in results if x is not r])
        rows.append({"date": r["date"], "calm_err": calm_p - r["calm_after"], "calm_base_err": base_calm - r["calm_after"],
                     "t80_err": t80_p - r["t80"], "peak_err": peak_p - peak_a, "hit": (pb == ab) if (pb and ab) else None,
                     "busiest_is_best": (busiest == ab) if ab else None, "save": save, "level": level})
        # 들어온 문별 분산 안내: 안내대로 나눠 나갔다면 vs 그 문으로 들어온 차가 가장 많이 쓴 출구
        for ig in MAIN:
            e = r.get("entry", {}).get(ig)
            if not e:
                continue
            plan = split_plan(entry_waits(pool, ig))
            act = {og: v["median"] for og, v in e["out"].items() if v["median"] is not None}
            if not plan or any(g not in act for g in plan):
                continue
            habit = max(e["out"], key=lambda og: e["out"][og]["share"])
            if habit not in act:
                continue
            exp = sum(p * act[g] for g, p in plan.items())
            split_rows.append({"save": act[habit] - exp, "multi": len(plan) > 1})
    B = pd.DataFrame(rows)
    SP = pd.DataFrame(split_rows)
    hits = B["hit"].dropna()
    bb = B["busiest_is_best"].dropna()
    sv = B["save"].dropna()
    return {
        "n": int(len(B)),
        "calm_mae": float(B["calm_err"].abs().median()),
        "calm_within15": round(float((B["calm_err"].abs() <= 15).mean()), 3),
        "calm_base_mae": float(B["calm_base_err"].abs().median()),
        "t80_mae": float(B["t80_err"].abs().median()),
        "peak_mae": float(B["peak_err"].abs().median()),
        "peak_within10": round(float((B["peak_err"].abs() <= 10).mean()), 3),
        "gate_hit": round(float(hits.mean()), 3), "gate_n": int(len(hits)),
        "busiest_hit": round(float(bb.mean()), 3),
        "save_median": float(sv.median()) if len(sv) else None, "save_pos": round(float((sv > 0).mean()), 3) if len(sv) else None,
        "save_n": int(len(sv)),
        "level_median": round(float(B["level"].median()), 3),
        "split_n": int(len(SP)),
        "split_save_median": round(float(SP["save"].median()), 1) if len(SP) else None,
        "split_save_pos": round(float((SP["save"] > 0).mean()), 3) if len(SP) else None,
        "split_multi": round(float(SP["multi"].mean()), 3) if len(SP) else None,
    }


def gate_capacity(cap_lane):
    """출구별 1분 처리량 = 그 출구 차로들의 1분 최대 처리량 합"""
    return {g: round(sum(v for k, v in cap_lane.items() if k[:3] == g), 1) for g in MAIN}


def ops_table(results):
    """기관용: 공연 규모·요일별 퇴장 혼잡 요약 (피크·한산 시각, 출구별 비율과 종료 후 출차 시간)"""
    i0 = WIN_BEFORE // 5
    out = []
    for b, (lo, hi) in enumerate(BUCKETS):
        for we in (True, False):
            sel = [r for r in results if bucket_of(r["aud"]) == b and is_weekend(r) == we]
            if len(sel) < 3:
                continue
            peak_off = wmed([int(np.argmax(r["curve"]["total"][i0:])) * 5 for r in sel])
            wait = {}
            for g in MAIN:
                ws = [r["wait"][g]["median"] for r in sel if r["wait"][g]["median"] is not None]
                wait[g] = round(float(np.median(ws)), 1) if ws else None
            out.append({"bucket": b, "lo": lo, "hi": hi, "weekend": we, "n": len(sel),
                        "excess": wmed([r["excess"] for r in sel]), "peak_after": peak_off,
                        "t80": wmed([r["t80"] for r in sel]), "calm": wmed([r["calm_after"] for r in sel]),
                        "share": {g: round(float(np.mean([r["gates"][g]["share"] for r in sel])), 3) for g in MAIN},
                        "wait": wait})
    return out


def main():
    df = load_parking()
    df, cov, valid_days = coverage(df)
    print("차량 기록", len(df), "기간", df["in"].min(), "~", df["in"].max())
    for m, i in cov.items():
        print(f"  {m:2d}월 받은 {i['have']:7d} / 추정 원본 {i['total_est']:9.0f}  표본비율 {i['frac']:.3f}"
              f"{' 시간순' if i['ordered'] else ''}{' 원본잘림' if i['truncated'] else ''}"
              f"{' 완전한 날 ' + ','.join(i['complete_days']) if i.get('complete_days') else ''}")
    shows = load_shows()
    print("공연일", len(shows))
    n_linked = len(shows)
    shows = shows[shows["date"].isin(valid_days)].copy()
    shows["frac"] = shows["date"].dt.month.map({m: i["frac"] for m, i in cov.items()})
    print("분석 가능한 공연일(기록 있는 날)", len(shows))
    main_df = df[df["og"].isin(MAIN)]

    results = []
    for _, sh in shows.iterrows():
        r = analyze_show(main_df, sh, main_df)
        if r:
            results.append(r)
    print("분석된 공연일", len(results))

    # 공연 없는 날(같은 요일) 시간대별 평균 출차 vs 공연일
    df_main_days = main_df.assign(day=main_df["out"].dt.normalize(), hour=main_df["out"].dt.hour)
    df_main_days = df_main_days[df_main_days["day"].isin(valid_days)]
    show_dates = set(pd.to_datetime([r["date"] for r in results]))
    big_dates = set(pd.to_datetime([r["date"] for r in results if r["aud"] >= 10000]))
    all_days = pd.Series(sorted(df_main_days["day"].unique()))
    all_days = all_days[all_days.dt.year == 2025]
    # 비교군: 공연이 없거나 공원 전체 관람객 5천 명 미만인 날
    busy_dates = set(pd.to_datetime(load_shows().query("aud >= 5000")["date"]))
    nonshow = [d for d in all_days if d not in busy_dates]
    hourly = df_main_days.groupby(["day", "hour"])["w"].sum().unstack(fill_value=0)
    hourly = hourly.reindex(columns=range(24), fill_value=0)
    def avg(days):
        days = [d for d in days if d in hourly.index]
        return hourly.loc[days].mean().round(1).tolist() if days else [0] * 24
    wk = lambda ds, w: [d for d in ds if (d.weekday() >= 5) == w]  # noqa: E731
    hourly_cmp = {
        "big_show_weekend": avg(wk(big_dates, True)),
        "nonshow_weekend": avg(wk(nonshow, True)),
        "big_show_weekday": avg(wk(big_dates, False)),
        "nonshow_weekday": avg(wk(nonshow, False)),
        "n": {"big_show_weekend": len(wk(big_dates, True)), "nonshow_weekend": len(wk(nonshow, True)),
              "big_show_weekday": len(wk(big_dates, False)), "nonshow_weekday": len(wk(nonshow, False))},
    }

    cap = lane_capacity(main_df, show_dates)

    # 예측 모델: 관람객 수 → 공연 후 출차대수, T80 (선형회귀, 1만명 이상/이하 모두)
    R = pd.DataFrame([{k: r[k] for k in ("aud", "excess", "t80", "t50", "calm_after", "weekday")} for r in results])
    R["weekend"] = R["weekday"].isin(["토", "일"]).astype(int)
    def fit(y):
        X = np.c_[np.ones(len(R)), R["aud"] / 1000.0, R["weekend"]]
        coef, *_ = np.linalg.lstsq(X, R[y].values, rcond=None)
        pred = X @ coef
        ss = ((R[y] - pred) ** 2).sum(); st = ((R[y] - R[y].mean()) ** 2).sum()
        return {"intercept": float(coef[0]), "per_1000": float(coef[1]), "weekend": float(coef[2]),
                "r2": float(1 - ss / st) if st else 0.0}
    model = {"excess": fit("excess"), "t80": fit("t80"), "calm_after": fit("calm_after")}
    # 정규화 평균 곡선 (규모 구간별), 출구 분담률 평균
    buckets = [(0, 5000), (5000, 10000), (10000, 15000), (15000, 100000)]
    shapes = []
    for lo, hi in buckets:
        sel = [r for r in results if lo <= r["aud"] < hi]
        if not sel:
            continue
        arr = {k: np.mean([np.array(r["curve"][k]) / max(1, r["excess"]) for r in sel], axis=0).round(5).tolist()
               for k in ["total"] + MAIN}
        shapes.append({"lo": lo, "hi": hi, "n": len(sel), "shape": arr,
                       "excess": int(np.median([r["excess"] for r in sel])),
                       "t80": int(np.median([r["t80"] for r in sel])),
                       "calm": int(np.median([r["calm_after"] for r in sel])),
                       "peak5": int(np.median([r["peak5"] for r in sel])),
                       "share": {g: round(float(np.mean([r["gates"][g]["share"] for r in sel])), 3) for g in MAIN},
                       "wait_median": {g: round(float(np.nanmedian([r["wait"][g]["median"] or np.nan for r in sel])), 1) for g in MAIN}})
    model["shapes"] = shapes
    model["capacity_per_min"] = {k: round(v, 1) for k, v in cap.items() if k[:3] in MAIN}
    model["gate_capacity"] = gate_capacity(model["capacity_per_min"])
    model["n_shows"] = len(results)
    model["backtest"] = backtest(results)
    model["ops"] = ops_table(results)
    print("백테스트", json.dumps(model["backtest"], ensure_ascii=False))
    print("출구 처리량(대/분)", model["gate_capacity"])
    for o in model["ops"]:
        print("  운영", o["lo"], o["hi"], "주말" if o["weekend"] else "평일", "n", o["n"], "피크", o["peak_after"],
              "한산", o["calm"], "대기", o["wait"], "비율", o["share"])

    # 출입 교차(들어온 문과 다른 문으로 나간 비율)
    md = df[df["ig"].isin(MAIN) & df["og"].isin(MAIN)]
    cross = float(((md["ig"] != md["og"]) * md["w"]).sum() / md["w"].sum())

    stats = {
        "records": int(len(df)),
        "period": [str(df["in"].min()), str(df["in"].max())],
        "main_records": int(len(main_df)),
        "show_days_linked": int(n_linked),
        "show_days_with_parking": int(len(shows)),
        "show_days_analyzed": len(results),
        "cross_exit_ratio": round(cross, 3),
        "hourly_cmp": hourly_cmp,
        "model": {k: model[k] for k in ("excess", "t80", "calm_after")},
        "capacity_per_min": model["capacity_per_min"],
        "top_shows": sorted(results, key=lambda r: -r["aud"])[:10],
        "coverage": {int(m): {k: (round(v, 3) if isinstance(v, float) else v) for k, v in i.items()} for m, i in cov.items()},
        "valid_days": len(valid_days),
        "est_total": int(sum(i["total_est"] for i in cov.values())),
    }
    # 시연 웹용 (file:// 에서도 열리도록 JS로)
    gate_tot = md.groupby("og")["w"].sum()
    insight = {
        "records": int(len(df)),
        "main_records": int(len(main_df)),
        "show_days": len(results),
        "valid_days": len([d for d in valid_days if d.year == 2025]),
        "cross_exit_ratio": round(cross, 3),
        "hourly_cmp": hourly_cmp,
        "avg_t80": round(float(np.mean([r["t80"] for r in results])), 1),
        "avg_calm": round(float(np.mean([r["calm_after"] for r in results])), 1),
        "big_gate_share": {g: round(float(np.mean([r["gates"][g]["share"] for r in results if r["aud"] >= 10000])), 3) for g in MAIN},
        "big_wait_median": {g: round(float(np.nanmedian([r["wait"][g]["median"] or np.nan for r in results if r["aud"] >= 10000])), 1) for g in MAIN},
        "all_gate_share": {g: round(float(gate_tot.get(g, 0) / gate_tot.sum()), 3) for g in MAIN},
    }
    stats["backtest"] = model["backtest"]
    stats["ops"] = model["ops"]
    stats["gate_capacity"] = model["gate_capacity"]
    insight["updated"] = pd.Timestamp.now(tz="Asia/Seoul").strftime("%Y-%m-%d")
    # data.js는 임시 파일에 쓴 뒤 바꿔치기 → 중간에 실패해도 기존 파일이 깨지지 않음
    out_js = os.path.join(SITE, "data.js")
    with open(out_js + ".tmp", "w", encoding="utf-8") as f:
        f.write("window.SHOWS=" + json.dumps(results, ensure_ascii=False) + ";\n")
        f.write("window.MODEL=" + json.dumps(model, ensure_ascii=False) + ";\n")
        f.write("window.INSIGHT=" + json.dumps(insight, ensure_ascii=False) + ";\n")
    os.replace(out_js + ".tmp", out_js)
    json.dump(results, open(os.path.join(REP, "shows.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(model, open(os.path.join(REP, "model.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(stats, open(os.path.join(REP, "stats.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print(json.dumps({k: stats[k] for k in ("records", "period", "show_days_analyzed", "cross_exit_ratio", "model", "capacity_per_min")},
                     ensure_ascii=False, indent=1, default=str))
    for r in stats["top_shows"]:
        print(r["date"], r["aud"], r["name"][:25], "t0", r["t0"], "T80", r["t80"], "calm", r["calm_after"],
              {g: (r["gates"][g]["share"], r["wait"][g]["median"]) for g in MAIN})


if __name__ == "__main__":
    main()
