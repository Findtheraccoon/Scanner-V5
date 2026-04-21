"""Envolvente alcista/bajista 1H — 2 triggers del total de 14.

Port literal de scanner_v4.2.1.html líneas 424-430.

Un engulfing alcista es una vela bull (close ≥ open) cuyo body "envuelve"
al body de la vela anterior bear, y además es al menos 10% más grande.
El bajista es el espejo.

Reglas exactas del v4.2.1 (no decay — solo se chequea la vela 1H
actual vs la previa, no se mira en edades anteriores):

    Envolvente alcista 1H:
        curr_bull AND NOT prev_bull
        AND curr.o ≤ prev.c
        AND curr.c ≥ prev.o
        AND curr_body > prev_body * 1.1
        → CALL w=3.0

    Envolvente bajista 1H:
        NOT curr_bull AND prev_bull
        AND curr.o ≥ prev.c
        AND curr.c ≤ prev.o
        AND curr_body > prev_body * 1.1
        → PUT w=3.0
"""

from __future__ import annotations

from engines.scoring.triggers._helpers import candle_body, is_bull

_ENGULF_BODY_RATIO_MIN: float = 1.1
_WEIGHT_ENGULFING: float = 3.0


def detect_engulfing_1h(candles_1h: list[dict]) -> list[dict]:
    """Detecta engulfing 1H sobre la última y penúltima vela.

    Args:
        candles_1h: lista de velas 1H antigua→reciente. Se usan las
            últimas 2.

    Returns:
        Lista de `TriggerDict`. Vacía si `len < 2`, si las velas son
        de la misma dirección, o si las condiciones no se cumplen.
        Contiene a lo sumo 1 trigger — alcista y bajista son
        mutuamente excluyentes por el test de dirección.
    """
    if len(candles_1h) < 2:
        return []
    prev = candles_1h[-2]
    curr = candles_1h[-1]
    curr_body = candle_body(curr)
    prev_body = candle_body(prev)
    curr_bull = is_bull(curr)
    prev_bull = is_bull(prev)

    triggers: list[dict] = []

    # Alcista: curr bull, prev bear, envuelve el body previo
    if (
        curr_bull
        and not prev_bull
        and curr["o"] <= prev["c"]
        and curr["c"] >= prev["o"]
        and curr_body > prev_body * _ENGULF_BODY_RATIO_MIN
    ):
        triggers.append(
            {
                "tf": "1H",
                "d": "Envolvente alcista 1H",
                "sg": "CALL",
                "w": _WEIGHT_ENGULFING,
                "cat": "TRIGGER",
                "age": 0,
            }
        )

    # Bajista: curr bear, prev bull, envuelve el body previo (espejo)
    if (
        not curr_bull
        and prev_bull
        and curr["o"] >= prev["c"]
        and curr["c"] <= prev["o"]
        and curr_body > prev_body * _ENGULF_BODY_RATIO_MIN
    ):
        triggers.append(
            {
                "tf": "1H",
                "d": "Envolvente bajista 1H",
                "sg": "PUT",
                "w": _WEIGHT_ENGULFING,
                "cat": "TRIGGER",
                "age": 0,
            }
        )

    return triggers
