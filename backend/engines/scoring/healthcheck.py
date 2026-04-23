"""Healthcheck continuo del Scoring Engine (spec §3.4).

Mini parity test determinístico que corre cada 2 min para detectar
regresiones operativas del motor en runtime. Complementa al Check F
del Validator (exhaustivo pero caro, corre on-demand).

**Diseño:**

- **Dataset sintético pequeño** (~50 velas 15M/1H + 210 daily)
  pre-generado en código. Monotónico ascendente — produce un signal
  determinístico dada la fixture fija.
- **Fixture canonical QQQ** cargada una vez desde disco.
- **`sim_datetime` fijo** — `"2026-04-15 10:30:00"` — hora post-ORB
  para cubrir tanto código pre como post ORB gate.
- **Invariantes chequeados (operativos, no semánticos):**
    1. `analyze()` NO lanza (invariante I3 del motor).
    2. Output tiene todas las keys obligatorias del spec.
    3. `signal` es uno de `{NEUTRAL, SETUP, REVISAR}`.
    4. `score` es numérico.
    5. `error is False` y `error_code is None`.

El parity semántico bit-a-bit lo cubre el Check F del Validator
(exhaustivo, ~2min). Este healthcheck cada 2min sirve para detectar
crashes, shape roto, o regresiones estructurales.

**Severidad:**

- OK → `status="green"`, `error_code=None`.
- Invariante falla → `status="yellow"`, `error_code="ENG-050"`.
- `analyze()` lanza → `status="red"`, `error_code="ENG-001"`.

El resultado se pasa al heartbeat del motor scoring. Si el estado es
amarillo/rojo, el Dashboard muestra el piloto en color y el trader
puede revisar qué se rompió.

**Performance:** ~100ms por corrida (1 llamada a `analyze()` con
dataset chico). Negligible vs scan real (~0.3-0.8s cada 15 min).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engines.scoring import analyze

_SIM_DATETIME_FIXED = "2026-04-15 10:30:00"
_SIM_DATE_FIXED = "2026-04-15"

ENG_050 = "ENG-050"
ENG_001 = "ENG-001"

# Claves obligatorias del output de analyze() que verificamos en cada
# healthcheck — detectan cualquier refactor que rompa el contrato.
_REQUIRED_KEYS: frozenset[str] = frozenset({
    "ticker", "engine_version", "fixture_id", "fixture_version",
    "score", "conf", "signal", "dir", "blocked", "error",
    "layers", "ind", "patterns",
})

# Path default al fixture canonical QQQ.
_FIXTURE_PATH_DEFAULT = (
    Path(__file__).resolve().parents[2]
    / "fixtures" / "qqq_canonical_v1.json"
)


def _synthetic_daily(n: int = 210) -> list[dict]:
    """210 velas daily monotónicas ascendentes. Rangos OHLC razonables."""
    return [
        {
            "dt": f"2026-{(i // 30) + 1:02d}-{(i % 30) + 1:02d}",
            "o": 400.0 + i * 0.5,
            "h": 401.0 + i * 0.5,
            "l": 399.0 + i * 0.5,
            "c": 400.5 + i * 0.5,
            "v": 1_000_000 + i * 100,
        }
        for i in range(n)
    ]


def _synthetic_intraday(n: int, base_dt: str, minutes_per_step: int) -> list[dict]:
    """Velas intraday monotónicas ascendentes. `base_dt` es el dt inicial
    y cada vela suma `minutes_per_step`."""
    import datetime as _dt

    start = _dt.datetime.strptime(base_dt, "%Y-%m-%d %H:%M:%S")
    out: list[dict] = []
    for i in range(n):
        t = start + _dt.timedelta(minutes=i * minutes_per_step)
        out.append({
            "dt": t.strftime("%Y-%m-%d %H:%M:%S"),
            "o": 500.0 + i * 0.1,
            "h": 500.5 + i * 0.1,
            "l": 499.5 + i * 0.1,
            "c": 500.2 + i * 0.1,
            "v": 1_000_000 + i * 100,
        })
    return out


# Dataset sintético — construido una vez al importar.
# Los 1H arrancan 50h antes del sim_datetime; los 15M 50*15min=12.5h antes.
_SYNTHETIC_DAILY = _synthetic_daily(210)
_SYNTHETIC_1H = _synthetic_intraday(50, "2026-04-13 08:00:00", 60)
_SYNTHETIC_15M = _synthetic_intraday(
    50, "2026-04-14 22:00:00", 15,  # 50*15min=12.5h antes de 10:30
)


def _load_fixture(path: Path | None = None) -> dict:
    """Carga el fixture canonical QQQ como dict (no como modelo Pydantic)."""
    p = path or _FIXTURE_PATH_DEFAULT
    return json.loads(p.read_text(encoding="utf-8"))


def run_healthcheck(fixture_path: Path | None = None) -> dict[str, Any]:
    """Corre el mini parity test y devuelve el resultado.

    Returns:
        Dict con:
            - `status`: `"green"` | `"yellow"` | `"red"`.
            - `error_code`: `None` | `"ENG-050"` | `"ENG-001"`.
            - `message`: detalle humano si aplica.
            - `duration_ms`: cuánto tardó.
    """
    import time

    start = time.perf_counter()
    try:
        fixture = _load_fixture(fixture_path)
    except (OSError, json.JSONDecodeError) as e:
        return {
            "status": "red",
            "error_code": ENG_001,
            "message": f"no se pudo leer fixture canonical: {e}",
            "duration_ms": (time.perf_counter() - start) * 1000.0,
        }

    try:
        out = analyze(
            ticker="QQQ",
            candles_daily=_SYNTHETIC_DAILY,
            candles_1h=_SYNTHETIC_1H,
            candles_15m=_SYNTHETIC_15M,
            fixture=fixture,
            spy_daily=_SYNTHETIC_DAILY,
            sim_datetime=_SIM_DATETIME_FIXED,
            sim_date=_SIM_DATE_FIXED,
            bench_daily=_SYNTHETIC_DAILY,
        )
    except Exception as e:
        # Invariante I3 violada — motor lanzó excepción.
        return {
            "status": "red",
            "error_code": ENG_001,
            "message": f"analyze() lanzó: {e.__class__.__name__}: {e}",
            "duration_ms": (time.perf_counter() - start) * 1000.0,
        }

    # Invariante: output debe tener las keys obligatorias.
    missing = sorted(_REQUIRED_KEYS - set(out.keys()))
    if missing:
        return {
            "status": "yellow",
            "error_code": ENG_050,
            "message": f"output sin keys obligatorias: {missing}",
            "duration_ms": (time.perf_counter() - start) * 1000.0,
        }

    # Invariante: error=False.
    if out.get("error"):
        return {
            "status": "yellow",
            "error_code": out.get("error_code") or ENG_050,
            "message": f"motor retornó error_code={out.get('error_code')}",
            "duration_ms": (time.perf_counter() - start) * 1000.0,
        }

    # Invariante: signal es string válido del vocabulario del spec.
    if out.get("signal") not in {"NEUTRAL", "SETUP", "REVISAR"}:
        return {
            "status": "yellow",
            "error_code": ENG_050,
            "message": (
                f"signal={out.get('signal')!r} fuera del vocabulario "
                "{NEUTRAL, SETUP, REVISAR}"
            ),
            "duration_ms": (time.perf_counter() - start) * 1000.0,
        }

    # Invariante: score es numérico.
    score = out.get("score")
    if not isinstance(score, (int, float)):
        return {
            "status": "yellow",
            "error_code": ENG_050,
            "message": f"score no numérico: {type(score).__name__}",
            "duration_ms": (time.perf_counter() - start) * 1000.0,
        }

    duration_ms = (time.perf_counter() - start) * 1000.0
    return {
        "status": "green",
        "error_code": None,
        "message": None,
        "duration_ms": duration_ms,
    }
