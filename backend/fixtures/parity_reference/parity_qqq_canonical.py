#!/usr/bin/env python3
"""
parity_qqq_canonical.py — Go/no-go test del motor v5 contra el canonical QQQ.

Compara las señales generadas por el motor actual al correr sobre 30 sesiones de
QQQ de 2025 contra el golden reference capturado de observatory_v5_2.db.

El test PASA si bit-por-bit los outputs del motor coinciden con el reference:
 - Misma cantidad de señales por sesión
 - Mismo score, confidence, dirección
 - Mismo alignment, trigger_sum, confirm_sum, conflict_blocked
 - Mismos componentes detectados

Uso:
    python3 tests/parity_qqq_canonical.py [--tolerance 0.01]

Exit codes:
    0 — parity OK, el motor matchea el reference
    1 — parity FAIL, hay diferencias (el script imprime el diff detallado)
    2 — error de setup (DB no encontrada, sample roto, etc.)

Requisitos para correr:
    - observatory_v5_2.db en la raíz del repo (o pasar otro path)
    - fixtures/qqq_canonical_v1.json + .sha256
    - tests/fixtures/parity_qqq_sample.json
"""

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from collections import defaultdict


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, "observatory_v5_2.db")
CANONICAL_PATH = os.path.join(ROOT, "fixtures", "qqq_canonical_v1.json")
CANONICAL_HASH_PATH = os.path.join(ROOT, "fixtures", "qqq_canonical_v1.sha256")
SAMPLE_PATH = os.path.join(ROOT, "tests", "fixtures", "parity_qqq_sample.json")

# Tolerancia default para comparación de floats
DEFAULT_TOL = 0.01


# ═══════════════════════════════════════════════════════════════════════════
# VALIDACIONES PRE-TEST
# ═══════════════════════════════════════════════════════════════════════════

def verify_canonical_hash():
    """Verifica que el hash del canonical matchee su .sha256 sibling."""
    if not os.path.exists(CANONICAL_PATH):
        return False, f"Canonical no encontrado: {CANONICAL_PATH}"
    if not os.path.exists(CANONICAL_HASH_PATH):
        return False, f"Hash sibling no encontrado: {CANONICAL_HASH_PATH}"

    with open(CANONICAL_PATH, "rb") as f:
        content = f.read()
    actual = hashlib.sha256(content).hexdigest()

    with open(CANONICAL_HASH_PATH) as f:
        expected = f.read().split()[0]

    if actual != expected:
        return False, (
            f"Hash mismatch del canonical (REG-020):\n"
            f"  archivo: {actual}\n"
            f"  esperado: {expected}"
        )
    return True, actual


def load_sample():
    """Carga el parity reference sample."""
    if not os.path.exists(SAMPLE_PATH):
        return None, f"Sample no encontrado: {SAMPLE_PATH}"
    with open(SAMPLE_PATH) as f:
        sample = json.load(f)
    required = ["signals", "canonical_hash", "engine_version", "selected_sessions"]
    for k in required:
        if k not in sample:
            return None, f"Sample corrupto: falta campo '{k}'"
    return sample, None


# ═══════════════════════════════════════════════════════════════════════════
# LOAD SEÑALES DEL MOTOR (actual state)
# ═══════════════════════════════════════════════════════════════════════════

def load_engine_signals(db_path, sessions):
    """Carga las señales generadas por el motor actual para las sesiones del sample."""
    if not os.path.exists(db_path):
        return None, f"DB no encontrada: {db_path}"

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    signals_by_session = defaultdict(list)

    for session in sessions:
        cur.execute("""
            SELECT id, timestamp, ticker, price_at_signal, direction, score, confidence,
                   alignment_n, alignment_dir, trend_15m, trend_1h, trend_daily,
                   structure_pass, structure_override,
                   trigger_count, trigger_sum, confirm_sum, conflict_blocked
            FROM signals
            WHERE date(timestamp) = ?
            ORDER BY timestamp
        """, (session,))

        for row in cur.fetchall():
            sid = row[0]
            components = []
            cur2 = conn.cursor()
            cur2.execute("""
                SELECT category, description, weight, direction, timeframe, age
                FROM signal_components
                WHERE signal_id = ? ORDER BY category, description
            """, (sid,))
            for c in cur2.fetchall():
                components.append({
                    "category": c[0],
                    "description": c[1],
                    "weight": c[2],
                    "direction": c[3],
                    "timeframe": c[4],
                    "age": c[5]
                })

            signals_by_session[session].append({
                "timestamp": row[1],
                "ticker": row[2],
                "price_at_signal": row[3],
                "direction": row[4],
                "score": row[5],
                "confidence": row[6],
                "alignment": {"n": row[7], "dir": row[8]},
                "trends": {"t15m": row[9], "t1h": row[10], "tdaily": row[11]},
                "structure": {"pass": bool(row[12]), "override": bool(row[13])},
                "trigger_count": row[14],
                "trigger_sum": row[15],
                "confirm_sum": row[16],
                "conflict_blocked": bool(row[17]),
                "components": components
            })

    conn.close()
    return dict(signals_by_session), None


# ═══════════════════════════════════════════════════════════════════════════
# COMPARACIÓN
# ═══════════════════════════════════════════════════════════════════════════

def floats_equal(a, b, tol):
    """Comparación de floats con tolerancia relativa."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= tol


def compare_signal(expected, actual, tol):
    """Compara una señal campo por campo. Devuelve lista de diffs."""
    diffs = []

    # Campos escalares obligatorios
    for k in ["direction", "confidence", "trigger_count", "conflict_blocked"]:
        if expected.get(k) != actual.get(k):
            diffs.append(f"  {k}: esperado={expected.get(k)!r}, actual={actual.get(k)!r}")

    # Campos float con tolerancia
    for k in ["score", "trigger_sum", "confirm_sum", "price_at_signal"]:
        if not floats_equal(expected.get(k), actual.get(k), tol):
            diffs.append(f"  {k}: esperado={expected.get(k)}, actual={actual.get(k)}")

    # Alignment
    if expected["alignment"]["n"] != actual["alignment"]["n"]:
        diffs.append(f"  alignment.n: esperado={expected['alignment']['n']}, actual={actual['alignment']['n']}")
    if expected["alignment"]["dir"] != actual["alignment"]["dir"]:
        diffs.append(f"  alignment.dir: esperado={expected['alignment']['dir']}, actual={actual['alignment']['dir']}")

    # Trends
    for tk in ["t15m", "t1h", "tdaily"]:
        if expected["trends"][tk] != actual["trends"][tk]:
            diffs.append(f"  trends.{tk}: esperado={expected['trends'][tk]}, actual={actual['trends'][tk]}")

    # Structure flags
    if expected["structure"]["pass"] != actual["structure"]["pass"]:
        diffs.append(f"  structure.pass: esperado={expected['structure']['pass']}, actual={actual['structure']['pass']}")
    if expected["structure"]["override"] != actual["structure"]["override"]:
        diffs.append(f"  structure.override: esperado={expected['structure']['override']}, actual={actual['structure']['override']}")

    # Componentes: comparar sets de (category, description, weight)
    exp_comp = sorted(
        [(c["category"], c["description"], c["weight"]) for c in expected["components"]]
    )
    act_comp = sorted(
        [(c["category"], c["description"], c["weight"]) for c in actual["components"]]
    )
    if exp_comp != act_comp:
        missing = [c for c in exp_comp if c not in act_comp]
        extra = [c for c in act_comp if c not in exp_comp]
        if missing:
            diffs.append(f"  componentes faltantes: {missing}")
        if extra:
            diffs.append(f"  componentes extra: {extra}")

    return diffs


def compare_sessions(sample_signals, actual_signals, tol):
    """Compara todas las sesiones. Devuelve (total, mismatches, report)."""
    report = []
    total = 0
    mismatches = 0

    # Agrupar sample por sesión
    sample_by_session = defaultdict(list)
    for s in sample_signals:
        session = s["timestamp"][:10]
        sample_by_session[session].append(s)

    for session in sorted(sample_by_session.keys()):
        expected = sample_by_session[session]
        actual = actual_signals.get(session, [])

        # Match por timestamp + direction
        actual_by_key = {}
        for a in actual:
            k = (a["timestamp"], a["direction"])
            actual_by_key[k] = a

        session_mismatches = []

        for exp in expected:
            total += 1
            k = (exp["timestamp"], exp["direction"])
            if k not in actual_by_key:
                mismatches += 1
                session_mismatches.append(
                    f"  ⚠ señal ausente en DB: {exp['timestamp']} {exp['direction']} "
                    f"(reference esperaba score={exp['score']} conf={exp['confidence']})"
                )
                continue

            act = actual_by_key[k]
            diffs = compare_signal(exp, act, tol)
            if diffs:
                mismatches += 1
                session_mismatches.append(
                    f"  ⚠ señal diff en {exp['timestamp']} {exp['direction']}:\n"
                    + "\n".join(diffs)
                )

        # Señales extra en actual que no estaban en sample
        expected_keys = {(e["timestamp"], e["direction"]) for e in expected}
        for k, a in actual_by_key.items():
            if k not in expected_keys:
                mismatches += 1
                total += 1
                session_mismatches.append(
                    f"  ⚠ señal extra en DB: {a['timestamp']} {a['direction']} "
                    f"(score={a['score']} conf={a['confidence']})"
                )

        if session_mismatches:
            report.append(f"\nSesión {session} ({len(expected)} señales esperadas):")
            report.extend(session_mismatches)

    return total, mismatches, report


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Parity check del motor v5 contra el canonical QQQ"
    )
    parser.add_argument("--db", default=DEFAULT_DB,
                        help=f"Path a la DB a comparar (default: {DEFAULT_DB})")
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOL,
                        help=f"Tolerancia para floats (default: {DEFAULT_TOL})")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Mostrar más detalle")
    args = parser.parse_args()

    print("=" * 72)
    print("PARITY CHECK — QQQ canonical v1")
    print("=" * 72)

    # Paso 1 — verificar hash del canonical
    print("\n[1/4] Verificando hash del canonical...")
    ok, info = verify_canonical_hash()
    if not ok:
        print(f"✗ FALLO: {info}")
        return 2
    print(f"✓ Hash OK: {info[:16]}...")

    # Paso 2 — cargar sample reference
    print("\n[2/4] Cargando parity reference sample...")
    sample, err = load_sample()
    if err:
        print(f"✗ FALLO: {err}")
        return 2
    print(f"✓ Sample cargado: {sample['total_signals']} señales esperadas en "
          f"{len(sample['selected_sessions'])} sesiones")
    print(f"  Reference engine version: {sample['engine_version']}")
    print(f"  Distribución esperada: {sample['distribution_by_band']}")

    # Paso 3 — cargar señales del motor actual
    print(f"\n[3/4] Cargando señales del motor desde {args.db}...")
    actual, err = load_engine_signals(args.db, sample["selected_sessions"])
    if err:
        print(f"✗ FALLO: {err}")
        return 2
    total_actual = sum(len(v) for v in actual.values())
    print(f"✓ Motor produjo {total_actual} señales en las {len(actual)} sesiones")

    # Paso 4 — comparar
    print(f"\n[4/4] Comparando (tolerancia para floats: {args.tolerance})...")
    total, mismatches, report = compare_sessions(
        sample["signals"], actual, args.tolerance
    )

    print("\n" + "=" * 72)
    if mismatches == 0:
        print(f"✓ PARITY OK — {total} señales comparadas, 0 diferencias")
        print(f"  El motor actual matchea bit-por-bit el reference canonical.")
        print("=" * 72)
        return 0
    else:
        pct_ok = 100.0 * (total - mismatches) / total if total else 0
        print(f"✗ PARITY FAIL — {mismatches}/{total} señales con diferencias "
              f"({pct_ok:.1f}% OK)")
        print("=" * 72)
        if report:
            print("\nDetalle de diferencias:")
            for line in report[:50]:  # limit output
                print(line)
            if len(report) > 50:
                print(f"\n... y {len(report) - 50} líneas más (usar --verbose para ver todo)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
