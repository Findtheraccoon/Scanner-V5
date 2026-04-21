"""
Scanner v4.2.1 — Main Engine (Python Port)
Ported from scanner_v4_2_1.html lines 577-698.

Orchestrates: indicators → patterns → alignment → divergence →
sector relative → pivots → key levels → fakeouts → GAP → ORB → scoring.
"""
from .indicators import (
    calc_indicators, ma, pct_change, vol_ratio,
)
from .patterns import detect
from .scoring import (
    trend, trend_slope, find_pivots, key_levels,
    layered_score, get_time_weight,
)


BENCH = {"QQQ": "SPY"}


def analyze(ticker, candles_daily, candles_1h, candles_15m,
            spy_daily=None, sim_datetime=None, sim_date=None,
            bench_ticker=None, bench_daily=None):
    """
    Full analysis for one asset at one point in time.
    
    Args:
        ticker: symbol string (e.g. "QQQ")
        candles_daily: list of daily candle dicts (oldest→newest)
        candles_1h: list of 1H candle dicts
        candles_15m: list of 15M candle dicts
        spy_daily: list of SPY daily candle dicts (for DivSPY, always SPY)
        sim_datetime: simulated datetime string "YYYY-MM-DD HH:MM:SS" in ET
        sim_date: simulated date string "YYYY-MM-DD"
        bench_ticker: optional benchmark ticker override for FzaRel (e.g. "QQQ").
                      If None, falls back to BENCH[ticker].
        bench_daily: optional benchmark daily candles for FzaRel.
                     If None, falls back to spy_daily (legacy behavior).
    
    Returns:
        dict with full analysis results, or dict with error=True
    """
    if not candles_daily or not candles_1h or not candles_15m:
        return {"ticker": ticker, "error": True}

    # ─── INDICATORS ───
    ind = calc_indicators(candles_daily, candles_1h, candles_15m, sim_date)

    # ─── PATTERNS ───
    patterns = detect(candles_15m, candles_1h, candles_daily, ind)

    # ─── TREND / ALIGNMENT (Option B: with slope fallback) ───
    ma40M = ma(candles_15m, 40)

    # 15M trend
    tM = trend(candles_15m, ind["ma20M"], ma40M) if ma40M else trend_slope(candles_15m, ind["ma20M"])
    if tM == "neutral" and ind["ma20M"] and ma40M:
        p = candles_15m[-1]["c"]
        if p > ind["ma20M"] and p > ma40M:
            sl = trend_slope(candles_15m, ind["ma20M"])
            if sl == "bullish":
                tM = "bullish"
        if p < ind["ma20M"] and p < ma40M:
            sl = trend_slope(candles_15m, ind["ma20M"])
            if sl == "bearish":
                tM = "bearish"

    # 1H trend
    tH = trend(candles_1h, ind["ma20H"], ind["ma40H"])
    if tH == "neutral" and ind["ma20H"] and ind["ma40H"]:
        p = candles_1h[-1]["c"]
        if p > ind["ma20H"] and p > ind["ma40H"]:
            sl = trend_slope(candles_1h, ind["ma20H"])
            if sl == "bullish":
                tH = "bullish"
        if p < ind["ma20H"] and p < ind["ma40H"]:
            sl = trend_slope(candles_1h, ind["ma20H"])
            if sl == "bearish":
                tH = "bearish"

    # Daily trend: strict, no fallback
    tD = trend(candles_daily, ind["ma20D"], ind["ma40D"])

    # Alignment
    ts = [tM, tH, tD]
    bc = sum(1 for t in ts if t == "bearish")
    uc = sum(1 for t in ts if t == "bullish")
    if bc >= 3:
        aln = {"n": 3, "dir": "bearish"}
    elif uc >= 3:
        aln = {"n": 3, "dir": "bullish"}
    elif bc >= 2:
        aln = {"n": 2, "dir": "bearish"}
    elif uc >= 2:
        aln = {"n": 2, "dir": "bullish"}
    else:
        aln = {"n": max(bc, uc), "dir": "mixed"}

    # ─── DIVERGENCE SPY ───
    div_spy = None
    a_chg = ind["chgD"]
    spy_chg = pct_change(spy_daily, 1) if spy_daily and len(spy_daily) >= 2 else 0

    if ticker != "SPY" and spy_chg != 0:
        if (a_chg < -0.5 and spy_chg > 0.3) or (a_chg > 0.5 and spy_chg < -0.3):
            div_spy = {"a": a_chg, "spy": spy_chg, "type": "bearish" if a_chg < 0 else "bullish"}
            patterns.append({
                "tf": "D",
                "d": f"Div SPY ({ticker}:{'+' if a_chg > 0 else ''}{a_chg}% vs SPY:{'+' if spy_chg > 0 else ''}{spy_chg}%) → VERIFICAR CATALIZADOR",
                "sg": "PUT" if a_chg < 0 else "CALL",
                "w": 1, "cat": "CONFIRM", "age": 0,
            })

    # ─── SECTOR RELATIVE STRENGTH ───
    # Benchmark resolution:
    #   - If bench_ticker is passed explicitly, use it + bench_daily
    #   - Otherwise fall back to BENCH map with spy_daily (legacy behavior)
    sec_rel = None
    if bench_ticker is not None:
        bench = bench_ticker
        bench_data = bench_daily
    else:
        bench = BENCH.get(ticker)
        bench_data = spy_daily

    if bench and bench_data and len(bench_data) >= 2:
        b_chg = pct_change(bench_data, 1)
        sec_rel = {"a": a_chg, "b": b_chg, "tk": bench, "diff": round(a_chg - b_chg, 2)}
        if ((aln["dir"] == "bullish" and a_chg > b_chg + 0.5)
                or (aln["dir"] == "bearish" and a_chg < b_chg - 0.5)):
            patterns.append({
                "tf": "D",
                "d": f"FzaRel {'+' if sec_rel['diff'] > 0 else ''}{sec_rel['diff']}% vs {bench}",
                "sg": "CONFIRM", "w": 4, "cat": "CONFIRM", "age": 0,
            })

    # ─── PIVOTS & KEY LEVELS ───
    piv_d = find_pivots(candles_daily, 50, 0.004)
    piv_h = find_pivots(candles_1h, 50, 0.003)
    k_lvls = key_levels(ind, piv_d, piv_h, ind["price"])

    # ─── FAKEOUT ON STRONG PIVOTS ───
    if len(candles_15m) >= 3:
        c2 = candles_15m[-2]
        c1 = candles_15m[-1]
        for piv in [p for p in piv_h["r"] if p["tx"] >= 2]:
            if c2["h"] > piv["lv"] and c2["c"] < piv["lv"] and c1["c"] < piv["lv"]:
                patterns.append({
                    "tf": "15M",
                    "d": f"Fakeout sobre pivote ${piv['lv']} ({piv['tx']}x)",
                    "sg": "WARN", "w": -3, "cat": "RISK", "age": 0,
                })
        for piv in [p for p in piv_h["s"] if p["tx"] >= 2]:
            if c2["l"] < piv["lv"] and c2["c"] > piv["lv"] and c1["c"] > piv["lv"]:
                patterns.append({
                    "tf": "15M",
                    "d": f"Fakeout bajo pivote ${piv['lv']} ({piv['tx']}x)",
                    "sg": "WARN", "w": -3, "cat": "RISK", "age": 0,
                })

    # ─── GAP as CONFIRM ───
    if ind["gap"] and ind["gap"]["significant"]:
        if ind["gap"]["dir"] == "bullish":
            patterns.append({
                "tf": "D",
                "d": f"Gap alcista {'+' if ind['gap']['pct'] > 0 else ''}{ind['gap']['pct']}%",
                "sg": "CALL", "w": 1, "cat": "CONFIRM", "age": 0,
            })
        else:
            patterns.append({
                "tf": "D",
                "d": f"Gap bajista {ind['gap']['pct']}%",
                "sg": "PUT", "w": 1, "cat": "CONFIRM", "age": 0,
            })

    # ─── ORB as TRIGGER ───
    # ORB triggers are only valid in the first hour of market (9:30–10:30 ET).
    # Evidence: 56% of ORB_Breakdown signals fired in prime2+caution (48.1% WR, 0.80x MFE/MAE).
    # After 10:30, the Opening Range has no predictive value — it becomes a different pattern.
    # ORB key levels are still tracked for S/R reference regardless of time.
    _orb_in_first_hour = False
    if sim_datetime:
        try:
            _hhmm = sim_datetime[11:16]  # "HH:MM" from "YYYY-MM-DD HH:MM:SS"
            _orb_in_first_hour = _hhmm <= "10:30"
        except Exception:
            _orb_in_first_hour = True   # fallback: allow if parsing fails
    else:
        _orb_in_first_hour = True       # live mode without sim_datetime: allow

    if ind["orb"]:
        if _orb_in_first_hour:
            if ind["orb"]["breakUp"] and ind["volM"] >= 1.0:
                patterns.append({
                    "tf": "15M",
                    "d": f"ORB breakout ↑${ind['orb']['high']}",
                    "sg": "CALL", "w": 2, "cat": "TRIGGER", "age": 0,
                })
            if ind["orb"]["breakDown"] and ind["volM"] >= 1.0:
                patterns.append({
                    "tf": "15M",
                    "d": f"ORB breakdown ↓${ind['orb']['low']}",
                    "sg": "PUT", "w": 2, "cat": "TRIGGER", "age": 0,
                })
        # ORB levels always tracked for S/R reference (regardless of time)
        if not ind["orb"]["breakUp"]:
            k_lvls["r"].append({"p": ind["orb"]["high"], "l": "ORB↑"})
        if not ind["orb"]["breakDown"]:
            k_lvls["s"].append({"p": ind["orb"]["low"], "l": "ORB↓"})
        k_lvls["r"] = sorted(k_lvls["r"], key=lambda x: x["p"])[:5]
        k_lvls["s"] = sorted(k_lvls["s"], key=lambda x: x["p"], reverse=True)[:5]

    # ─── ATR-BASED CATALYST TRIGGER ───
    atr_pct_val = ind["atrPct"] or 2
    cat_threshold = round(atr_pct_val * 1.5, 2)
    needs_cat = abs(a_chg) > cat_threshold or div_spy is not None

    # ─── SCORING ───
    time_w = get_time_weight(sim_datetime or "2026-01-01 10:00:00")
    scoring = layered_score(
        patterns, aln, ind, div_spy, sec_rel, k_lvls,
        needs_cat, tM, tH, time_w,
    )

    return {
        "ticker": ticker,
        "error": False,
        "ind": ind,
        "patterns": patterns,
        "aln": aln,
        "tM": tM, "tH": tH, "tD": tD,
        "scoring": scoring,
        "chg": a_chg,
        "needsCat": needs_cat,
        "catThreshold": cat_threshold,
        "divSPY": div_spy,
        "secRel": sec_rel,
        "kLvls": k_lvls,
    }
