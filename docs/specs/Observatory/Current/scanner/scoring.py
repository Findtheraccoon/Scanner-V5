"""
Scanner v5 — Scoring Module
Based on v4.2.1 port, modified with empirical recalibration (Signal Observatory Fase 2b).

v5 formula: raw_score = trigger_sum + new_confirm_sum
Eliminated from score: volMult, time_w, bonus, risk_sum, VolSeq, SqExp.
Confirm weights remapped by marginal WR contribution.

Includes: time-of-day weight (informational), trend detection, pivots, key levels,
and the layered scoring engine.
"""
import math
from .indicators import ma


# ═══════════════════════════════════════
# TIME-OF-DAY WEIGHT
# ═══════════════════════════════════════

def get_time_weight(sim_datetime_str):
    """
    Time-of-day multiplier based on ET market hours.
    In backtest: parse simulated datetime string.
    
    Args:
        sim_datetime_str: "YYYY-MM-DD HH:MM:SS" in ET
    
    Returns:
        dict {w, label, zone}
    """
    try:
        time_part = sim_datetime_str.split(" ")[1] if " " in sim_datetime_str else "12:00"
        parts = time_part.split(":")
        h = int(parts[0])
        m = int(parts[1])
        mins = h * 60 + m

        if mins < 9 * 60 + 45 or mins >= 16 * 60:
            return {"w": 0, "label": "FUERA HORARIO", "zone": "closed"}
        if mins < 11 * 60 + 30:
            return {"w": 1.0, "label": "ÓPTIMO", "zone": "prime1"}
        if mins < 13 * 60:
            return {"w": 0.9, "label": "MODERADO", "zone": "moderate"}
        if mins < 14 * 60:
            return {"w": 0.8, "label": "ZONA MUERTA", "zone": "dead"}
        if mins < 15 * 60:
            return {"w": 1.0, "label": "ÓPTIMO", "zone": "prime2"}
        return {"w": 0.9, "label": "CUIDADO", "zone": "caution"}
    except Exception:
        return {"w": 1.0, "label": "—", "zone": "unknown"}


# ═══════════════════════════════════════
# TREND DETECTION
# ═══════════════════════════════════════

def trend(candles, ma20, ma40):
    """Strict trend: price > MA20 > MA40 = bullish."""
    if not candles or not ma20 or not ma40:
        return "neutral"
    p = candles[-1]["c"]
    if p > ma20 and ma20 > ma40:
        return "bullish"
    if p < ma20 and ma20 < ma40:
        return "bearish"
    return "neutral"


def trend_slope(candles, ma20):
    """
    Fallback trend using MA20 slope.
    Used when MA40 unavailable or when strict trend is neutral but
    price is above both MAs with rising MA20.
    """
    if not candles or not ma20:
        return "neutral"
    p = candles[-1]["c"]
    # Calculate previous MA20 (shifted 5 candles back)
    if len(candles) >= 25:
        ma20_prev = round(sum(c["c"] for c in candles[-25:-5]) / 20, 2)
    else:
        return "bullish" if p > ma20 else ("bearish" if p < ma20 else "neutral")

    if p > ma20 and ma20 > ma20_prev:
        return "bullish"
    if p < ma20 and ma20 < ma20_prev:
        return "bearish"
    return "neutral"


# ═══════════════════════════════════════
# PIVOTS & KEY LEVELS
# ═══════════════════════════════════════

def find_pivots(candles, lookback=50, tolerance=0.003):
    """
    Find pivot highs and lows, cluster nearby levels.
    Returns {r: [{lv, tx}], s: [{lv, tx}]}.
    """
    if not candles or len(candles) < lookback:
        return {"r": [], "s": []}
    
    rec = candles[-lookback:]
    hi = []
    lo = []
    for i in range(2, len(rec) - 2):
        if (rec[i]["h"] > rec[i - 1]["h"] and rec[i]["h"] > rec[i - 2]["h"]
                and rec[i]["h"] > rec[i + 1]["h"] and rec[i]["h"] > rec[i + 2]["h"]):
            hi.append(rec[i]["h"])
        if (rec[i]["l"] < rec[i - 1]["l"] and rec[i]["l"] < rec[i - 2]["l"]
                and rec[i]["l"] < rec[i + 1]["l"] and rec[i]["l"] < rec[i + 2]["l"]):
            lo.append(rec[i]["l"])

    def cluster(arr):
        if not arr:
            return []
        sorted_arr = sorted(arr)
        clusters = []
        group = [sorted_arr[0]]
        for i in range(1, len(sorted_arr)):
            if abs(sorted_arr[i] - group[0]) / group[0] < tolerance:
                group.append(sorted_arr[i])
            else:
                clusters.append({"lv": round(sum(group) / len(group), 2), "tx": len(group)})
                group = [sorted_arr[i]]
        clusters.append({"lv": round(sum(group) / len(group), 2), "tx": len(group)})
        return sorted(clusters, key=lambda x: x["tx"], reverse=True)[:4]

    return {"r": cluster(hi), "s": cluster(lo)}


def key_levels(ind, pivots_daily, pivots_1h, price):
    """
    Build sorted resistance and support levels from MAs, BBs, pivots, ORB.
    Returns {r: [{p, l}], s: [{p, l}]}.
    """
    all_levels = []

    # MAs as S/R
    if ind["ma20D"]:
        all_levels.append({"p": ind["ma20D"], "l": "MA20D", "t": "s" if price > ind["ma20D"] else "r"})
    if ind["ma40D"]:
        all_levels.append({"p": ind["ma40D"], "l": "MA40D", "t": "s" if price > ind["ma40D"] else "r"})
    if ind["ma200D"]:
        all_levels.append({"p": ind["ma200D"], "l": "MA200D", "t": "s" if price > ind["ma200D"] else "r"})

    # BB levels
    if ind["bbH"]:
        all_levels.append({"p": ind["bbH"]["u"], "l": "BB↑1H", "t": "r"})
        all_levels.append({"p": ind["bbH"]["m"], "l": "BBm1H", "t": "s" if price > ind["bbH"]["m"] else "r"})
        all_levels.append({"p": ind["bbH"]["l"], "l": "BB↓1H", "t": "s"})
    if ind["bbD"]:
        all_levels.append({"p": ind["bbD"]["u"], "l": "BB↑D", "t": "r"})
        all_levels.append({"p": ind["bbD"]["l"], "l": "BB↓D", "t": "s"})

    # Pivots
    for x in pivots_daily["r"]:
        all_levels.append({"p": x["lv"], "l": f"PivD({x['tx']}x)", "t": "r"})
    for x in pivots_daily["s"]:
        all_levels.append({"p": x["lv"], "l": f"PivD({x['tx']}x)", "t": "s"})
    for x in pivots_1h["r"]:
        all_levels.append({"p": x["lv"], "l": f"Piv1H({x['tx']}x)", "t": "r"})
    for x in pivots_1h["s"]:
        all_levels.append({"p": x["lv"], "l": f"Piv1H({x['tx']}x)", "t": "s"})

    # Deduplicate close levels
    deduped = []
    sorted_all = sorted(all_levels, key=lambda x: x["p"])
    for lv in sorted_all:
        existing = next((d for d in deduped if abs(d["p"] - lv["p"]) / lv["p"] < 0.002), None)
        if not existing:
            deduped.append(lv)
        elif "Piv" in lv["l"]:
            existing["l"] += " +" + lv["l"]

    resistances = sorted([l for l in deduped if l["p"] > price * 1.001], key=lambda x: x["p"])[:4]
    supports = sorted([l for l in deduped if l["p"] < price * 0.999], key=lambda x: x["p"], reverse=True)[:4]

    return {"r": resistances, "s": supports}


# ═══════════════════════════════════════
# v5 CONFIRM WEIGHT REMAPPING
# ═══════════════════════════════════════
# Based on marginal WR contribution (Fase 2a/2b empirical analysis).
# Original weights from patterns.py/engine.py are preserved in signal_components
# for traceability; the remapping only affects the score calculation.

NEW_CONFIRM_WEIGHTS = {
    "FzaRel":   4,   # +8.1% marginal WR
    "BBinf_1H": 3,   # +5.3%
    "VolHigh":  2,   # +3.2%
    "Gap":      1,   # +1.3%
    "BBsup_1H": 1,   # +0.7%
    "BBinf_D":  1,   # +0.6%
    "BBsup_D":  1,   # ±0.0%
    "DivSPY":   1,   # insufficient data, keep at 1
    "VolSeq":   0,   # -1.8% → eliminated
    "SqExp":    0,   # -4.3% → eliminated
}


def _categorize_confirm(desc):
    """Map confirm description string to weight category."""
    if desc.startswith("FzaRel"):         return "FzaRel"
    if desc.startswith("BB sup D"):       return "BBsup_D"
    if desc.startswith("BB inf D"):       return "BBinf_D"
    if desc.startswith("BB sup 1H"):      return "BBsup_1H"
    if desc.startswith("BB inf 1H"):      return "BBinf_1H"
    if desc.startswith("Vol creciente"):  return "VolSeq"
    if "x avg" in desc:                   return "VolHigh"
    if desc.startswith("Gap"):            return "Gap"
    if desc.startswith("Squeeze"):        return "SqExp"
    if desc.startswith("Div SPY"):        return "DivSPY"
    return None


# ═══════════════════════════════════════
# LAYERED SCORING ENGINE — v5 FORMULA
# ═══════════════════════════════════════
#
# v4.2.1: raw_score = trigger_sum × volMult × time_w + confirm_sum + bonus + risk_sum
# v5:     raw_score = trigger_sum + new_confirm_sum
#
# Eliminated from score (kept as informational fields):
#   - volMult (vol doesn't predict direction, only magnitude/speed)
#   - time_w  (dead zone WR ≥ prime1 — no discrimination)
#   - bonus   (near-pivot bonus not predictive)
#   - risk_sum (no risk type consistently reduces WR)
#   - VolSeq, SqExp (negative marginal contribution)

def layered_score(patterns, alignment, ind, div_spy, sec_rel, k_levels, needs_cat, tM, tH, time_w):
    """
    Layered scoring: structure → triggers → confirms → risks → final score.
    
    Args:
        patterns: list of pattern dicts from detect()
        alignment: dict {n, dir}
        ind: indicators dict
        div_spy: divergence info or None
        sec_rel: sector relative strength or None
        k_levels: key levels dict {r, s}
        needs_cat: bool — catalyst needed
        tM: 15M trend string
        tH: 1H trend string
        time_w: dict from get_time_weight()
    
    Returns:
        dict with score, conf, signal, layers, timeW, dir, blocked
    """
    layers = {
        "structure": {"pass": False, "reason": "", "override": False},
        "trigger": {"pass": False, "count": 0, "sum": 0},
        "confirm": {"sum": 0, "volMult": 1.0, "items": [], "bonus": 0},
        "risk": {"sum": 0, "blocked": False, "items": [], "conflictInfo": None},
    }

    # ─── LAYER 1: STRUCTURE (unchanged) ───
    if alignment["n"] >= 2:
        layers["structure"]["pass"] = True
        layers["structure"]["reason"] = f"{alignment['n']}/3 {alignment['dir']}"
    else:
        layers["structure"]["reason"] = f"{alignment['n']}/3 insuficiente"

    # Catalyst override: 15M+1H agree without daily
    if (not layers["structure"]["pass"] and needs_cat
            and tM and tH and tM != "neutral" and tM == tH):
        layers["structure"]["pass"] = True
        layers["structure"]["override"] = True
        layers["structure"]["reason"] = f"⚠️OVERRIDE {alignment['n']}/3 (15M+1H:{tM}, catalizador)"
        alignment = {"n": 2, "dir": "bearish" if tM == "bearish" else "bullish"}

    if not layers["structure"]["pass"]:
        return {
            "score": 0, "conf": "—", "signal": "NEUTRAL",
            "layers": layers, "timeW": time_w, "dir": None,
            "blocked": "Alineación insuficiente",
        }

    direction = "PUT" if alignment["dir"] == "bearish" else "CALL"

    # ─── LAYER 2: TRIGGERS (unchanged) ───
    triggers = [p for p in patterns if p["cat"] == "TRIGGER" and p["sg"] == direction]
    layers["trigger"]["count"] = len(triggers)
    layers["trigger"]["sum"] = sum(p["w"] for p in triggers)
    layers["trigger"]["pass"] = len(triggers) >= 1

    if not layers["trigger"]["pass"]:
        return {
            "score": 0, "conf": "—", "signal": "NEUTRAL",
            "layers": layers, "timeW": time_w, "dir": direction,
            "blocked": "Sin trigger de entrada",
        }

    # ─── LAYER 3: CONFIRMATIONS (v5: remapped weights) ───
    # volMult: still calculated for informational storage, NOT used in score
    vol_m = ind["volM"]
    if vol_m >= 2.0:
        layers["confirm"]["volMult"] = 1.5
    elif vol_m >= 1.5:
        layers["confirm"]["volMult"] = 1.3
    elif vol_m < 0.6:
        layers["confirm"]["volMult"] = 0.5
    else:
        layers["confirm"]["volMult"] = 1.0

    confirms = [p for p in patterns if p["cat"] == "CONFIRM" and p["sg"] in (direction, "CONFIRM")]

    # v5: remap confirm weights by category, deduplicate
    new_confirm_sum = 0
    seen_cats = set()
    for p in confirms:
        cat = _categorize_confirm(p["d"])
        if cat and cat not in seen_cats:
            seen_cats.add(cat)
            new_confirm_sum += NEW_CONFIRM_WEIGHTS.get(cat, 0)

    layers["confirm"]["sum"] = new_confirm_sum

    # Bonus: still calculated for informational storage, NOT used in score
    bonus = 0
    if sec_rel:
        if (direction == "PUT" and sec_rel["diff"] < -0.5) or (direction == "CALL" and sec_rel["diff"] > 0.5):
            bonus += 1
    if direction == "PUT":
        near_piv = next((l for l in k_levels["r"] if "Piv" in l["l"] and abs(ind["price"] - l["p"]) / l["p"] < 0.01), None)
    else:
        near_piv = next((l for l in k_levels["s"] if "Piv" in l["l"] and abs(ind["price"] - l["p"]) / l["p"] < 0.01), None)
    if near_piv:
        bonus += 1
    layers["confirm"]["bonus"] = bonus

    # ─── LAYER 4: RISKS (v5: informational only, NOT in score) ───
    risks = [p for p in patterns if p["cat"] == "RISK"]
    layers["risk"]["sum"] = sum(p["w"] for p in risks)
    layers["risk"]["items"] = risks

    # Conflict check: gate still active (structural, not a weight)
    put_w = sum(p["w"] for p in patterns if p["cat"] == "TRIGGER" and p["sg"] == "PUT")
    call_w = sum(p["w"] for p in patterns if p["cat"] == "TRIGGER" and p["sg"] == "CALL")
    conflict_diff = abs(put_w - call_w)
    if put_w > 0 and call_w > 0:
        if conflict_diff < 2:
            layers["risk"]["blocked"] = True
    layers["risk"]["conflictInfo"] = (
        {"put": put_w, "call": call_w, "diff": conflict_diff}
        if put_w > 0 and call_w > 0 else None
    )

    if layers["risk"]["blocked"]:
        return {
            "score": 0, "conf": "—", "signal": "NEUTRAL",
            "layers": layers, "timeW": time_w, "dir": direction,
            "blocked": f"Conflicto PUT({put_w})/CALL({call_w}) — diferencia {conflict_diff:.1f} < 2",
        }

    # ─── FINAL SCORE (v5 formula) ───
    raw_score = layers["trigger"]["sum"] + new_confirm_sum
    score = round(max(0, raw_score), 1)

    # v5 confidence thresholds — DEFINITIVOS (calibrados en Fase 2 Paso 4)
    # Franjas: REVISAR[2,4) B[4,7) A[7,10) A+[10,14) S[14,16) S+[16,∞)
    # Corte operativo: A (score ≥7) — MFE/MAE cruza 1.0x entre 6 (0.89x) y 7 (1.09x)
    # B+ eliminada: score 6 tiene peor WR que score 5 — no hay zona gris
    # S+ agregada: score ≥16 con 63.3% WR@30, 1.55x MFE/MAE (N=30)
    signal = "NEUTRAL"
    conf = "—"
    if score >= 16:
        signal = "SETUP"
        conf = "S+"
    elif score >= 14:
        signal = "SETUP"
        conf = "S"
    elif score >= 10:
        signal = "SETUP"
        conf = "A+"
    elif score >= 7:
        signal = "SETUP"
        conf = "A"
    elif score >= 4:
        signal = "REVISAR"
        conf = "B"
    elif score >= 2:
        signal = "REVISAR"
        conf = "REVISAR"

    return {
        "score": score, "conf": conf, "signal": signal,
        "layers": layers, "timeW": time_w, "dir": direction,
        "blocked": None,
    }
