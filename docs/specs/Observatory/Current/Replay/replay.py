"""
Signal Observatory — Replay Engine
Main backtest loop: minute-by-minute replay of historical data.

Feeds candle builder → runs scanner on 15M completion → logs signals → tracks prices.
"""
import json
import time
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from backtest.candle_builder import CandleBuilder
from backtest.db import (
    get_connection, create_schema, insert_session,
    insert_scan_log, insert_signal, insert_price_tracking,
)
from scanner.engine import analyze


# ═══════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════
TICKER = "QQQ"
SIGNAL_THRESHOLD = 2      # Score ≥ 2 (B and B+)
TRACKING_MINUTES = 120     # Post-signal price tracking
MIN_15M_HISTORY = 25       # Min 15M candles before scanning (for MAs/patterns)
MIN_1H_HISTORY = 25        # Min 1H candles before scanning
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "observatory_v5_2.db")


def load_data():
    """Load historical candle data."""
    print("Loading data...")
    with open(os.path.join(DATA_DIR, "qqq_1min.json")) as f:
        qqq_1m = json.load(f)
    with open(os.path.join(DATA_DIR, "qqq_daily.json")) as f:
        qqq_daily = json.load(f)
    with open(os.path.join(DATA_DIR, "spy_daily.json")) as f:
        spy_daily = json.load(f)

    print(f"  QQQ 1min:  {len(qqq_1m):,} candles")
    print(f"  QQQ daily: {len(qqq_daily):,} candles")
    print(f"  SPY daily: {len(spy_daily):,} candles")
    return qqq_1m, qqq_daily, spy_daily


def daily_up_to(candles_daily, sim_date):
    """Slice daily candles up to sim_date (no look-ahead)."""
    return [c for c in candles_daily if c["dt"] <= sim_date]


def run_backtest(start_date=None, end_date=None):
    """
    Main backtest loop.
    
    Args:
        start_date: "YYYY-MM-DD" — skip days before this (still builds candle history)
        end_date: "YYYY-MM-DD" — stop after this date
    """
    qqq_1m, qqq_daily, spy_daily = load_data()

    conn = get_connection(DB_PATH)
    create_schema(conn)

    builder = CandleBuilder()

    # Active signals needing price tracking: [{signal_id, price_at_signal, direction, minutes_tracked, max_fav, max_adv}]
    active_tracking = []

    current_session_id = None
    current_date = None
    scan_count = 0
    signal_count = 0
    tracking_inserts = 0
    warmup_done = False

    total_candles = len(qqq_1m)
    start_time = time.time()

    print(f"\nStarting replay: {qqq_1m[0]['dt']} → {qqq_1m[-1]['dt']}")
    if start_date:
        print(f"  Scanning from: {start_date}")
    if end_date:
        print(f"  Scanning until: {end_date}")
    print()

    for i, candle_1m in enumerate(qqq_1m):
        dt = candle_1m["dt"]
        sim_date = dt.split(" ")[0]

        # ─── End date check ───
        if end_date and sim_date > end_date:
            break

        # ─── Feed candle builder ───
        result = builder.add(candle_1m)

        # ─── New day handling ───
        if sim_date != current_date:
            current_date = sim_date

            # Find open/prev_close for session
            daily_slice = daily_up_to(qqq_daily, sim_date)
            open_price = candle_1m["o"]
            prev_close = daily_slice[-2]["c"] if len(daily_slice) >= 2 else None

            current_session_id = insert_session(conn, sim_date, open_price, prev_close)

        # ─── Price tracking for active signals ───
        still_active = []
        for trk in active_tracking:
            if trk["minutes_tracked"] <= TRACKING_MINUTES:
                trk["max_fav"], trk["max_adv"] = insert_price_tracking(
                    conn, trk["signal_id"], trk["minutes_tracked"],
                    candle_1m["c"], candle_1m["v"],
                    trk["price_at_signal"], trk["direction"],
                    trk["max_fav"], trk["max_adv"],
                )
                trk["minutes_tracked"] += 1
                if trk["minutes_tracked"] <= TRACKING_MINUTES:
                    still_active.append(trk)
        active_tracking = still_active

        # Commit tracking in batches
        if i % 100 == 0:
            conn.commit()

        # ─── Scanner trigger: 15M candle completed ───
        if result["completed_15m"] is None:
            continue

        # Check warmup
        candles_15m = builder.get_15m_candles(include_current=True)
        candles_1h = builder.get_1h_candles(include_current=True)

        if len(candles_15m) < MIN_15M_HISTORY or len(candles_1h) < MIN_1H_HISTORY:
            if not warmup_done:
                continue
        else:
            if not warmup_done:
                warmup_done = True
                print(f"  Warmup complete at {dt} ({len(candles_15m)} x 15M, {len(candles_1h)} x 1H)")

        # Skip if before start_date
        if start_date and sim_date < start_date:
            continue

        # ─── Run scanner ───
        daily_slice = daily_up_to(qqq_daily, sim_date)
        spy_slice = daily_up_to(spy_daily, sim_date)

        scan_result = analyze(
            ticker=TICKER,
            candles_daily=daily_slice,
            candles_1h=candles_1h,
            candles_15m=candles_15m,
            spy_daily=spy_slice,
            sim_datetime=dt,
            sim_date=sim_date,
        )

        if scan_result.get("error"):
            continue

        scoring = scan_result["scoring"]
        score = scoring["score"]
        conf = scoring["conf"]
        direction = scoring.get("dir")
        signal_generated = score >= SIGNAL_THRESHOLD and conf not in ("—",)

        # Log every scan
        insert_scan_log(
            conn, current_session_id, dt, TICKER,
            scan_result["ind"]["price"], score, conf, direction,
            signal_generated,
        )
        scan_count += 1

        # ─── Signal logging ───
        if signal_generated:
            signal_id = insert_signal(conn, current_session_id, scan_result, dt, TICKER)
            signal_count += 1

            # Start price tracking
            active_tracking.append({
                "signal_id": signal_id,
                "price_at_signal": scan_result["ind"]["price"],
                "direction": direction,
                "minutes_tracked": 0,
                "max_fav": 0.0,
                "max_adv": 0.0,
            })

        # ─── Progress ───
        if scan_count % 50 == 0:
            elapsed = time.time() - start_time
            pct = (i + 1) / total_candles * 100
            print(f"  {sim_date} | {pct:.0f}% | scans:{scan_count} signals:{signal_count} tracking:{len(active_tracking)} | {elapsed:.0f}s")

    # Final commit
    conn.commit()
    elapsed = time.time() - start_time

    # ─── Summary ───
    total_scans = conn.execute("SELECT COUNT(*) FROM scan_log").fetchone()[0]
    total_signals = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    total_tracking = conn.execute("SELECT COUNT(*) FROM price_tracking").fetchone()[0]
    total_sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    total_components = conn.execute("SELECT COUNT(*) FROM signal_components").fetchone()[0]

    print(f"\n{'='*60}")
    print(f"  BACKTEST COMPLETE — {elapsed:.1f}s")
    print(f"{'='*60}")
    print(f"  Sessions:    {total_sessions}")
    print(f"  Scans:       {total_scans}")
    print(f"  Signals:     {total_signals} (score ≥ {SIGNAL_THRESHOLD})")
    print(f"  Components:  {total_components}")
    print(f"  Tracking:    {total_tracking} price points")

    if total_signals > 0:
        # Quick stats
        by_conf = conn.execute(
            "SELECT confidence, COUNT(*) as cnt FROM signals GROUP BY confidence ORDER BY confidence"
        ).fetchall()
        print(f"\n  By confidence:")
        for row in by_conf:
            print(f"    {row['confidence']}: {row['cnt']}")

        by_dir = conn.execute(
            "SELECT direction, COUNT(*) as cnt FROM signals GROUP BY direction"
        ).fetchall()
        print(f"\n  By direction:")
        for row in by_dir:
            print(f"    {row['direction']}: {row['cnt']}")

    conn.close()
    print(f"\n  DB: {DB_PATH}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Signal Observatory Backtest")
    parser.add_argument("--start", help="Start date YYYY-MM-DD (scans from this date, warmup before)")
    parser.add_argument("--end", help="End date YYYY-MM-DD")
    args = parser.parse_args()
    run_backtest(start_date=args.start, end_date=args.end)
