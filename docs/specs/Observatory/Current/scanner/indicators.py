"""
Scanner v4.2.1 — Indicators Module (Python Port)
Ported from scanner_v4_2_1.html lines 183-335.

Each candle is a dict: {o, h, l, c, v, dt}
  o=open, h=high, l=low, c=close, v=volume, dt=datetime string

All functions receive lists of candle dicts sorted oldest→newest.
"""
import math
from statistics import median as _std_median


# ═══════════════════════════════════════
# BASIC INDICATORS
# ═══════════════════════════════════════

def ma(candles, period):
    """Simple Moving Average over last `period` candles' close."""
    if not candles or len(candles) < period:
        return None
    return round(sum(c["c"] for c in candles[-period:]) / period, 2)


def bb(candles, period=20, mult=2):
    """Bollinger Bands: {u, m, l, w} or None."""
    if not candles or len(candles) < period:
        return None
    s = candles[-period:]
    mn = sum(c["c"] for c in s) / period
    st = math.sqrt(sum((c["c"] - mn) ** 2 for c in s) / period)
    return {
        "u": round(mn + mult * st, 2),
        "m": round(mn, 2),
        "l": round(mn - mult * st, 2),
        "w": round(2 * mult * st, 2),
    }


def median(arr):
    """Median of a numeric list."""
    if not arr:
        return 0
    s = sorted(arr)
    mid = len(s) // 2
    if len(s) % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


def pct_change(candles, n=1):
    """Percent change between current close and N candles back."""
    if not candles or len(candles) < n + 1:
        return 0
    prev = candles[-1 - n]["c"]
    cur = candles[-1]["c"]
    return round((cur - prev) / prev * 100, 2) if prev > 0 else 0


# ═══════════════════════════════════════
# TODAY CANDLES (intraday filtering)
# ═══════════════════════════════════════

def today_candles(candles, sim_date=None):
    """
    Filter candles belonging to 'today'.
    In backtest: sim_date is the simulated date string (YYYY-MM-DD).
    In live: uses last candle's date.
    """
    if not candles:
        return []
    if sim_date is None:
        last_dt = candles[-1]["dt"]
        sim_date = last_dt.split(" ")[0] if " " in last_dt else last_dt.split("T")[0]
    return [c for c in candles if c["dt"] and c["dt"].startswith(sim_date)]


# ═══════════════════════════════════════
# VOLUME RATIO (mediana, same-day)
# ═══════════════════════════════════════

def vol_ratio(candles, today_only=False, sim_date=None):
    """
    Volume ratio: penultimate completed candle vs median of completed candles.
    
    For intraday TFs (15M, 1H) with today_only=True:
      - Uses only same-day candles for apples-to-apples comparison.
      - If <3 completed candles today → neutral (1.0).
      - Median eliminates outliers (opening candle 9:30).
    
    For daily: original 10-period logic.
    """
    if today_only:
        tc = today_candles(candles, sim_date)
        if len(tc) < 4:  # <3 completed + 1 current → neutral
            return 1.0
        completed = tc[-2]
        vols = [c["v"] for c in tc[:-2]]
        med = median(vols)
        return round(completed["v"] / med, 2) if med > 0 else 1.0
    
    # Daily fallback: original 10-period logic
    if not candles or len(candles) < 12:
        return 1.0
    completed = candles[-2]
    vols = [c["v"] for c in candles[-12:-2]]
    med = median(vols)
    return round(completed["v"] / med, 2) if med > 0 else 1.0


def vol_ratio_projected(candles, interval_mins, today_only=False, sim_date=None):
    """
    Projected volume of current (incomplete) candle — informational only.
    Returns dict {projected, raw, confidence} or None.
    """
    if today_only:
        tc = today_candles(candles, sim_date)
        if len(tc) < 4:
            return None
        vols = [c["v"] for c in tc[:-1]]
        med = median(vols)
        if med <= 0:
            return None
        current_vol = tc[-1]["v"]
        raw_ratio = current_vol / med
        confidence = "high" if raw_ratio >= 0.5 else "low"
        return {"projected": round(raw_ratio, 2), "raw": current_vol, "confidence": confidence}
    
    if not candles or len(candles) < 12:
        return None
    vols = [c["v"] for c in candles[-11:-1]]
    med = median(vols)
    if med <= 0:
        return None
    current_vol = candles[-1]["v"]
    raw_ratio = current_vol / med
    confidence = "high" if raw_ratio >= 0.5 else "low"
    return {"projected": round(raw_ratio, 2), "raw": current_vol, "confidence": confidence}


# ═══════════════════════════════════════
# ATR (Average True Range)
# ═══════════════════════════════════════

def atr(candles, period=14):
    """ATR over daily candles. Returns dollar value or None."""
    if not candles or len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        tr = max(
            candles[i]["h"] - candles[i]["l"],
            abs(candles[i]["h"] - candles[i - 1]["c"]),
            abs(candles[i]["l"] - candles[i - 1]["c"]),
        )
        trs.append(tr)
    if len(trs) < period:
        return None
    return round(sum(trs[-period:]) / period, 2)


def atr_pct(candles, period=14):
    """ATR as percentage of current price."""
    a = atr(candles, period)
    if a is None:
        return None
    price = candles[-1]["c"]
    return round(a / price * 100, 2) if price > 0 else None


# ═══════════════════════════════════════
# BB WIDTH (Squeeze Detection)
# ═══════════════════════════════════════

def bb_width(candles, period=20):
    """
    BB squeeze detection by percentile of width over last 20 readings.
    Returns {current, min20, percentile, isSqueeze, isExpanding} or None.
    """
    if not candles or len(candles) < period + 20:
        return None
    widths = []
    for i in range(period, len(candles) + 1):
        b = bb(candles[:i], period)
        if b:
            widths.append(b["w"])
    if len(widths) < 20:
        return None
    current = widths[-1]
    min20 = min(widths[-20:])
    max20 = max(widths[-20:])
    rng = max20 - min20 or 1
    percentile = round((current - min20) / rng * 100)
    return {
        "current": round(current, 2),
        "min20": round(min20, 2),
        "percentile": percentile,
        "isSqueeze": percentile < 15,
        "isExpanding": (
            len(widths) >= 3
            and widths[-1] > widths[-2]
            and widths[-2] > widths[-3]
        ),
    }


# ═══════════════════════════════════════
# VOLUME SEQUENCE
# ═══════════════════════════════════════

def vol_sequence(candles, n=4):
    """
    Volume sequence: checks if last N completed candles have 
    growing or declining volume (75% threshold).
    Excludes last incomplete candle.
    Returns {growing, declining, count}.
    """
    if not candles or len(candles) < n + 2:
        return {"growing": False, "declining": False, "count": 0}
    completed = candles[-(n + 1):-1]  # last N completed (exclude current)
    g_count = 0
    d_count = 0
    for i in range(1, len(completed)):
        if completed[i]["v"] > completed[i - 1]["v"] * 0.95:
            g_count += 1
        if completed[i]["v"] < completed[i - 1]["v"] * 1.05:
            d_count += 1
    threshold = math.ceil((n - 1) * 0.75)
    growing = g_count >= threshold
    declining = d_count >= threshold
    if growing:
        return {"growing": True, "declining": False, "count": g_count}
    if declining:
        return {"growing": False, "declining": True, "count": -d_count}
    return {"growing": False, "declining": False, "count": 0}


# ═══════════════════════════════════════
# GAP ANALYSIS
# ═══════════════════════════════════════

def gap(candles_daily, atr_pct_val):
    """
    Gap analysis: today's open vs yesterday's close.
    Significant if > 0.5×ATR.
    Returns {pct, significant, dir} or None.
    """
    if not candles_daily or len(candles_daily) < 2:
        return None
    today = candles_daily[-1]
    yesterday = candles_daily[-2]
    gap_pct = round((today["o"] - yesterday["c"]) / yesterday["c"] * 100, 2)
    atr_val = atr_pct_val or 2
    significant = abs(gap_pct) > atr_val * 0.5
    return {
        "pct": gap_pct,
        "significant": significant,
        "dir": "bullish" if gap_pct > 0 else "bearish",
    }


# ═══════════════════════════════════════
# OPENING RANGE BREAKOUT (ORB)
# ═══════════════════════════════════════

def orb(candles_15m, sim_date=None):
    """
    Opening Range Breakout: high/low of first 2 candles of 15M (9:30-10:00).
    Returns {high, low, breakUp, breakDown} or None.
    """
    if not candles_15m or len(candles_15m) < 10:
        return None
    
    tc = today_candles(candles_15m, sim_date)
    if len(tc) < 3:  # need at least ORB + 1 candle after
        return None
    
    orb_candles = tc[:2]  # first 2 candles = 30min
    orb_high = max(orb_candles[0]["h"], orb_candles[1]["h"])
    orb_low = min(orb_candles[0]["l"], orb_candles[1]["l"])
    current = candles_15m[-1]
    break_up = current["c"] > orb_high
    break_down = current["c"] < orb_low
    return {
        "high": round(orb_high, 2),
        "low": round(orb_low, 2),
        "breakUp": break_up,
        "breakDown": break_down,
    }


# ═══════════════════════════════════════
# COMPOSITE: Calculate All Indicators
# ═══════════════════════════════════════

def calc_indicators(candles_daily, candles_1h, candles_15m, sim_date=None):
    """
    Calculate all indicators for one asset. 
    Equivalent to JS calcInd().
    Returns dict with all indicator values.
    """
    price = candles_15m[-1]["c"] if candles_15m else 0
    ma200d = ma(candles_daily, 200)
    atr_pct_val = atr_pct(candles_daily)
    
    return {
        "price": price,
        # Moving averages
        "ma20D": ma(candles_daily, 20),
        "ma40D": ma(candles_daily, 40),
        "ma100D": ma(candles_daily, 100),
        "ma200D": ma200d,
        "ma20H": ma(candles_1h, 20),
        "ma40H": ma(candles_1h, 40),
        "ma20M": ma(candles_15m, 20),
        # Bollinger Bands
        "bbD": bb(candles_daily),
        "bbH": bb(candles_1h),
        "bbM": bb(candles_15m),
        # Volume
        "volM": vol_ratio(candles_15m, today_only=True, sim_date=sim_date),
        "volH": vol_ratio(candles_1h, today_only=True, sim_date=sim_date),
        "volProjM": vol_ratio_projected(candles_15m, 15, today_only=True, sim_date=sim_date),
        # Change
        "chgD": pct_change(candles_daily, 1),
        # Distance to MA200
        "dMA200": round((price - ma200d) / ma200d * 100, 2) if ma200d else None,
        # ATR
        "atr": atr(candles_daily),
        "atrPct": atr_pct_val,
        # BB Squeeze
        "bbSqM": bb_width(candles_15m),
        "bbSqH": bb_width(candles_1h),
        # Volume Sequence
        "volSeqM": vol_sequence(candles_15m, 4),
        "volSeqH": vol_sequence(candles_1h, 3),
        # GAP
        "gap": gap(candles_daily, atr_pct_val),
        # ORB
        "orb": orb(candles_15m, sim_date),
    }
