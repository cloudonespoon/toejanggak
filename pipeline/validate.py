"""새로 만든 data.js가 정상인지 검사 (자동 갱신용).

사용법: python validate.py 새data.js [이전data.js]
        python validate.py --same 새data.js 이전data.js   (갱신 날짜 말고 바뀐 게 없으면 종료 코드 0)
- 형식이 깨졌거나, 공연 수·기록 수가 이전보다 크게 줄었으면 실패(종료 코드 1)
- 실패하면 워크플로가 이전 data.js를 그대로 두므로 서비스는 계속 이전 데이터로 동작한다.
"""
import json
import re
import sys


def load(path):
    text = open(path, encoding="utf-8").read()
    out = {}
    for name in ("SHOWS", "MODEL", "INSIGHT"):
        m = re.search(r"window\." + name + r"=(.*?);\n", text, re.S)
        if not m:
            raise ValueError(f"{name} 없음")
        out[name] = json.loads(m.group(1))
    return out


def check(new, old=None):
    errs = []
    shows, model, ins = new["SHOWS"], new["MODEL"], new["INSIGHT"]
    if len(shows) < 50:
        errs.append(f"분석된 공연일이 너무 적음 ({len(shows)}일)")
    if len(model.get("shapes", [])) < 3:
        errs.append("규모별 퇴장 패턴(shapes)이 3개 미만")
    for s in shows:
        if not (0 <= s["t80"] <= 150 and 0 <= s["calm_after"] <= 150 and s["excess"] > 0):
            errs.append(f"이상값: {s['date']} t80={s['t80']} calm={s['calm_after']} excess={s['excess']}")
            break
    if not model.get("backtest", {}).get("n"):
        errs.append("백테스트 결과 없음")
    if old:
        o_ins = old["INSIGHT"]
        if ins.get("records", 0) < o_ins.get("records", 0):
            errs.append(f"기록 수 감소 {o_ins.get('records')} → {ins.get('records')}")
        if len(shows) < 0.9 * len(old["SHOWS"]):
            errs.append(f"공연일 10% 이상 감소 {len(old['SHOWS'])} → {len(shows)}")
    return errs


def same(a, b):
    """갱신 날짜만 빼고 내용이 같은지"""
    a, b = json.loads(json.dumps(a)), json.loads(json.dumps(b))
    a["INSIGHT"].pop("updated", None)
    b["INSIGHT"].pop("updated", None)
    return a == b


if __name__ == "__main__":
    if sys.argv[1] == "--same":  # 내용이 같으면 0, 다르면 1
        sys.exit(0 if same(load(sys.argv[2]), load(sys.argv[3])) else 1)
    new = load(sys.argv[1])
    old = load(sys.argv[2]) if len(sys.argv) > 2 else None
    errs = check(new, old)
    if errs:
        print("검사 실패:\n- " + "\n- ".join(errs))
        sys.exit(1)
    print(f"검사 통과: 공연일 {len(new['SHOWS'])}일, 기록 {new['INSIGHT'].get('records'):,}건")
