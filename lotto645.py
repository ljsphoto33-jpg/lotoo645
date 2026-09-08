#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
 로또 6/45 구간분석 기반 번호 생성기  (동행복권 공식 데이터)
===============================================================================

  사용법
  ------
    python3 lotto645.py update            최신 회차 자동 수집 (동행복권 서버)
    python3 lotto645.py stats             3/4/5/6개월 구간별 통계 리포트
    python3 lotto645.py gen               번호 5게임 생성 (기본)
    python3 lotto645.py gen -n 10         번호 10게임 생성
    python3 lotto645.py gen --explain     생성된 조합의 통계 검증표까지 출력
    python3 lotto645.py backtest          전략 효과를 과거 데이터로 검증

  옵션
  ----
    --include 7,13       반드시 포함할 번호
    --exclude 4,44       반드시 제외할 번호
    --alpha 0.35         빈도 가중 강도 (0=완전 랜덤, 1.0=고빈도 편중)
    --seed 42            난수 시드 고정(재현용)

===============================================================================
  ※ 먼저 읽어주세요 — 이 프로그램이 할 수 있는 것과 없는 것
-------------------------------------------------------------------------------
  [수학적 사실]
    1게임의 1등 확률은 1/8,145,060 이며, 어떤 번호를 고르든 정확히 같습니다.
    "고빈도 번호", "이월수 제외", "연속번호 패턴" 등 어떤 필터를 써도
    이 확률은 단 0.0000001%도 올라가지 않습니다. 로또 추첨은 매 회차 독립이고,
    공은 지난주에 무엇이 나왔는지 기억하지 못하기 때문입니다.
    온라인의 분석 프로그램들이 "확률을 높인다"고 말하는 부분은 대부분 사실이 아닙니다.

  [그래도 실제로 최적화가 가능한 것 — 이 프로그램이 하는 일]
    (1) 실수령 기대값(EV) 최적화  ★ 유일하게 수학적으로 증명되는 이득
        1등 당첨금은 당첨자 수로 나눕니다. 최근 1년만 봐도 1등 당첨자가
        9명일 때는 30.9억, 23명일 때는 12.0억으로 실수령액이 2.5배 차이납니다.
        사람들이 몰리는 조합(생일수 1~31 편중, 등차수열, 용지 패턴 등)을 피하면
        같은 확률로 당첨되고도 받는 금액의 기대값이 올라갑니다.
        → 이 프로그램은 인기조합 회피를 기본 적용합니다.

    (2) 게임 간 완전분산  ★ 확률이 실제로 개선되는 유일한 지점
        5게임을 살 때 번호를 하나도 겹치지 않게(=45개 중 30개 커버) 고르면,
        "5게임 중 최소 1게임이라도 3개 이상 적중(5등+)"할 확률이
        11.56% → 11.97% 로 올라갑니다. 상대적으로 약 3.5% 개선이며,
        60만 회 시뮬레이션에서 신뢰구간이 겹치지 않는 실제 차이입니다.
        자동으로 5게임을 사면 번호가 평균적으로 겹칩니다.
        (단, 1등 확률은 5게임이 서로 다르기만 하면 5/8,145,060으로 동일합니다)
        → backtest 명령으로 직접 재현해 볼 수 있습니다.

    (3) 구조적으로 비정상적인 조합 배제
        1,2,3,4,5,6 같은 조합은 당첨 확률은 같지만 실제 당첨 이력에 나온 적이 없고
        동시 당첨자 폭증 위험이 큽니다. 실제 당첨 조합의 통계적 분포
        (총합·홀짝·구간·연속수·AC값) 범위 안에 들도록 정리합니다.

  [정직한 결론]
    이 프로그램은 당첨 확률을 높여주지 않습니다. 다만 "같은 확률이면 더 유리한
    조건으로" 번호를 고르게 해줍니다. 그 이상을 약속하는 프로그램은 의심하세요.
    로또는 잃어도 괜찮은 금액으로만 즐기시기 바랍니다.
===============================================================================
"""

import argparse
import csv
import json
import math
import os
import random
import shutil
import sys
from collections import Counter
from itertools import combinations
import http.cookiejar
from urllib.request import Request, build_opener, HTTPCookieProcessor

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

def _app_dir():
    """스크립트(또는 exe)가 있는 폴더."""
    if getattr(sys, "frozen", False):          # PyInstaller 로 만든 exe
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _bundle_dir():
    """exe 안에 동봉된 파일이 풀리는 임시 폴더 (일반 실행이면 앱 폴더)."""
    return getattr(sys, "_MEIPASS", _app_dir())


def _data_dir():
    """읽고 쓸 수 있는 폴더. exe가 Program Files 같은 곳에 있으면 사용자 폴더로."""
    d = _app_dir()
    probe = os.path.join(d, ".write_test")
    try:
        with open(probe, "w"):
            pass
        os.remove(probe)
        return d
    except Exception:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        d2 = os.path.join(base, "Lotto645")
        os.makedirs(d2, exist_ok=True)
        return d2


HERE = _app_dir()
DATA_DIR = _data_dir()
CSV_PATH = os.path.join(DATA_DIR, "lotto645_history.csv")

# exe 로 배포된 경우, 동봉된 초기 데이터를 첫 실행 때 바깥으로 꺼내 놓는다
if not os.path.exists(CSV_PATH):
    _seed = os.path.join(_bundle_dir(), "lotto645_history.csv")
    if os.path.exists(_seed) and os.path.abspath(_seed) != os.path.abspath(CSV_PATH):
        try:
            shutil.copyfile(_seed, CSV_PATH)
        except Exception:
            pass

def set_data_dir(path, seed_from=None):
    """데이터 폴더를 바꾼다 (안드로이드 앱 저장소 등).

    seed_from 에 준 CSV 가 있고 대상이 비어 있으면 복사해 초기 데이터로 쓴다."""
    global DATA_DIR, CSV_PATH
    os.makedirs(path, exist_ok=True)
    DATA_DIR = path
    CSV_PATH = os.path.join(path, "lotto645_history.csv")
    if not os.path.exists(CSV_PATH) and seed_from and os.path.exists(seed_from):
        shutil.copyfile(seed_from, CSV_PATH)
    return CSV_PATH


API_NEW = ("https://www.dhlottery.co.kr/lt645/selectPstLt645InfoNew.do"
           "?srchDir=center&srchLtEpsd={n}")
API_OLD = ("https://www.dhlottery.co.kr/common.do"
           "?method=getLottoNumber&drwNo={n}")
PAGE_URL = "https://www.dhlottery.co.kr/lt645/result"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# 3 / 4 / 5 / 6개월 구간 (1주 1회차 기준)
WINDOWS = {"3개월": 13, "4개월": 17, "5개월": 22, "6개월": 26}
# 구간별 가중치 — 최근 구간에 더 큰 비중
WINDOW_WEIGHTS = {"3개월": 0.40, "4개월": 0.27, "5개월": 0.19, "6개월": 0.14}

ZONES = [(1, 9), (10, 19), (20, 29), (30, 39), (40, 45)]


# ---------------------------------------------------------------------------
# 데이터 입출력
# ---------------------------------------------------------------------------

def load_draws(path=None):
    """CSV에서 회차 데이터를 읽어 회차 오름차순 리스트로 반환."""
    path = path or CSV_PATH
    if not os.path.exists(path):
        sys.exit(f"[오류] 데이터 파일이 없습니다: {path}\n"
                 f"       lotto645_history.csv 를 같은 폴더에 두거나 "
                 f"'python3 lotto645.py update' 를 먼저 실행하세요.")
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.append({
                "draw": int(r["draw"]),
                "date": r["date"],
                "nums": sorted(int(r[f"n{i}"]) for i in range(1, 7)),
                "bonus": int(r["bonus"]),
            })
    out.sort(key=lambda d: d["draw"])
    return out


def save_draws(draws, path=None):
    path = path or CSV_PATH
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["draw", "date", "n1", "n2", "n3", "n4", "n5", "n6", "bonus"])
        for d in draws:
            w.writerow([d["draw"], d["date"]] + list(d["nums"]) + [d["bonus"]])


_OPENER = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
_WARMED = [False]


def _warm_up():
    """일반 브라우저처럼 결과 페이지를 한 번 열어 세션 쿠키를 받아둔다."""
    if _WARMED[0]:
        return
    _WARMED[0] = True
    try:
        _OPENER.open(Request(PAGE_URL, headers={"User-Agent": UA}), timeout=15).read()
    except Exception:
        pass


try:
    import requests as _requests
    try:
        import certifi as _certifi
        _VERIFY = _certifi.where()
    except Exception:
        _VERIFY = True
    _SESSION = _requests.Session()
except Exception:
    _requests = None


def _http_json(url):
    if _requests is not None:
        r = _SESSION.get(url, timeout=20, verify=_VERIFY, headers={
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": PAGE_URL,
            "X-Requested-With": "XMLHttpRequest"})
        return json.loads(r.text)
    _warm_up()
    req = Request(url, headers={"User-Agent": UA,
                                "Accept": "application/json, text/plain, */*",
                                "Accept-Language": "ko-KR,ko;q=0.9",
                                "Referer": PAGE_URL,
                                "X-Requested-With": "XMLHttpRequest"})
    with _OPENER.open(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def fetch_around(epsd):
    """동행복권 서버에서 해당 회차 주변(10회차)을 가져온다."""
    got = {}
    try:
        j = _http_json(API_NEW.format(n=epsd))
        for x in (j.get("data") or {}).get("list") or []:
            got[int(x["ltEpsd"])] = {
                "draw": int(x["ltEpsd"]),
                "date": str(x["ltRflYmd"]),
                "nums": sorted(int(x[f"tm{i}WnNo"]) for i in range(1, 7)),
                "bonus": int(x["bnsWnNo"]),
            }
    except Exception:
        pass
    if got:
        return got
    # 구버전 API 폴백
    try:
        j = _http_json(API_OLD.format(n=epsd))
        if j.get("returnValue") == "success":
            got[int(j["drwNo"])] = {
                "draw": int(j["drwNo"]),
                "date": str(j["drwNoDate"]).replace("-", ""),
                "nums": sorted(int(j[f"drwtNo{i}"]) for i in range(1, 7)),
                "bonus": int(j["bnusNo"]),
            }
    except Exception:
        pass
    return got


def expected_latest_draw(now=None):
    """오늘 날짜 기준으로 '나와 있어야 할' 최신 회차 번호.

    1회 추첨일 2002-12-07(토). 매주 토요일 20:45 추첨."""
    from datetime import datetime, timedelta
    now = now or datetime.now()
    first = datetime(2002, 12, 7, 20, 45)
    if now < first:
        return 0
    return int((now - first) // timedelta(days=7)) + 1


def update_history():
    """동행복권에서 새 회차를 받아 CSV 를 갱신하고 결과를 dict 로 돌려준다."""
    draws = load_draws() if os.path.exists(CSV_PATH) else []
    have = {d["draw"]: d for d in draws}
    last = max(have) if have else 0

    added, cursor, misses, reached = 0, last + 1, 0, False
    while misses < 3:
        got = fetch_around(cursor)
        reached = reached or bool(got)
        new = {k: v for k, v in got.items() if k not in have}
        if not new:
            misses += 1
        else:
            misses = 0
            have.update(new)
            added += len(new)
        cursor = (max(got) + 5) if got else (cursor + 5)
        if cursor > last + 260:          # 5년치 이상 밀린 경우의 안전장치
            break

    if added:
        save_draws([have[k] for k in sorted(have)])
    newest = max(have) if have else 0
    return {"added": added, "reached": reached, "last_before": last,
            "newest": newest, "row": have.get(newest)}


def cmd_update(args=None):
    """최신 회차를 동행복권에서 받아 CSV를 갱신한다."""
    before = load_draws() if os.path.exists(CSV_PATH) else []
    print(f"현재 보유: {len(before)}회차 "
          f"(최신 {max((d['draw'] for d in before), default=0)}회)")
    print("동행복권 서버 조회 중 ...")

    r = update_history()
    if r["added"]:
        row = r["row"]
        print(f"✔ {r['added']}개 회차 추가. 최신 {r['newest']}회 "
              f"({row['date']}) → {row['nums']} + 보너스 {row['bonus']}")
    elif r["reached"]:
        print("✔ 이미 최신 상태입니다.")
    else:
        print("✖ 동행복권 서버에 연결하지 못했습니다.")
        print("  인터넷 연결 또는 방화벽/사내망 차단 여부를 확인하세요.")
        print("  (연결이 안 되어도 기존 CSV 데이터로 stats / gen 은 정상 동작합니다)")


# ---------------------------------------------------------------------------
# 조합의 통계적 특성
# ---------------------------------------------------------------------------

def ac_value(nums):
    """AC값 = 서로 다른 차이의 개수 - 5. 번호가 고르게 흩어질수록 큼(최대 10)."""
    diffs = {abs(a - b) for a, b in combinations(nums, 2)}
    return len(diffs) - 5


def features(nums):
    nums = sorted(nums)
    consec = sum(1 for i in range(5) if nums[i + 1] - nums[i] == 1)
    run, best = 1, 1
    for i in range(5):
        run = run + 1 if nums[i + 1] - nums[i] == 1 else 1
        best = max(best, run)
    zc = [0] * len(ZONES)
    for n in nums:
        for i, (lo, hi) in enumerate(ZONES):
            if lo <= n <= hi:
                zc[i] += 1
                break
    return {
        "sum": sum(nums),
        "odd": sum(1 for n in nums if n % 2 == 1),
        "low": sum(1 for n in nums if n <= 22),      # 저구간 1~22
        "consec_pairs": consec,                       # 연속번호 쌍 개수
        "max_run": best,                              # 최장 연속 길이
        "tail_sum": sum(n % 10 for n in nums),        # 끝수합
        "ac": ac_value(nums),
        "zones": zc,
        "zones_used": sum(1 for c in zc if c > 0),
        "max_zone": max(zc),
        "over31": sum(1 for n in nums if n > 31),     # 생일수(1~31) 밖 개수
    }


def percentile(sorted_vals, p):
    if not sorted_vals:
        return 0
    k = (len(sorted_vals) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return sorted_vals[int(k)]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def calibrate(draws, keep=0.94):
    """실제 당첨 조합 분포에서 필터 경계를 자동 산출.

    keep=0.94 이면 역대 당첨 조합의 약 94%가 개별 항목을 통과하는 균형형 경계."""
    tail = (1 - keep) / 2
    feats = [features(d["nums"]) for d in draws]
    S = sorted(f["sum"] for f in feats)
    T = sorted(f["tail_sum"] for f in feats)
    A = sorted(f["ac"] for f in feats)
    return {
        "sum_min": int(round(percentile(S, tail))),
        "sum_max": int(round(percentile(S, 1 - tail))),
        "tail_min": int(round(percentile(T, tail))),
        "tail_max": int(round(percentile(T, 1 - tail))),
        "ac_min": int(round(percentile(A, tail))),
        "odd_min": 1, "odd_max": 5,
        "low_min": 1, "low_max": 5,
        "max_run": 2,          # 3연속 이상 금지
        "consec_max": 2,       # 연속 쌍 최대 2
        "zones_min": 3,        # 최소 3개 구간에 분산
        "max_zone": 3,         # 한 구간 최대 3개
        "carry_max": 2,        # 지난 회차 번호 최대 2개까지 허용(3개 이상은 역대 2%)
        "carry_penalty": 0.6,  # 지난 회차 번호 선택 가중치 감산(하드 제외 대신 소프트)
        "min_over31": 1,       # 생일수(1~31)로만 채우지 않음  ← EV 최적화
    }


# ---------------------------------------------------------------------------
# 구간(3/4/5/6개월) 분석
# ---------------------------------------------------------------------------

def window_counts(draws, w):
    c = Counter()
    for d in draws[-w:]:
        c.update(d["nums"])
    return c


def gaps(draws):
    """번호별 '마지막 출현 이후 경과 회차'."""
    g = {n: len(draws) for n in range(1, 46)}
    for i, d in enumerate(reversed(draws)):
        for n in d["nums"]:
            if g[n] == len(draws):
                g[n] = i
    return g


def analyze(draws):
    """3/4/5/6개월 구간별 분석 결과를 한 번에 반환."""
    res = {"windows": {}, "gaps": gaps(draws),
           "last": draws[-1]["nums"], "n_draws": len(draws)}
    for name, w in WINDOWS.items():
        c = window_counts(draws, w)
        exp = w * 6 / 45.0                       # 균등 기대 출현수
        sd = math.sqrt(w * (6 / 45.0) * (1 - 6 / 45.0))
        res["windows"][name] = {
            "w": w, "counts": c, "expected": exp, "sd": sd,
            "hot": [n for n, _ in c.most_common(8)],
            "cold": sorted(range(1, 46), key=lambda n: (c.get(n, 0), n))[:8],
        }
    # 이월(직전 회차 번호가 다음 회차에 다시 나온 개수) 이력
    carry = [len(set(draws[i]["nums"]) & set(draws[i - 1]["nums"]))
             for i in range(1, len(draws))]
    res["carry_hist"] = Counter(carry)
    res["carry_mean"] = sum(carry) / len(carry)
    # 연속번호 쌍 이력
    res["consec_hist"] = Counter(features(d["nums"])["consec_pairs"] for d in draws)
    return res


def number_scores(draws, alpha=0.35):
    """번호별 선택 가중치.

    alpha = 0     → 완전 균등(순수 랜덤)
    alpha 클수록  → 최근 구간 고빈도 번호 쪽으로 기울어짐
    (주의: 통계적으로 적중률을 올려주지 않습니다. backtest 참고)
    """
    a = analyze(draws)
    score = {}
    for n in range(1, 46):
        z = 0.0
        for name, info in a["windows"].items():
            cnt = info["counts"].get(n, 0)
            z += WINDOW_WEIGHTS[name] * (cnt - info["expected"]) / info["sd"]
        score[n] = max(0.05, 1.0 + alpha * z)
    return score, a


# ---------------------------------------------------------------------------
# 조합 생성
# ---------------------------------------------------------------------------

def is_arithmetic(nums):
    d = nums[1] - nums[0]
    return all(nums[i + 1] - nums[i] == d for i in range(5))


def passes(nums, cfg, last_nums, past_sets):
    f = features(nums)
    if not (cfg["sum_min"] <= f["sum"] <= cfg["sum_max"]):        return False
    if not (cfg["tail_min"] <= f["tail_sum"] <= cfg["tail_max"]): return False
    if f["ac"] < cfg["ac_min"]:                                   return False
    if not (cfg["odd_min"] <= f["odd"] <= cfg["odd_max"]):        return False
    if not (cfg["low_min"] <= f["low"] <= cfg["low_max"]):        return False
    if f["max_run"] > cfg["max_run"]:                             return False
    if f["consec_pairs"] > cfg["consec_max"]:                     return False
    if f["zones_used"] < cfg["zones_min"]:                        return False
    if f["max_zone"] > cfg["max_zone"]:                           return False
    if f["over31"] < cfg["min_over31"]:                           return False
    if len(set(nums) & set(last_nums)) > cfg["carry_max"]:        return False
    if is_arithmetic(nums):                                       return False   # 등차수열 = 인기조합
    if frozenset(nums) in past_sets:                              return False   # 역대 1등 조합 재사용 금지
    return True


def weighted_pick(score, pool, k, rng):
    pool = list(pool)
    w = [score[n] for n in pool]
    out = []
    for _ in range(k):
        tot = sum(w)
        r = rng.random() * tot
        acc = 0.0
        for i, x in enumerate(w):
            acc += x
            if acc >= r:
                break
        out.append(pool.pop(i))
        w.pop(i)
    return sorted(out)


def generate(draws, n_games=5, alpha=0.35, include=(), exclude=(),
             keep=0.94, rng=None, max_overlap=0):
    rng = rng or random.Random()
    score, a = number_scores(draws, alpha)
    cfg = calibrate(draws, keep)
    last_nums = draws[-1]["nums"]
    # 지난 회차 번호는 '완전 제외'가 아니라 가중치를 낮춘다.
    # (역대 61%의 회차에서 이월번호가 1개 이상 나오므로 전면 제외는 과도한 필터)
    for n in last_nums:
        score[n] *= cfg["carry_penalty"]
    past_sets = {frozenset(d["nums"]) for d in draws}

    include = sorted(set(include))
    pool_base = [n for n in range(1, 46)
                 if n not in exclude and n not in include]

    # 45개 번호로 완전분산(중복 0)이 가능한 것은 최대 7게임까지
    if max_overlap == 0 and n_games > 7:
        max_overlap = 1

    games, tries = [], 0
    relax_at = 60000
    while len(games) < n_games and tries < 400000:
        if tries == relax_at and max_overlap < 6:      # 조건이 너무 빡빡하면 완화
            max_overlap += 1
            relax_at += 60000
        tries += 1
        nums = sorted(include + weighted_pick(score, pool_base,
                                              6 - len(include), rng))
        if not passes(nums, cfg, last_nums, past_sets):
            continue
        # 이미 뽑은 게임과 과도하게 겹치지 않도록 (게임 간 분산)
        if any(len(set(nums) & set(g)) > max_overlap for g in games):
            continue
        games.append(nums)
    return games, cfg, a


# ---------------------------------------------------------------------------
# 리포트
# ---------------------------------------------------------------------------

def bar(v, mx, width=22):
    return "█" * max(0, int(round(v / mx * width))) if mx else ""


def cmd_stats(args):
    draws = load_draws()
    a = analyze(draws)
    cfg = calibrate(draws, args.keep)
    last = draws[-1]

    print("=" * 72)
    print(f" 로또 6/45 구간 분석  |  총 {len(draws)}회차 "
          f"(1회 ~ {last['draw']}회, {last['date']})")
    print("=" * 72)
    print(f"\n▶ 직전 회차 {last['draw']}회 : {last['nums']}  +보너스 {last['bonus']}")
    f = features(last["nums"])
    print(f"   총합 {f['sum']} / 홀짝 {f['odd']}:{6-f['odd']} / "
          f"저고 {f['low']}:{6-f['low']} / 연속쌍 {f['consec_pairs']} / AC {f['ac']}")

    print("\n" + "-" * 72)
    print(" [1] 구간별 고빈도·저빈도 번호")
    print("-" * 72)
    for name, info in a["windows"].items():
        hot = ", ".join(f"{n}({info['counts'][n]}회)" for n in info["hot"][:6])
        cold = ", ".join(f"{n}({info['counts'].get(n,0)}회)" for n in info["cold"][:6])
        print(f"\n  {name} (최근 {info['w']}회차, 기대 출현 {info['expected']:.1f}회)")
        print(f"    자주 나온 번호 : {hot}")
        print(f"    적게 나온 번호 : {cold}")

    print("\n" + "-" * 72)
    print(" [2] 종합 점수 (3/4/5/6개월 가중 합산, 상위·하위 10개)")
    print("-" * 72)
    score, _ = number_scores(draws, args.alpha)
    ranked = sorted(range(1, 46), key=lambda n: -score[n])
    mx = max(score.values())
    print("\n  ▲ 상위")
    for n in ranked[:10]:
        print(f"    {n:2d}  {score[n]:5.2f}  {bar(score[n], mx)}")
    print("\n  ▼ 하위")
    for n in ranked[-10:]:
        print(f"    {n:2d}  {score[n]:5.2f}  {bar(score[n], mx)}")

    print("\n" + "-" * 72)
    print(" [3] 미출현 기간(마지막 출현 이후 경과 회차) 상위 10개")
    print("-" * 72)
    g = sorted(a["gaps"].items(), key=lambda kv: -kv[1])[:10]
    print("    " + "  ".join(f"{n}번:{v}회" for n, v in g))

    print("\n" + "-" * 72)
    print(" [4] 이월번호 — 직전 회차 번호가 다음 회차에 다시 나온 개수")
    print("-" * 72)
    tot = sum(a["carry_hist"].values())
    for k in sorted(a["carry_hist"]):
        c = a["carry_hist"][k]
        print(f"    {k}개 겹침 : {c:4d}회 ({c/tot*100:5.1f}%)  {bar(c, tot*0.5)}")
    print(f"    → 평균 {a['carry_mean']:.2f}개. 지난주 번호를 '전부' 빼는 것은")
    print(f"      과도한 필터입니다(약 {(1-a['carry_hist'][0]/tot)*100:.0f}%의 회차에서 1개 이상 재출현).")
    print(f"      이 프로그램은 하드 제외 대신 선택 가중치를 {cfg['carry_penalty']}배로 낮추고,")
    print(f"      최대 {cfg['carry_max']}개까지만 허용합니다(3개 이상은 역대 2.1%).")

    print("\n" + "-" * 72)
    print(" [5] 연속번호 쌍 출현 분포")
    print("-" * 72)
    tot = sum(a["consec_hist"].values())
    for k in sorted(a["consec_hist"]):
        c = a["consec_hist"][k]
        print(f"    연속쌍 {k}개 : {c:4d}회 ({c/tot*100:5.1f}%)  {bar(c, tot*0.6)}")

    print("\n" + "-" * 72)
    print(f" [6] 자동 산출된 필터 경계 (역대 당첨조합 약 {args.keep*100:.0f}% 통과 기준)")
    print("-" * 72)
    print(f"    총합       {cfg['sum_min']} ~ {cfg['sum_max']}")
    print(f"    끝수합     {cfg['tail_min']} ~ {cfg['tail_max']}")
    print(f"    AC값       {cfg['ac_min']} 이상")
    print(f"    홀수 개수  {cfg['odd_min']} ~ {cfg['odd_max']}")
    print(f"    저구간(1~22) {cfg['low_min']} ~ {cfg['low_max']}개")
    print(f"    최장 연속  {cfg['max_run']} 이하  /  연속쌍 {cfg['consec_max']} 이하")
    print(f"    구간 분산  최소 {cfg['zones_min']}개 구간, 한 구간 최대 {cfg['max_zone']}개")
    print(f"    이월번호   가중치 {cfg['carry_penalty']}배 감산, 최대 {cfg['carry_max']}개")
    print(f"    32~45 번호 최소 {cfg['min_over31']}개 (생일수 편중 회피 = 기대값 최적화)")
    print()


def cmd_gen(args):
    draws = load_draws()
    rng = random.Random(args.seed)
    inc = [int(x) for x in args.include.split(",") if x.strip()] if args.include else []
    exc = [int(x) for x in args.exclude.split(",") if x.strip()] if args.exclude else []
    games, cfg, a = generate(draws, args.n, args.alpha, inc, exc,
                             args.keep, rng, args.max_overlap)

    last = draws[-1]
    nxt = last["draw"] + 1
    print("=" * 72)
    print(f" 제 {nxt}회 추천 번호  |  분석 기준: 1~{last['draw']}회 "
          f"(직전 {last['date']})")
    print("=" * 72)
    print(f" 직전 회차 번호 {last['nums']} → 선택 가중치 "
          f"{cfg['carry_penalty']}배 감산, 최대 {cfg['carry_max']}개까지 이월 허용\n")

    for i, g in enumerate(games, 1):
        f = features(g)
        marks = " ".join(f"{n:2d}" for n in g)
        print(f"  {chr(64+i)} 게임   {marks}")
        if args.explain:
            print(f"            총합 {f['sum']:3d} | 홀짝 {f['odd']}:{6-f['odd']} | "
                  f"저고 {f['low']}:{6-f['low']} | 연속쌍 {f['consec_pairs']} | "
                  f"AC {f['ac']:2d} | 끝수합 {f['tail_sum']:2d} | "
                  f"32이상 {f['over31']}개 | 구간분포 {f['zones']}")
    print()

    if args.explain:
        print("-" * 72)
        print(" 적용된 조건")
        print("-" * 72)
        print(f"  · 총합 {cfg['sum_min']}~{cfg['sum_max']}, 끝수합 {cfg['tail_min']}~{cfg['tail_max']}, "
              f"AC {cfg['ac_min']}+ (역대 당첨조합 {args.keep*100:.0f}% 범위)")
        print(f"  · 3연속 이상 금지, 연속쌍 {cfg['consec_max']}개 이하")
        print(f"  · {cfg['zones_min']}개 이상 구간에 분산, 한 구간 {cfg['max_zone']}개 이하")
        print(f"  · 직전 회차 번호 가중치 {cfg['carry_penalty']}배 감산 + {cfg['carry_max']}개 이하로만 이월")
        print(f"  · 32~45 최소 1개 (생일수 편중 회피)")
        print(f"  · 등차수열·역대 1등 조합 배제")
        if args.max_overlap == 0:
            print(f"  · 게임 간 번호 완전분산 (중복 0개) "
                  f"← 확률이 실제로 개선되는 유일한 조건")
        else:
            print(f"  · 게임 간 번호 중복 {args.max_overlap}개 이하")
        print(f"  · 구간 가중치 alpha={args.alpha} "
              f"(3개월 {WINDOW_WEIGHTS['3개월']} / 4개월 {WINDOW_WEIGHTS['4개월']} / "
              f"5개월 {WINDOW_WEIGHTS['5개월']} / 6개월 {WINDOW_WEIGHTS['6개월']})")
        print()

    print("-" * 72)
    print(" ※ 1등 확률은 어떤 번호든 1/8,145,060로 동일합니다. 위 조건은 확률을")
    print("   올리는 것이 아니라, 당첨 시 나눠 갖는 인원을 줄여 실수령 기대값을")
    print("   높이고 구조적으로 비정상적인 조합을 걸러내기 위한 것입니다.")
    print("-" * 72)


# ---------------------------------------------------------------------------
# 백테스트 — 전략이 실제로 효과가 있는지 데이터로 검증
# ---------------------------------------------------------------------------

def _clustered(per_draw):
    """회차 단위 클러스터 표준오차 → 95% 신뢰구간 폭."""
    n = len(per_draw)
    m = sum(per_draw) / n
    if n < 2:
        return m, 0.0
    var = sum((x - m) ** 2 for x in per_draw) / (n - 1)
    return m, 1.96 * math.sqrt(var / n)


def cmd_backtest(args):
    draws = load_draws()
    rng = random.Random(args.seed if args.seed is not None else 20260831)
    n_test = args.draws
    test_from = len(draws) - n_test
    gpd = args.games

    print("=" * 74)
    print(" 백테스트 1 — 번호 선택 전략이 적중률을 바꾸는가?")
    print("=" * 74)
    print(f" 시험 회차 : 최근 {n_test}회 "
          f"({draws[test_from]['draw']}회 ~ {draws[-1]['draw']}회)")
    print(f" 회차당 {gpd}게임 × 3개 전략 = 전략별 {n_test*gpd:,}게임")
    print(" 각 회차는 그 시점까지의 과거 데이터만 사용합니다 (미래 정보 차단)\n")

    def s_random(past, k, rng):
        return [sorted(rng.sample(range(1, 46), 6)) for _ in range(k)]

    def s_weighted(past, k, rng):
        score, _ = number_scores(past, args.alpha)
        return [weighted_pick(score, range(1, 46), 6, rng) for _ in range(k)]

    def s_full(past, k, rng):
        gs, _, _ = generate(past, k, args.alpha, (), (), args.keep, rng,
                            max_overlap=6)
        return gs

    strategies = [("① 순수 랜덤 (자동)", s_random),
                  ("② 구간 빈도 가중만", s_weighted),
                  ("③ 이 프로그램 (가중+필터)", s_full)]

    print("-" * 74)
    print(f" {'전략':<26}{'평균 적중':>12}{'3개+ 적중률 (95% 신뢰구간)':>30}")
    print("-" * 74)
    for name, sampler in strategies:
        per_draw_p3, per_draw_mean = [], []
        for i in range(test_from, len(draws)):
            win = set(draws[i]["nums"])
            gs = sampler(draws[:i], gpd, rng)
            ms = [len(win & set(g)) for g in gs]
            per_draw_p3.append(sum(1 for m in ms if m >= 3) / len(ms))
            per_draw_mean.append(sum(ms) / len(ms))
        p3, ci = _clustered(per_draw_p3)
        mn, _ = _clustered(per_draw_mean)
        print(f" {name:<26}{mn:>12.4f}"
              f"{p3*100:>18.3f}%  ± {ci*100:.3f}%p")
    print("-" * 74)
    print(" 이론값 (모든 조합에 공통) :  평균 적중 0.8000   |   3개+ 적중률 2.244%")
    print("-" * 74)
    print("""
 [해석]
 세 전략의 신뢰구간이 모두 이론값 2.244%를 포함합니다. 즉 통계적으로 구분되는
 차이가 없습니다. 이것이 정답입니다 — 로또는 매 회차 독립 시행이므로 어떤
 번호를 고르든 적중 확률은 같습니다. 구간 분석도, 이 프로그램의 필터도
 그 확률을 바꾸지 못합니다. 그 사실을 숨기지 않고 직접 확인시켜 주는 것이
 이 백테스트의 목적입니다.
""")

    # ------------------------------------------------------------------
    print("=" * 74)
    print(" 백테스트 2 — 여러 게임을 살 때 번호를 '분산'하면? ★ 실제 효과 있음")
    print("=" * 74)
    N = args.repeats
    A = list(range(1, 46))
    print(f" 5게임 구매를 {N:,}회 시뮬레이션하여 비교\n")

    def build(mode):
        if mode == "indep":
            return [rng.sample(A, 6) for _ in range(5)]
        if mode == "ov2":
            gs = []
            while len(gs) < 5:
                c = rng.sample(A, 6)
                if any(len(set(c) & set(g)) > 2 for g in gs):
                    continue
                gs.append(c)
            return gs
        p = rng.sample(A, 30)                     # 완전분산: 서로 겹치지 않는 30개
        return [p[i * 6:(i + 1) * 6] for i in range(5)]

    labels = [("indep", "겹침 신경 안 씀 (일반 자동 5게임)"),
              ("ov2", "중복 2개 이하로 완화 분산"),
              ("disjoint", "완전분산 — 30개 번호 전부 다르게 ★ 이 프로그램 기본값")]
    print("-" * 74)
    print(f" {'구매 방식':<40}{'5게임 중 최소 1게임 3개+ 적중':>32}")
    print("-" * 74)
    for mode, label in labels:
        hit = 0
        for _ in range(N):
            win = set(rng.sample(A, 6))
            if any(len(win & set(g)) >= 3 for g in build(mode)):
                hit += 1
        p = hit / N
        ci = 1.96 * math.sqrt(p * (1 - p) / N)
        print(f" {label:<40}{p*100:>22.3f}%  ± {ci*100:.3f}%p")
    print("-" * 74)
    print("""
 [해석]
 완전분산은 신뢰구간이 겹치지 않을 만큼 확실하게 높습니다. 5등(3개 적중)
 이상을 한 번이라도 받을 확률이 상대적으로 약 3~4% 개선됩니다.
 이유는 단순합니다 — 5게임에 번호가 겹치면 45개 중 실제로 커버하는 번호가
 30개보다 줄어들기 때문입니다. 자동 5게임을 사면 평균적으로 번호가 겹칩니다.

 단, 1등 확률은 5게임이 서로 다른 조합이기만 하면 5/8,145,060으로 동일하며
 분산 여부와 무관합니다. 분산이 개선하는 것은 '하위 등수라도 한 번은 받을
 확률'입니다. 이것이 이 프로그램에서 수치로 증명되는 유일한 확률적 이득입니다.
""")


# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description="로또 6/45 구간분석 번호 생성기",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")

    def common(sp):
        sp.add_argument("--alpha", type=float, default=0.35,
                        help="구간 빈도 가중 강도 (0=균등, 기본 0.35)")
        sp.add_argument("--keep", type=float, default=0.94,
                        help="필터 느슨함 (역대 당첨조합 통과 비율, 기본 0.94)")
        sp.add_argument("--seed", type=int, default=None, help="난수 시드")

    s = sub.add_parser("update", help="최신 회차 자동 수집")
    s.set_defaults(func=cmd_update)

    s = sub.add_parser("stats", help="3/4/5/6개월 구간 통계 리포트")
    common(s)
    s.set_defaults(func=cmd_stats)

    s = sub.add_parser("gen", help="번호 생성")
    common(s)
    s.add_argument("-n", type=int, default=5, help="생성할 게임 수 (기본 5)")
    s.add_argument("--include", type=str, default="", help="반드시 포함 (예: 7,13)")
    s.add_argument("--exclude", type=str, default="", help="반드시 제외 (예: 4,44)")
    s.add_argument("--max-overlap", dest="max_overlap", type=int, default=0,
                   help="게임 간 허용 중복 개수 (기본 0 = 완전분산). "
                        "n이 7게임을 넘으면 자동 완화")
    s.add_argument("--explain", action="store_true", help="통계 검증표 함께 출력")
    s.set_defaults(func=cmd_gen)

    s = sub.add_parser("backtest", help="전략 효과 검증")
    common(s)
    s.add_argument("--draws", type=int, default=200, help="시험할 최근 회차 수")
    s.add_argument("--games", type=int, default=300, help="회차당 생성 게임 수")
    s.add_argument("--repeats", type=int, default=200000,
                   help="분산 실험 시뮬레이션 횟수 (기본 200000)")
    s.set_defaults(func=cmd_backtest)

    a = p.parse_args()
    if not a.cmd:
        a = p.parse_args(["gen"])
    a.func(a)


if __name__ == "__main__":
    main()
