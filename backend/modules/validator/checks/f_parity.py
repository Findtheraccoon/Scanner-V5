"""Check F — Parity exhaustivo contra canonical QQQ.

Corre `analyze()` sobre las velas de `parity_qqq_candles.db` para cada
señal del sample `parity_qqq_sample.json` y compara campo a campo.

**Paths por default** (relativos al módulo `engines.scoring`):

- DB de velas: `backend/fixtures/parity_reference/fixtures/parity_qqq_candles.db`
- Sample: `backend/fixtures/parity_reference/fixtures/parity_qqq_sample.json`
- Fixture canonical: `backend/fixtures/qqq_canonical_v1.json`

Los 3 args son overridables — en tests se pasa `tmp_path`.

**Severidad (spec §3.2 + código ENG-050):**

- Dataset completo ausente (DB o sample o fixture) → `skip`.
- Match rate ≥ `min_match_rate` (default 0.70) → `pass`.
- Match rate < minimum → `fail / warning` con `ENG-050` + stats.
- `analyze()` crashea en alguna señal → contribuye a `errors` en stats;
  warning igual (spec: ENG-050 es warning, no fatal).

**Performance:**

Por default `limit=30` (~1s). `limit=None` procesa las 245 del sample
(~7s — aceptable para arranque, lento para Dashboard on-demand).

**Lógica portada de `backend/fixtures/parity_reference/parity_qqq_regenerate.py`:**

El slicing por signal (`slice_for_signal`) y la comparación campo-a-campo
(`compare_signal`) son versiones auto-contenidas y puras de la lógica del
runner CLI original. Reemplazar por un import directo requiere refactorear
el runner para que no use `sys.path` hacks — fuera de scope de V.4.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from engines.scoring import analyze
from engines.scoring.aggregator import aggregate_to_1h, aggregate_to_15m
from modules.validator.models import TestResult

# ──────────────────────────────────────────────────────────────────────
# Paths default — relativos a backend/
# ──────────────────────────────────────────────────────────────────────

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_DB = _BACKEND_ROOT / "fixtures/parity_reference/fixtures/parity_qqq_candles.db"
_DEFAULT_SAMPLE = (
    _BACKEND_ROOT / "fixtures/parity_reference/fixtures/parity_qqq_sample.json"
)
_DEFAULT_FIXTURE = _BACKEND_ROOT / "fixtures/qqq_canonical_v1.json"

DEFAULT_TOLERANCE = 0.01
DEFAULT_LIMIT = 30
DEFAULT_MIN_MATCH_RATE = 0.99  # baseline post-fix aggregator + vol_ratio: 245/245 = 100%

ENG_050 = "ENG-050"


# ──────────────────────────────────────────────────────────────────────
# Slicing + compare (portados del runner CLI)
# ──────────────────────────────────────────────────────────────────────


def _load_candles(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    cur = conn.cursor()
    out = {}
    for table in ("qqq_1min", "qqq_daily", "spy_daily"):
        cur.execute(f"SELECT dt, o, h, l, c, v FROM {table} ORDER BY dt")
        out[table] = [
            {"dt": r[0], "o": r[1], "h": r[2], "l": r[3], "c": r[4], "v": r[5]}
            for r in cur.fetchall()
        ]
    return out


def _slice_for_signal(
    signal_dt: str,
    qqq_1min: list[dict],
    qqq_daily: list[dict],
    spy_daily: list[dict],
) -> dict[str, list[dict]]:
    date = signal_dt[:10]
    return {
        "candles_15m": aggregate_to_15m(
            qqq_1min, until_dt=signal_dt, include_partial=True,
        ),
        "candles_1h": aggregate_to_1h(
            qqq_1min, until_dt=signal_dt, include_partial=True,
        ),
        "candles_daily": [c for c in qqq_daily if c["dt"] <= date],
        "spy_daily": [c for c in spy_daily if c["dt"] <= date],
    }


def _close_enough(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


def _compare_signal(
    expected: dict, actual: dict, tolerance: float,
) -> list[str]:
    """Retorna lista de diffs. Vacía si matchean."""
    diffs: list[str] = []

    if not _close_enough(actual.get("score", 0), expected["score"], tolerance):
        diffs.append(f"score: expected={expected['score']} actual={actual.get('score')}")
    if actual.get("conf") != expected["confidence"]:
        diffs.append(f"conf: expected={expected['confidence']} actual={actual.get('conf')}")
    if actual.get("dir") != expected["direction"]:
        diffs.append(f"dir: expected={expected['direction']} actual={actual.get('dir')}")

    aln = actual.get("layers", {}).get("alignment", {})
    if aln.get("n") != expected["alignment"]["n"]:
        diffs.append(f"alignment.n: expected={expected['alignment']['n']} actual={aln.get('n')}")
    if aln.get("dir") != expected["alignment"]["dir"]:
        diffs.append(f"alignment.dir: expected={expected['alignment']['dir']} actual={aln.get('dir')}")

    trends = actual.get("layers", {}).get("trends", {})
    for tf in ("t15m", "t1h", "tdaily"):
        if expected["trends"].get(tf) != trends.get(tf):
            diffs.append(f"trends.{tf}: expected={expected['trends'].get(tf)} actual={trends.get(tf)}")

    struct = actual.get("layers", {}).get("structure", {})
    if struct.get("pass") != expected["structure"]["pass"]:
        diffs.append(f"structure.pass: expected={expected['structure']['pass']} actual={struct.get('pass')}")

    trig = actual.get("layers", {}).get("trigger", {})
    if trig.get("count") != expected["trigger_count"]:
        diffs.append(f"trigger_count: expected={expected['trigger_count']} actual={trig.get('count')}")
    if not _close_enough(trig.get("sum", 0), expected["trigger_sum"], tolerance):
        diffs.append(f"trigger_sum: expected={expected['trigger_sum']} actual={trig.get('sum')}")

    conf = actual.get("layers", {}).get("confirm", {})
    if not _close_enough(conf.get("sum", 0), expected["confirm_sum"], tolerance):
        diffs.append(f"confirm_sum: expected={expected['confirm_sum']} actual={conf.get('sum')}")

    return diffs


# ──────────────────────────────────────────────────────────────────────
# Check runner
# ──────────────────────────────────────────────────────────────────────


async def run(
    *,
    db_path: Path | None = None,
    sample_path: Path | None = None,
    fixture_path: Path | None = None,
    tolerance: float = DEFAULT_TOLERANCE,
    limit: int | None = DEFAULT_LIMIT,
    min_match_rate: float = DEFAULT_MIN_MATCH_RATE,
) -> TestResult:
    start = time.perf_counter()

    db = db_path or _DEFAULT_DB
    sample_p = sample_path or _DEFAULT_SAMPLE
    fixture_p = fixture_path or _DEFAULT_FIXTURE

    missing = [str(p) for p in (db, sample_p, fixture_p) if not p.is_file()]
    if missing:
        return TestResult(
            test_id="F",
            status="skip",
            message=f"dataset parity no disponible: {missing}",
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )

    sample = json.loads(sample_p.read_text(encoding="utf-8"))
    fixture = json.loads(fixture_p.read_text(encoding="utf-8"))

    signals = sample["signals"]
    if limit is not None and limit > 0:
        signals = signals[:limit]

    conn = sqlite3.connect(db)
    try:
        data = _load_candles(conn)
    finally:
        conn.close()

    matches = 0
    mismatches = 0
    errors = 0
    sample_diffs: list[dict[str, Any]] = []

    for sig in signals:
        inputs = _slice_for_signal(
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
                bench_daily=inputs["spy_daily"],
            )
        except Exception as e:
            errors += 1
            if len(sample_diffs) < 5:
                sample_diffs.append(
                    {"timestamp": sig["timestamp"], "error": f"{type(e).__name__}: {e}"},
                )
            continue

        if out.get("error"):
            errors += 1
            continue

        diffs = _compare_signal(sig, out, tolerance)
        if diffs:
            mismatches += 1
            if len(sample_diffs) < 5:
                sample_diffs.append(
                    {"timestamp": sig["timestamp"], "diffs": diffs},
                )
        else:
            matches += 1

    total = len(signals)
    match_rate = matches / total if total else 0.0
    duration_ms = (time.perf_counter() - start) * 1000.0

    stats = {
        "total": total,
        "matches": matches,
        "mismatches": mismatches,
        "errors": errors,
        "match_rate": round(match_rate, 4),
        "min_match_rate": min_match_rate,
        "sample_diffs": sample_diffs,
    }

    if match_rate >= min_match_rate and errors == 0:
        return TestResult(
            test_id="F",
            status="pass",
            details=stats,
            duration_ms=duration_ms,
        )

    return TestResult(
        test_id="F",
        status="fail",
        severity="warning",
        error_code=ENG_050,
        message=(
            f"parity {matches}/{total} (rate {match_rate:.2%}, "
            f"min {min_match_rate:.0%}) — errors={errors}"
        ),
        details=stats,
        duration_ms=duration_ms,
    )
