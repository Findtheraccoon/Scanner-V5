"""Builders de output estructurado del Scoring Engine.

El motor NUNCA lanza excepciones hacia el caller (invariante I3 del
spec §3). Los errores operativos se materializan como dicts con
`error=True` y `error_code="ENG-XXX"`. Las señales ordinarias tienen
`error=False`.

Estas funciones garantizan que toda salida del motor tenga la forma
completa descrita en `SCORING_ENGINE_SPEC.md §2.3`, sin importar el
camino que tomó el flujo interno.
"""

from __future__ import annotations

from typing import Any

from engines.scoring.constants import (
    CONF_UNKNOWN,
    ENGINE_VERSION,
    SIGNAL_NEUTRAL,
)


def build_error_output(
    *,
    ticker: str,
    error_code: str,
    error_detail: str,
    fixture_id: str = "",
    fixture_version: str = "",
) -> dict[str, Any]:
    """Construye un output con `error=True` conservando la forma completa.

    Usado cuando el motor no puede producir una señal (fixture inválida,
    candles insuficientes, excepción inesperada, etc.).

    Args:
        ticker: echo del input ticker.
        error_code: uno de los códigos `ENG-XXX` definidos en constants.
        error_detail: texto humano que explica la causa. Se loguea en
            `layers.error_detail` para trazabilidad.
        fixture_id: si la fixture pudo parsearse antes del error, su id.
        fixture_version: si la fixture pudo parsearse, su versión.
    """
    return {
        "ticker": ticker,
        "engine_version": ENGINE_VERSION,
        "fixture_id": fixture_id,
        "fixture_version": fixture_version,
        "score": 0.0,
        "conf": CONF_UNKNOWN,
        "signal": SIGNAL_NEUTRAL,
        "dir": None,
        "blocked": None,
        "error": True,
        "error_code": error_code,
        "layers": {"error_detail": error_detail},
        "ind": {},
        "patterns": [],
        "sec_rel": None,
        "div_spy": None,
    }


def build_neutral_output(
    *,
    ticker: str,
    fixture_id: str,
    fixture_version: str,
    blocked: str | None = None,
    layers: dict[str, Any] | None = None,
    ind: dict[str, Any] | None = None,
    patterns: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Construye un output sin señal (no-error, sin trigger o bloqueado).

    Usado cuando el motor corrió OK pero los gates no pasaron o no
    hubo triggers. `score=0`, `dir=None`, `error=False`. Si `blocked`
    tiene valor, describe qué gate falló.
    """
    return {
        "ticker": ticker,
        "engine_version": ENGINE_VERSION,
        "fixture_id": fixture_id,
        "fixture_version": fixture_version,
        "score": 0.0,
        "conf": CONF_UNKNOWN,
        "signal": SIGNAL_NEUTRAL,
        "dir": None,
        "blocked": blocked,
        "error": False,
        "error_code": None,
        "layers": layers if layers is not None else {},
        "ind": ind if ind is not None else {},
        "patterns": patterns if patterns is not None else [],
        "sec_rel": None,
        "div_spy": None,
    }
