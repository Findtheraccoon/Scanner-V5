"""
Scanner v4.2.1 — Pattern Detection Module (Python Port)
Ported from scanner_v4_2_1.html lines 388-478.

Detects: triggers (entry signals), confirmations, risks, squeeze.
Each pattern is a dict: {tf, d, sg, w, cat, age}
  tf=timeframe, d=description, sg=signal direction, 
  w=weight, cat=category, age=candles back
"""


def decay_weight(age):
    """Decay factor for older patterns."""
    if age <= 1:
        return 1.0
    if age <= 3:
        return 0.85
    if age <= 5:
        return 0.7
    if age <= 10:
        return 0.4
    return 0.2


def detect(candles_15m, candles_1h, candles_daily, ind):
    """
    Detect all patterns across timeframes.
    
    Args:
        candles_15m: list of 15M candle dicts (oldest→newest)
        candles_1h: list of 1H candle dicts
        candles_daily: list of daily candle dicts
        ind: dict from calc_indicators()
    
    Returns:
        list of pattern dicts
    """
    P = []
    if not candles_15m or not candles_1h or not candles_daily:
        return P

    # ─── 15M PATTERNS (with decay, last 5 candles) ───
    for age in range(min(5, len(candles_15m) - 1)):
        idx = len(candles_15m) - 1 - age
        L = candles_15m[idx]
        pv = candles_15m[idx - 1] if idx > 0 else None
        if not L or not pv:
            continue

        decay = decay_weight(age)
        rng = L["h"] - L["l"]
        body = abs(L["o"] - L["c"])
        upper_wick = L["h"] - max(L["o"], L["c"])
        lower_wick = min(L["o"], L["c"]) - L["l"]
        bull = L["c"] >= L["o"]
        age_lbl = f" ({age}v atrás)" if age > 0 else ""

        # ─── TRIGGERS (layer 2) ───

        # BB-dependent patterns ONLY on current candle (age=0)
        if age == 0 and rng > 0 and body / rng < 0.12:
            if ind["bbM"] and L["h"] >= ind["bbM"]["u"] * 0.998:
                P.append({"tf": "15M", "d": "Doji BB sup", "sg": "PUT", "w": 2, "cat": "TRIGGER", "age": age})
            if ind["bbM"] and L["l"] <= ind["bbM"]["l"] * 1.002:
                P.append({"tf": "15M", "d": "Doji BB inf", "sg": "CALL", "w": 2, "cat": "TRIGGER", "age": age})

        # Pure rejection wicks (any age, no BB dependency)
        if rng > 0 and upper_wick / rng > 0.6:
            P.append({
                "tf": "15M",
                "d": f"Rechazo sup {upper_wick / rng * 100:.0f}%{age_lbl}",
                "sg": "PUT", "w": round(2 * decay, 1), "cat": "TRIGGER", "age": age,
            })
        if rng > 0 and lower_wick / rng > 0.6:
            P.append({
                "tf": "15M",
                "d": f"Rechazo inf {lower_wick / rng * 100:.0f}%{age_lbl}",
                "sg": "CALL", "w": round(2 * decay, 1), "cat": "TRIGGER", "age": age,
            })

        # Hammer / Shooting Star — only current candle, BB-dependent
        if age == 0 and rng > 0:
            if lower_wick > body * 2 and upper_wick < body * 0.5:
                if ind["bbM"] and L["l"] <= ind["bbM"]["l"] * 1.005:
                    P.append({"tf": "15M", "d": "Hammer", "sg": "CALL", "w": 2, "cat": "TRIGGER", "age": age})
            if upper_wick > body * 2 and lower_wick < body * 0.5:
                if ind["bbM"] and L["h"] >= ind["bbM"]["u"] * 0.995:
                    P.append({"tf": "15M", "d": "Shooting Star", "sg": "PUT", "w": 2, "cat": "TRIGGER", "age": age})

        # Engulfing 15M (with decay)
        pv_body = abs(pv["o"] - pv["c"])
        pv_bull = pv["c"] >= pv["o"]
        if bull and not pv_bull and L["o"] <= pv["c"] and L["c"] >= pv["o"] and body > pv_body * 1.1:
            P.append({
                "tf": "15M", "d": f"Envolvente alcista{age_lbl}",
                "sg": "CALL", "w": round(3 * decay, 1), "cat": "TRIGGER", "age": age,
            })
        if not bull and pv_bull and L["o"] >= pv["c"] and L["c"] <= pv["o"] and body > pv_body * 1.1:
            P.append({
                "tf": "15M", "d": f"Envolvente bajista{age_lbl}",
                "sg": "PUT", "w": round(3 * decay, 1), "cat": "TRIGGER", "age": age,
            })

    # ─── 1H ENGULFING (current only, no decay) ───
    if len(candles_1h) >= 2:
        lH = candles_1h[-1]
        pH = candles_1h[-2]
        hB = lH["c"] >= lH["o"]
        hPB = pH["c"] >= pH["o"]
        hBd = abs(lH["o"] - lH["c"])
        hPBd = abs(pH["o"] - pH["c"])
        if hB and not hPB and lH["o"] <= pH["c"] and lH["c"] >= pH["o"] and hBd > hPBd * 1.1:
            P.append({"tf": "1H", "d": "Envolvente alcista 1H", "sg": "CALL", "w": 3, "cat": "TRIGGER", "age": 0})
        if not hB and hPB and lH["o"] >= pH["c"] and lH["c"] <= pH["o"] and hBd > hPBd * 1.1:
            P.append({"tf": "1H", "d": "Envolvente bajista 1H", "sg": "PUT", "w": 3, "cat": "TRIGGER", "age": 0})

    # ─── DOUBLE TOP / BOTTOM (last 20 candles 15M) ───
    if len(candles_15m) >= 20:
        rc = candles_15m[-20:]
        hi = []
        lo = []
        for i in range(1, len(rc) - 1):
            if rc[i]["h"] > rc[i - 1]["h"] and rc[i]["h"] > rc[i + 1]["h"]:
                hi.append({"v": rc[i]["h"], "i": i})
            if rc[i]["l"] < rc[i - 1]["l"] and rc[i]["l"] < rc[i + 1]["l"]:
                lo.append({"v": rc[i]["l"], "i": i})
        if len(hi) >= 2:
            a, b = hi[-2], hi[-1]
            if abs(a["v"] - b["v"]) / a["v"] < 0.005 and b["i"] - a["i"] >= 3:
                P.append({"tf": "15M", "d": f"Doble techo ~${a['v']:.2f}", "sg": "PUT", "w": 3, "cat": "TRIGGER", "age": 0})
        if len(lo) >= 2:
            a, b = lo[-2], lo[-1]
            if abs(a["v"] - b["v"]) / a["v"] < 0.005 and b["i"] - a["i"] >= 3:
                P.append({"tf": "15M", "d": f"Doble piso ~${a['v']:.2f}", "sg": "CALL", "w": 3, "cat": "TRIGGER", "age": 0})

    # ─── MA CROSS 1H ───
    if len(candles_1h) >= 42:
        from .indicators import ma as _ma
        m2n = _ma(candles_1h, 20)
        m4n = _ma(candles_1h, 40)
        m2p = _ma(candles_1h[:-2], 20)
        m4p = _ma(candles_1h[:-2], 40)
        if m2n and m4n and m2p and m4p:
            if m2p < m4p and m2n > m4n:
                P.append({"tf": "1H", "d": "Cruce alcista MA20/40", "sg": "CALL", "w": 2, "cat": "TRIGGER", "age": 0})
            if m2p > m4p and m2n < m4n:
                P.append({"tf": "1H", "d": "Cruce bajista MA20/40", "sg": "PUT", "w": 2, "cat": "TRIGGER", "age": 0})

    # ─── CONFIRMATIONS (layer 3) ───
    L = candles_15m[-1]

    # BB extremes
    if ind["bbH"] and L["c"] >= ind["bbH"]["u"]:
        P.append({"tf": "1H", "d": f"BB sup 1H (${ind['bbH']['u']})", "sg": "PUT", "w": 1, "cat": "CONFIRM", "age": 0})
    if ind["bbH"] and L["c"] <= ind["bbH"]["l"]:
        P.append({"tf": "1H", "d": f"BB inf 1H (${ind['bbH']['l']})", "sg": "CALL", "w": 3, "cat": "CONFIRM", "age": 0})
    if ind["bbD"] and L["c"] >= ind["bbD"]["u"]:
        P.append({"tf": "D", "d": f"BB sup D (${ind['bbD']['u']})", "sg": "PUT", "w": 1, "cat": "CONFIRM", "age": 0})
    if ind["bbD"] and L["c"] <= ind["bbD"]["l"]:
        P.append({"tf": "D", "d": f"BB inf D (${ind['bbD']['l']})", "sg": "CALL", "w": 1, "cat": "CONFIRM", "age": 0})

    # High volume
    if ind["volM"] > 1.5:
        P.append({"tf": "15M", "d": f"Vol {ind['volM']}x avg", "sg": "CONFIRM", "w": 2, "cat": "CONFIRM", "age": 0})

    # Volume sequence growing
    if ind["volSeqM"]["growing"]:
        P.append({"tf": "15M", "d": f"Vol creciente {ind['volSeqM']['count'] + 1} velas", "sg": "CONFIRM", "w": 0, "cat": "CONFIRM", "age": 0})

    # BB Squeeze
    if ind["bbSqH"] and ind["bbSqH"]["isSqueeze"]:
        P.append({"tf": "1H", "d": f"BB Squeeze (ancho p{ind['bbSqH']['percentile']})", "sg": "CONFIRM", "w": 0, "cat": "SQUEEZE", "age": 0})
    if ind["bbSqH"] and ind["bbSqH"]["isSqueeze"] and ind["bbSqH"]["isExpanding"]:
        P.append({"tf": "1H", "d": "Squeeze → Expansión (ruptura)", "sg": "CONFIRM", "w": 0, "cat": "CONFIRM", "age": 0})

    # ─── RISKS (layer 4) ───
    if len(candles_15m) >= 2:
        pv = candles_15m[-2]
        # Low volume bounce
        if ind["volM"] < 0.6 and L["c"] > pv["c"]:
            P.append({"tf": "15M", "d": f"Rebote vol bajo ({ind['volM']}x)", "sg": "WARN", "w": -2, "cat": "RISK", "age": 0})
        # Declining volume on bounce
        if ind["volSeqM"]["declining"] and L["c"] > pv["c"]:
            P.append({"tf": "15M", "d": "Vol declinante en rebote", "sg": "WARN", "w": -1, "cat": "RISK", "age": 0})

    # Fakeout detection (BB)
    if len(candles_15m) >= 3:
        c3 = candles_15m[-3]
        c2 = candles_15m[-2]
        c1 = candles_15m[-1]
        # Fakeout above BB upper
        if ind["bbH"] and c2["h"] > ind["bbH"]["u"] and c2["c"] < ind["bbH"]["u"] and c1["c"] < ind["bbH"]["u"]:
            P.append({"tf": "15M", "d": "Fakeout sobre BB sup 1H", "sg": "WARN", "w": -3, "cat": "RISK", "age": 0})
        # Fakeout below BB lower
        if ind["bbH"] and c2["l"] < ind["bbH"]["l"] and c2["c"] > ind["bbH"]["l"] and c1["c"] > ind["bbH"]["l"]:
            P.append({"tf": "15M", "d": "Fakeout bajo BB inf 1H", "sg": "WARN", "w": -3, "cat": "RISK", "age": 0})

    return P
