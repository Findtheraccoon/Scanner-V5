"""
Signal Observatory — Multi-Ticker Replay Engine

Parameterized version of replay.py. Supports any ticker + optional benchmark
override for FzaRel computation. Same scanner/engine/scoring pipeline — only
the I/O and ticker/benchmark wiring changes.

Usage (as module):
    from backtest.multi_replay import run_backtest
    run_backtest({
        "ticker": "SPY",
        "ticker_1min_path": "data/spy_1min.json",
        "ticker_daily_path": "data/spy_daily.json",
        "spy_daily_path": "data/spy_daily.json",       # always SPY for DivSPY
        "bench_ticker": "QQQ",                          # optional; None → use BENCH map
        "bench_daily_path": "data/qqq_daily.json",      # optional
        "db_path": "observatory_SPY_bench_QQQ_v5_2.db",
    })

Invariants vs replay.py:
    - Scanner logic UNCHANGED (scanner/engine.py extended with optional params,
      fully backward compatible).
    - Same SIGNAL_THRESHOLD, TRACKING_MINUTES, warmup rules.
    - Output schema identical → existing analysis scripts read these DBs.
"""
import json
import time
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest.candle_builder import CandleBuilder
from backtest.db import (
    get_connection, create_schema, insert_session,
    insert_scan_log, insert_signal, insert_price_tracking,
)
from scanner.engine import analyze


# ═══════════════════════════════════════
# DEFAULTS
# ═══════════════════════════════════════
DEFAULT_SIGNAL_THRESHOLD = 2
DEFAULT_TRACKING_MINUTES = 120
DEFAULT_MIN_15M_HISTORY = 25
DEFAULT_MIN_1H_HISTORY = 25


def _load_json(path):
    with open(path) as f:
        return json.load(f)


def _daily_up_to(candles_daily, sim_date):
    """Slice daily candles up to sim_date (no look-ahead)."""
    return [c for c in candles_daily if c["dt"] <= sim_date]


def run_backtest(config):
    """
    Parameterized backtest.

    Required config keys:
        ticker: symbol string (e.g. "SPY")
        ticker_1min_path: path to 1min candles JSON
        ticker_daily_path: path to daily candles JSON
        spy_daily_path: path to SPY daily (always needed for DivSPY)
        db_path: output SQLite path

    Optional config keys:
        bench_ticker: explicit benchmark for FzaRel (e.g. "QQQ").
                      If omitted, engine falls back to BENCH map.
        bench_daily_path: benchmark daily candles path.
                          Required if bench_ticker is set AND benchmark != SPY.
                          If benchmark == SPY, can reuse spy_daily_path.
        start_date / end_date: "YYYY-MM-DD" scan window
        signal_threshold: default 2
        tracking_minutes: default 120
        verbose: bool, default True
    """
    ticker = config["ticker"]
    verbose = config.get("verbose", True)
    signal_threshold = config.get("signal_threshold", DEFAULT_SIGNAL_THRESHOLD)
    tracking_minutes = config.get("tracking_minutes", DEFAULT_TRACKING_MINUTES)
    start_date = config.get("start_date")
    end_date = config.get("end_date")

    if verbose:
        print(f"\n{'='*60}")
        print(f"  MULTI-TICKER REPLAY — {ticker}")
        print(f"{'='*60}")
        print(f"  Loading data...")

    # ─── Load data ───
    ticker_1m = _load_json(config["ticker_1min_path"])
    ticker_daily = _load_json(config["ticker_daily_path"])
    spy_daily = _load_json(config["spy_daily_path"])

    bench_ticker = config.get("bench_ticker")
    bench_daily = None
    if config.get("bench_daily_path"):
        bench_daily = _load_json(config["bench_daily_path"])
    elif bench_ticker == "SPY":
        # Shortcut: if bench is SPY, reuse SPY daily
        bench_daily = spy_daily

    if verbose:
        print(f"  {ticker} 1min:   {len(ticker_1m):,} candles")
        print(f"  {ticker} daily:  {len(ticker_daily):,} candles")
        print(f"  SPY daily:       {len(spy_daily):,} candles")
        if bench_ticker:
            bench_n = len(bench_daily) if bench_daily else 0
            print(f"  BENCH [{bench_ticker}]:  {bench_n:,} candles (explicit override)")
        else:
            print(f"  BENCH: fallback to engine BENCH map")

    # ─── DB setup ───
    db_path = config["db_path"]
    if os.path.exists(db_path):
        os.remove(db_path)
        if verbose:
            print(f"  Removed preexisting DB: {db_path}")

    conn = get_connection(db_path)
    create_schema(conn)

    # ─── State ───
    builder = CandleBuilder()
    active_tracking = []
    current_session_id = None
    current_date = None
    scan_count = 0
    signal_count = 0
    warmup_done = False
    total_candles = len(ticker_1m)
    t_start = time.time()

    if verbose:
        print(f"\n  Starting replay: {ticker_1m[0]['dt']} → {ticker_1m[-1]['dt']}")
        if start_date:
            print(f"    Scanning from: {start_date}")
        if end_date:
            print(f"    Scanning until: {end_date}")
        print()

    # ─── Main loop ───
    for i, candle_1m in enumerate(ticker_1m):
        dt = candle_1m["dt"]
        sim_date = dt.split(" ")[0]

        if end_date and sim_date > end_date:
            break

        result = builder.add(candle_1m)

        # New day
        if sim_date != current_date:
            current_date = sim_date
            daily_slice = _daily_up_to(ticker_daily, sim_date)
            open_price = candle_1m["o"]
            prev_close = daily_slice[-2]["c"] if len(daily_slice) >= 2 else None
            current_session_id = insert_session(conn, sim_date, open_price, prev_close)

        # Price tracking for active signals
        still_active = []
        for trk in active_tracking:
            if trk["minutes_tracked"] <= tracking_minutes:
                trk["max_fav"], trk["max_adv"] = insert_price_tracking(
                    conn, trk["signal_id"], trk["minutes_tracked"],
                    candle_1m["c"], candle_1m["v"],
                    trk["price_at_signal"], trk["direction"],
                    trk["max_fav"], trk["max_adv"],
                )
                trk["minutes_tracked"] += 1
                if trk["minutes_tracked"] <= tracking_minutes:
                    still_active.append(trk)
        active_tracking = still_active

        if i % 100 == 0:
            conn.commit()

        # Scanner trigger: 15M completed
        if result["completed_15m"] is None:
            continue

        candles_15m = builder.get_15m_candles(include_current=True)
        candles_1h = builder.get_1h_candles(include_current=True)

        if len(candles_15m) < DEFAULT_MIN_15M_HISTORY or len(candles_1h) < DEFAULT_MIN_1H_HISTORY:
            if not warmup_done:
                continue
        else:
            if not warmup_done:
                warmup_done = True
                if verbose:
                    print(f"  Warmup complete at {dt} ({len(candles_15m)} x 15M, {len(candles_1h)} x 1H)")

        if start_date and sim_date < start_date:
            continue

        # ─── Run scanner ───
        daily_slice = _daily_up_to(ticker_daily, sim_date)
        spy_slice = _daily_up_to(spy_daily, sim_date)
        bench_slice = _daily_up_to(bench_daily, sim_date) if bench_daily else None

        scan_result = analyze(
            ticker=ticker,
            candles_daily=daily_slice,
            candles_1h=candles_1h,
            candles_15m=candles_15m,
            spy_daily=spy_slice,
            sim_datetime=dt,
            sim_date=sim_date,
            bench_ticker=bench_ticker,
            bench_daily=bench_slice,
        )

        if scan_result.get("error"):
            continue

        scoring = scan_result["scoring"]
        score = scoring["score"]
        conf = scoring["conf"]
        direction = scoring.get("dir")
        signal_generated = score >= signal_threshold and conf not in ("—",)

        insert_scan_log(
            conn, current_session_id, dt, ticker,
            scan_result["ind"]["price"], score, conf, direction,
            signal_generated,
        )
        scan_count += 1

        if signal_generated:
            signal_id = insert_signal(conn, current_session_id, scan_result, dt, ticker)
            signal_count += 1
            active_tracking.append({
                "signal_id": signal_id,
                "price_at_signal": scan_result["ind"]["price"],
                "direction": direction,
                "minutes_tracked": 0,
                "max_fav": 0.0,
                "max_adv": 0.0,
            })

        if verbose and scan_count % 500 == 0:
            elapsed = time.time() - t_start
            pct = (i + 1) / total_candles * 100
            print(f"  {sim_date} | {pct:.0f}% | scans:{scan_count} signals:{signal_count} tracking:{len(active_tracking)} | {elapsed:.0f}s")

    conn.commit()
    elapsed = time.time() - t_start

    # ─── Summary ───
    total_scans = conn.execute("SELECT COUNT(*) FROM scan_log").fetchone()[0]
    total_signals = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    total_tracking = conn.execute("SELECT COUNT(*) FROM price_tracking").fetchone()[0]
    total_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    summary = {
        "ticker": ticker,
        "bench_ticker": bench_ticker,
        "db_path": db_path,
        "elapsed_s": elapsed,
        "sessions": total_sessions,
        "scans": total_scans,
        "signals": total_signals,
        "tracking_points": total_tracking,
    }

    if verbose:
        print(f"\n{'='*60}")
        print(f"  REPLAY COMPLETE — {ticker} — {elapsed:.1f}s")
        print(f"{'='*60}")
        print(f"  Sessions:   {total_sessions}")
        print(f"  Scans:      {total_scans}")
        print(f"  Signals:    {total_signals} (score ≥ {signal_threshold})")
        print(f"  Tracking:   {total_tracking} price points")

        if total_signals > 0:
            by_conf = conn.execute(
                "SELECT confidence, COUNT(*) as cnt FROM signals GROUP BY confidence ORDER BY confidence"
            ).fetchall()
            print(f"\n  By confidence:")
            for row in by_conf:
                print(f"    {row['confidence']}: {row['cnt']}")

        print(f"\n  DB: {db_path}")

    conn.close()
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Multi-ticker backtest replay")
    parser.add_argument("--ticker", required=True, help="Ticker symbol (e.g. SPY)")
    parser.add_argument("--ticker-1min", required=True, help="Path to ticker 1min JSON")
    parser.add_argument("--ticker-daily", required=True, help="Path to ticker daily JSON")
    parser.add_argument("--spy-daily", required=True, help="Path to SPY daily JSON (for DivSPY)")
    parser.add_argument("--bench-ticker", default=None, help="Explicit benchmark ticker override")
    parser.add_argument("--bench-daily", default=None, help="Path to benchmark daily JSON")
    parser.add_argument("--db", required=True, help="Output DB path")
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    args = parser.parse_args()

    config = {
        "ticker": args.ticker,
        "ticker_1min_path": args.ticker_1min,
        "ticker_daily_path": args.ticker_daily,
        "spy_daily_path": args.spy_daily,
        "bench_ticker": args.bench_ticker,
        "bench_daily_path": args.bench_daily,
        "db_path": args.db,
        "start_date": args.start,
        "end_date": args.end,
    }
    run_backtest(config)
