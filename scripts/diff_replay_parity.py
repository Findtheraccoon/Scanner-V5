#!/usr/bin/env python3
"""Diff bit-a-bit entre replay Python (motor V5 backend) y replay JS
(scanner_v5_standalone.html).

Carga:
  - SQLite de `scripts/replay_canonical_parity.py` (motor V5 backend).
  - JSON de `scripts/replay_html_parity.js` (motor JS del HTML).

JOIN por `sim_datetime` y reporta:
  - Counts por banda lado a lado.
  - % de match exacto (score + banda + dir + signal + blocked).
  - Confusion matrix de bandas (Python → JS).
  - Top N divergencias por |Δ score|.
  - Análisis de score residual: |Δ| medio, p50, p95, max.

Uso:
  python scripts/diff_replay_parity.py [--py PATH] [--js PATH] [--top N]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_PY = REPO / "backend/data/replay_qqq_canonical_v1.db"
DEFAULT_JS = Path("/tmp/parity_html_full.json")


def load_py(path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT sim_datetime, score, conf, dir, signal, blocked FROM replay_signals ORDER BY sim_datetime"
    ).fetchall()
    conn.close()
    return {r["sim_datetime"]: dict(r) for r in rows}


def load_js(path):
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    return {r["sim_datetime"]: r for r in rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--py", default=str(DEFAULT_PY))
    ap.add_argument("--js", default=str(DEFAULT_JS))
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    print(f"Loading Python replay: {args.py}")
    py = load_py(Path(args.py))
    print(f"Loading JS replay    : {args.js}")
    js = load_js(Path(args.js))
    print(f"  py rows: {len(py):,}")
    print(f"  js rows: {len(js):,}")

    # Sim_datetimes en común.
    py_keys = set(py.keys())
    js_keys = set(js.keys())
    common = py_keys & js_keys
    only_py = py_keys - js_keys
    only_js = js_keys - py_keys
    print("\nTimestamp coverage:")
    print(f"  common  : {len(common):,}")
    print(f"  only py : {len(only_py):,}")
    print(f"  only js : {len(only_js):,}")

    # Counts por banda.
    bands = ["S+", "S", "A+", "A", "B", "REVISAR", "—"]
    py_counts = Counter()
    js_counts = Counter()
    for k in common:
        if not py[k]["blocked"]:
            py_counts[py[k]["conf"]] += 1
        if not js[k]["blocked"]:
            js_counts[js[k]["conf"]] += 1
    print("\nCounts por banda (no bloqueadas, sobre common):")
    print(f"  {'band':<10} {'py':>8} {'js':>8} {'Δ':>8}  {'Δ%':>7}")
    for b in bands:
        p = py_counts.get(b, 0)
        j = js_counts.get(b, 0)
        d = j - p
        pct = (d / p * 100) if p else 0.0
        sign = "+" if d > 0 else ""
        print(f"  {b:<10} {p:>8,} {j:>8,} {sign}{d:>7,}  {pct:>+6.1f}%")

    # Match exact (score + conf + dir + signal + blocked).
    full_match = 0
    band_match = 0
    blocked_match = 0
    score_diffs = []
    matrix = defaultdict(int)  # (py_band, js_band) -> count
    div_rows = []  # (timestamp, py_score, js_score, py_band, js_band, py_dir, js_dir, |Δ|)
    SCORE_TOL = 0.05  # tolerance for "exact" match (rounding 1 dp + IEEE float noise).
    score_tol_match = 0

    for k in sorted(common):
        p = py[k]
        j = js[k]
        p_score = float(p["score"]) if p["score"] is not None else 0.0
        j_score = float(j["score"]) if j["score"] is not None else 0.0
        p_band = p["conf"] or "—"
        j_band = j["conf"] or "—"
        p_dir = p["dir"] or ""
        j_dir = j["dir"] or ""
        p_blk = bool(p["blocked"])
        j_blk = bool(j["blocked"])

        delta = abs(p_score - j_score)
        score_diffs.append(delta)
        matrix[(p_band, j_band)] += 1
        if p_blk == j_blk:
            blocked_match += 1
        if p_band == j_band:
            band_match += 1
        if delta < SCORE_TOL:
            score_tol_match += 1
        if (
            abs(p_score - j_score) < SCORE_TOL
            and p_band == j_band
            and p_dir == j_dir
            and p_blk == j_blk
        ):
            full_match += 1
        else:
            div_rows.append((k, p_score, j_score, p_band, j_band, p_dir, j_dir, delta, p_blk, j_blk))

    n = len(common)
    print("\nMatch rates (sobre common):")
    print(f"  full match (score+band+dir+blocked): {full_match:>8,} / {n:,}  {full_match/n*100:>5.2f}%")
    print(f"  banda match exacto                 : {band_match:>8,} / {n:,}  {band_match/n*100:>5.2f}%")
    print(f"  score |Δ| < {SCORE_TOL}                  : {score_tol_match:>8,} / {n:,}  {score_tol_match/n*100:>5.2f}%")
    print(f"  blocked flag match                 : {blocked_match:>8,} / {n:,}  {blocked_match/n*100:>5.2f}%")

    if score_diffs:
        nonzero = [d for d in score_diffs if d > 0]
        print("\nScore residual (|Δ| sobre todos los common):")
        print(f"  mean : {statistics.mean(score_diffs):.3f}")
        print(f"  p50  : {statistics.median(score_diffs):.3f}")
        if len(score_diffs) > 20:
            sorted_d = sorted(score_diffs)
            p95 = sorted_d[int(len(sorted_d) * 0.95)]
            print(f"  p95  : {p95:.3f}")
        print(f"  max  : {max(score_diffs):.3f}")
        print(f"  count |Δ|>0     : {len(nonzero):,}")
        print(f"  count |Δ|>1.0   : {sum(1 for d in score_diffs if d > 1.0):,}")
        print(f"  count |Δ|>3.0   : {sum(1 for d in score_diffs if d > 3.0):,}")

    # Confusion matrix bandas.
    print("\nConfusion matrix (filas=Python · columnas=JS):")
    header = "  " + "py\\js".ljust(10) + " ".join(b.rjust(8) for b in bands)
    print(header)
    for pb in bands:
        row = "  " + pb.ljust(10)
        for jb in bands:
            row += str(matrix.get((pb, jb), 0)).rjust(8) + " "
        print(row)

    # Top N divergencias por |Δ|.
    print(f"\nTop {args.top} divergencias por |Δ score|:")
    div_sorted = sorted(div_rows, key=lambda x: -x[7])
    print(f"  {'timestamp':<22} {'py_score':>9} {'js_score':>9} {'|Δ|':>6} {'py_band':<8} {'js_band':<8} {'py_dir':<6} {'js_dir':<6} {'p_blk':<5} {'j_blk':<5}")
    for r in div_sorted[: args.top]:
        ts, ps, jss, pb, jb, pd, jd, d, pblk, jblk = r
        print(f"  {ts:<22} {ps:>9.2f} {jss:>9.2f} {d:>6.2f} {pb:<8} {jb:<8} {pd:<6} {jd:<6} {str(pblk):<5} {str(jblk):<5}")


if __name__ == "__main__":
    main()
