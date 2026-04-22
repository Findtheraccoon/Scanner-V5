#!/usr/bin/env python3
"""regenerate_from_observatory.py — Fase 5.4 closure.

Regenera `parity_qqq_sample.json` leyendo los valores frescos del
Observatory DB commiteado. Evita tener que correr el replay completo
del Observatory: los valores ya computados en `signals` /
`signal_components` son la fuente de verdad (output directo del
motor Observatory).

Mantiene:
- Los mismos 245 `signal_id_ref` del sample actual.
- El mismo formato JSON (keys, subkeys, tipos).
- La metadata top-level (`parity_reference_version`, `source_db`,
  `canonical_hash`, etc.) — solo actualiza `generated_at` y el
  `distribution_by_band` recalculado.

Uso::

    cd /home/user/Scanner-V5
    python backend/fixtures/parity_reference/regenerate_from_observatory.py

    # Con --dry-run muestra el diff sin escribir
    python backend/fixtures/parity_reference/regenerate_from_observatory.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))

DB_PATH = os.path.join(
    REPO_ROOT, "docs", "specs", "Observatory", "Current", "observatory_v5_2.db",
)
SAMPLE_PATH = os.path.join(HERE, "fixtures", "parity_qqq_sample.json")


def fetch_signal(cur: sqlite3.Cursor, signal_id: int) -> dict | None:
    """Trae la señal + sus componentes al shape del sample JSON."""
    row = cur.execute(
        """
        SELECT id, timestamp, ticker, price_at_signal, direction, score, confidence,
               alignment_n, alignment_dir, trend_15m, trend_1h, trend_daily,
               structure_pass, structure_override, trigger_count, trigger_sum,
               confirm_sum, conflict_blocked
        FROM signals WHERE id = ?
        """,
        (signal_id,),
    ).fetchone()
    if row is None:
        return None

    (
        id_, ts, tkr, price, dir_, score, conf,
        aln_n, aln_dir, t15, t1h, td,
        struct_pass, struct_override,
        trig_count, trig_sum, conf_sum, conflict,
    ) = row

    components: list[dict] = []
    for c in cur.execute(
        """
        SELECT category, timeframe, description, direction, weight, age
        FROM signal_components WHERE signal_id = ?
        ORDER BY id
        """,
        (signal_id,),
    ).fetchall():
        cat, tf, desc, d, w, age = c
        components.append({
            "age": age,
            "category": cat,
            "description": desc,
            "direction": d,
            "timeframe": tf,
            "weight": w,
        })

    return {
        "alignment": {"dir": aln_dir, "n": aln_n},
        "components": components,
        "confidence": conf,
        "confirm_sum": conf_sum,
        "conflict_blocked": bool(conflict),
        "direction": dir_,
        "price_at_signal": price,
        "score": score,
        "signal_id_ref": id_,
        "structure": {
            "override": bool(struct_override),
            "pass": bool(struct_pass),
        },
        "ticker": tkr,
        "timestamp": ts,
        "trends": {"t15m": t15, "t1h": t1h, "tdaily": td},
        "trigger_count": trig_count,
        "trigger_sum": trig_sum,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dry-run", action="store_true",
        help="No sobrescribe el sample — solo muestra diff.",
    )
    args = ap.parse_args()

    for path, label in ((DB_PATH, "Observatory DB"), (SAMPLE_PATH, "sample JSON")):
        if not os.path.isfile(path):
            print(f"ERROR: {label} no encontrado en {path}", file=sys.stderr)
            return 2

    with open(SAMPLE_PATH) as f:
        old = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    new_signals: list[dict] = []
    missing: list[int] = []
    for s in old["signals"]:
        fresh = fetch_signal(cur, s["signal_id_ref"])
        if fresh is None:
            missing.append(s["signal_id_ref"])
            continue
        new_signals.append(fresh)

    conn.close()

    if missing:
        print(
            f"WARNING: {len(missing)} signal_id_ref(s) no encontrados "
            f"en Observatory DB: {missing[:10]}...",
            file=sys.stderr,
        )

    distribution = Counter(s["confidence"] for s in new_signals)

    new_sample = {
        **old,
        "generated_at": datetime.now().isoformat(timespec="seconds") + "Z",
        "total_signals": len(new_signals),
        "distribution_by_band": dict(distribution),
        "signals": new_signals,
    }

    # Diff summary
    changed = 0
    for old_s, new_s in zip(old["signals"], new_signals, strict=False):
        if old_s != new_s:
            changed += 1
    print(f"Signals totales: {len(new_signals)}")
    print(f"Signals con diff: {changed}/{len(old['signals'])}")
    print(f"distribution antes: {old['distribution_by_band']}")
    print(f"distribution ahora: {dict(distribution)}")

    if args.dry_run:
        print("\n[DRY-RUN] sample NO escrito.")
        return 0

    with open(SAMPLE_PATH, "w", encoding="utf-8") as f:
        json.dump(new_sample, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"\nsample regenerado en {SAMPLE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
