#!/usr/bin/env python3
"""parity_qqq_regenerate.py — Opción B del parity check.

Regenera las 245 señales del sample canonical QQQ corriendo `analyze()`
del motor V5 sobre las velas del `parity_qqq_candles.db` y compara
campo a campo contra `parity_qqq_sample.json`.

Uso::

    cd backend/fixtures/parity_reference
    python3 parity_qqq_regenerate.py

    # Modo verboso con primeros N diffs:
    python3 parity_qqq_regenerate.py --max-diffs 20

    # Sólo las primeras N señales (debug rápido):
    python3 parity_qqq_regenerate.py --limit 10

Exit codes:

    0 — PARITY OK: 0 diferencias significativas
    1 — PARITY FAIL: hay diferencias (imprime diff detallado)
    2 — Error de setup (DB no encontrada, sample corrupto, etc.)
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from typing import Any

# Ajustar sys.path para poder importar `engines` y `modules` desde el repo
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from engines.scoring import analyze  # noqa: E402
from engines.scoring.aggregator import aggregate_to_1h, aggregate_to_15m  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "parity_qqq_candles.db")
SAMPLE_PATH = os.path.join(HERE, "fixtures", "parity_qqq_sample.json")
FIXTURE_PATH = os.path.join(ROOT, "fixtures", "qqq_canonical_v1.json")

DEFAULT_TOLERANCE = 0.01


# ═══════════════════════════════════════════════════════════════════════════
# Data loading
# ═══════════════════════════════════════════════════════════════════════════


def load_sample() -> dict:
    with open(SAMPLE_PATH) as f:
        return json.load(f)


def load_fixture() -> dict:
    with open(FIXTURE_PATH) as f:
        return json.load(f)


def load_all_candles(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Carga las 3 tablas de velas en memoria una sola vez."""
    cur = conn.cursor()
    out = {}
    for table in ("qqq_1min", "qqq_daily", "spy_daily"):
        cur.execute(f"SELECT dt, o, h, l, c, v FROM {table} ORDER BY dt")
        out[table] = [
            {"dt": r[0], "o": r[1], "h": r[2], "l": r[3], "c": r[4], "v": r[5]}
            for r in cur.fetchall()
        ]
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Slicing por timestamp de señal
# ═══════════════════════════════════════════════════════════════════════════


def slice_for_signal(
    signal_dt: str,
    qqq_1min: list[dict],
    qqq_daily: list[dict],
    spy_daily: list[dict],
) -> dict[str, Any]:
    """Construye los inputs de `analyze()` correspondientes al momento T.

    - `candles_15m`: agg de 1min hasta `T` inclusive (última vela parcial).
    - `candles_1h`: agg de 1min hasta `T` inclusive.
    - `candles_daily`: todas las velas daily **anteriores** a `T[:10]`.
      (La sesión del día de T aún no ha cerrado, no se incluye.)
    - `spy_daily`: idem pero de SPY.
    """
    date = signal_dt[:10]
    c15 = aggregate_to_15m(qqq_1min, until_dt=signal_dt)
    c1h = aggregate_to_1h(qqq_1min, until_dt=signal_dt)
    cd = [c for c in qqq_daily if c["dt"] < date]
    sd = [c for c in spy_daily if c["dt"] < date]
    return {
        "candles_15m": c15,
        "candles_1h": c1h,
        "candles_daily": cd,
        "spy_daily": sd,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Comparación
# ═══════════════════════════════════════════════════════════════════════════


def close_enough(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


def compare_signal(
    expected: dict,
    actual: dict,
    tolerance: float,
) -> list[str]:
    """Compara campo a campo. Retorna lista de mensajes de diff (vacía
    si matchean)."""
    diffs: list[str] = []

    # Score (tolerancia float)
    if not close_enough(actual["score"], expected["score"], tolerance):
        diffs.append(f"score: expected={expected['score']} actual={actual['score']}")

    # Confidence, direction — strings exactos
    if actual["conf"] != expected["confidence"]:
        diffs.append(f"conf: expected={expected['confidence']} actual={actual['conf']}")
    if actual["dir"] != expected["direction"]:
        diffs.append(f"dir: expected={expected['direction']} actual={actual['dir']}")

    # Alignment n + dir
    aln_actual = actual["layers"].get("alignment", {})
    if aln_actual.get("n") != expected["alignment"]["n"]:
        diffs.append(
            f"alignment.n: expected={expected['alignment']['n']} "
            f"actual={aln_actual.get('n')}"
        )
    if aln_actual.get("dir") != expected["alignment"]["dir"]:
        diffs.append(
            f"alignment.dir: expected={expected['alignment']['dir']} "
            f"actual={aln_actual.get('dir')}"
        )

    # Trends
    trends_actual = actual["layers"].get("trends", {})
    for tf, key in (("t15m", "t15m"), ("t1h", "t1h"), ("tdaily", "tdaily")):
        exp_t = expected["trends"].get(tf)
        act_t = trends_actual.get(key)
        if exp_t != act_t:
            diffs.append(f"trends.{tf}: expected={exp_t} actual={act_t}")

    # Structure
    struct_actual = actual["layers"].get("structure", {})
    if struct_actual.get("pass") != expected["structure"]["pass"]:
        diffs.append(
            f"structure.pass: expected={expected['structure']['pass']} "
            f"actual={struct_actual.get('pass')}"
        )
    if struct_actual.get("override") != expected["structure"]["override"]:
        diffs.append(
            f"structure.override: expected={expected['structure']['override']} "
            f"actual={struct_actual.get('override')}"
        )

    # trigger_count / trigger_sum / confirm_sum
    trig_actual = actual["layers"].get("trigger", {})
    if trig_actual.get("count") != expected["trigger_count"]:
        diffs.append(
            f"trigger_count: expected={expected['trigger_count']} "
            f"actual={trig_actual.get('count')}"
        )
    if not close_enough(
        trig_actual.get("sum", 0), expected["trigger_sum"], tolerance,
    ):
        diffs.append(
            f"trigger_sum: expected={expected['trigger_sum']} "
            f"actual={trig_actual.get('sum')}"
        )
    conf_actual = actual["layers"].get("confirm", {})
    if not close_enough(
        conf_actual.get("sum", 0), expected["confirm_sum"], tolerance,
    ):
        diffs.append(
            f"confirm_sum: expected={expected['confirm_sum']} "
            f"actual={conf_actual.get('sum')}"
        )

    # Conflict blocked
    risk_actual = actual["layers"].get("risk", {})
    if risk_actual.get("blocked", False) != expected["conflict_blocked"]:
        diffs.append(
            f"conflict_blocked: expected={expected['conflict_blocked']} "
            f"actual={risk_actual.get('blocked', False)}"
        )

    return diffs


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    ap.add_argument("--limit", type=int, default=0, help="Máx señales a procesar (0=todas)")
    ap.add_argument("--max-diffs", type=int, default=10, help="Máx diffs a imprimir")
    args = ap.parse_args()

    # Pre-checks
    for path, label in (
        (DB_PATH, "DB de velas"),
        (SAMPLE_PATH, "sample"),
        (FIXTURE_PATH, "fixture canonical"),
    ):
        if not os.path.exists(path):
            print(f"ERROR: {label} no encontrado en {path}", file=sys.stderr)
            return 2

    sample = load_sample()
    fixture = load_fixture()

    conn = sqlite3.connect(DB_PATH)
    data = load_all_candles(conn)
    conn.close()

    signals = sample["signals"]
    if args.limit:
        signals = signals[: args.limit]

    matches = 0
    mismatches: list[tuple[dict, list[str]]] = []
    errors: list[tuple[dict, str]] = []

    for sig in signals:
        inputs = slice_for_signal(
            sig["timestamp"],
            data["qqq_1min"],
            data["qqq_daily"],
            data["spy_daily"],
        )
        try:
            out = analyze(
                ticker=sig["ticker"],
                candles_daily=inputs["candles_daily"],
                candles_1h=inputs["candles_1h"],
                candles_15m=inputs["candles_15m"],
                fixture=fixture,
                spy_daily=inputs["spy_daily"],
                sim_datetime=sig["timestamp"],
                sim_date=sig["timestamp"][:10],
                bench_daily=inputs["spy_daily"],  # QQQ benchmark = SPY
            )
        except Exception as e:
            errors.append((sig, f"{type(e).__name__}: {e}"))
            continue

        if out.get("error"):
            errors.append((sig, f"{out.get('error_code')}: {out.get('layers', {}).get('error_detail', '')}"))
            continue

        diffs = compare_signal(sig, out, args.tolerance)
        if diffs:
            mismatches.append((sig, diffs))
        else:
            matches += 1

    total = len(signals)
    print(f"PARITY REPORT — {total} señales procesadas")
    print(f"  matches:    {matches}")
    print(f"  mismatches: {len(mismatches)}")
    print(f"  errors:     {len(errors)}")
    print()

    if errors:
        print("ERRORS (primeros):")
        for sig, msg in errors[: args.max_diffs]:
            print(f"  [{sig['timestamp']}] {msg}")
        print()

    if mismatches:
        print(f"MISMATCHES (primeros {args.max_diffs}):")
        for sig, diffs in mismatches[: args.max_diffs]:
            print(f"  [{sig['timestamp']}] score_exp={sig['score']} conf_exp={sig['confidence']}")
            for d in diffs:
                print(f"    - {d}")
        print()

    if mismatches or errors:
        print("PARITY FAIL")
        return 1
    print("PARITY OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
