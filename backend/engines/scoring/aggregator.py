"""Agregación de velas 1-minuto a 15M y 1H.

Port de la semántica del `CandleBuilder` de Observatory (ver
`docs/specs/Observatory/Current/Replay/candle_builder.py`): el bucket
se identifica por `(date, hour, minute_bucket_15m)` o `(date, hour)`
de modo que al cambiar de día **el bucket en construcción se
descarta** (la lógica `reset_day()` del CandleBuilder, líneas 94-99
del replay).

Esto corrige el bug port que descubrimos al validar con las 1min
originales del Observatory: mi versión previa agrupaba por `HH:00`
round sin mirar la fecha, lo que hacía que la primera vela 1H del
día se rotulara `HH:00:00` (y acumulara cualquier pre-market del
mismo bucket hora). Observatory, en cambio, al ver la primera 1min
del nuevo día resetea el state y el bucket arranca con el `dt` de
esa primera 1min (típicamente `09:30:00` en mercado US).

**Convenciones verificadas:**

- El `dt` de la vela agregada es el `dt` de la **primera 1-minuto**
  del bucket, no un `HH:00` round. Si el día arranca a 09:30, la
  primera vela 1H tendrá `dt = "2025-02-12 09:30:00"`.
- Bucket 15M: 4 por hora, alineados a `minute // 15` (00, 15, 30, 45).
- Bucket 1H: 1 por hora de reloj.
- Cambio de día → bucket en construcción se descarta (no persiste
  en el resultado).

**`include_partial`:**

- `True` (default): el último bucket se incluye aunque no haya
  recibido el minuto final esperado (vela parcial).
- `False`: descarta el último bucket si su próximo minuto esperado
  cae dentro del mismo bucket (todavía no está cerrado).

**`price_at_signal` sigue coincidiendo con el close 1min del timestamp
de la señal** — validado con `parity_qqq_sample.json` y
`qqq_1min.json` del Observatory.
"""

from __future__ import annotations

from collections.abc import Callable


def _parse_dt(dt: str) -> tuple[str, int, int]:
    """Descompone `YYYY-MM-DD HH:MM:SS` en `(date, hour, minute)`."""
    return dt[:10], int(dt[11:13]), int(dt[14:16])


def _bucket_key_15m(dt: str) -> tuple:
    """Key del bucket 15M: `(date, hour, minute // 15)`.

    Cambios de día → key distinta → bucket previo se cierra.
    """
    date, h, m = _parse_dt(dt)
    return (date, h, m // 15)


def _bucket_key_1h(dt: str) -> tuple:
    """Key del bucket 1H: `(date, hour)`.

    Cambios de día → key distinta → bucket previo se cierra/descarta.
    """
    date, h, _ = _parse_dt(dt)
    return (date, h)


def aggregate_1min(
    candles_1min: list[dict],
    bucket_key_fn: Callable[[str], tuple],
    until_dt: str | None = None,
    include_partial: bool = True,
) -> list[dict]:
    """Agrega velas 1-minuto bucketing por `bucket_key_fn`.

    Args:
        candles_1min: lista ordenada oldest→newest de velas 1-minuto
            con claves `dt, o, h, l, c, v`.
        bucket_key_fn: función que devuelve la key (hashable/comparable)
            del bucket al que pertenece un `dt`. Dos claves iguales =
            mismo bucket. Incluir la fecha asegura reset al cambio de día.
        until_dt: descarta velas 1min con `dt > until_dt` (slicing
            sin look-ahead).
        include_partial: ver doc del módulo.

    Returns:
        Lista ordenada de velas agregadas. `dt` de cada vela = `dt` de
        la primera 1-minuto del bucket.
    """
    if until_dt is not None:
        candles_1min = [c for c in candles_1min if c["dt"] <= until_dt]
    if not candles_1min:
        return []

    result: list[dict] = []
    current_key: tuple | None = None
    bucket_candles: list[dict] = []

    for candle in candles_1min:
        key = bucket_key_fn(candle["dt"])
        if current_key is not None and key != current_key:
            # Cambio de bucket. Si además cambió la fecha, descartamos el
            # bucket previo emulando el `reset_day()` del CandleBuilder de
            # Observatory (líneas 94-99 del replay): al recibir la primera
            # 1-min del día nuevo, `building_*` se pone a None sin haber
            # sido pusheado a `candles_*`. Efecto práctico: la última hora
            # del día anterior (típicamente 15:xx en mercado US) no
            # persiste en el historial 1H.
            prev_date = current_key[0]
            new_date = key[0]
            if prev_date == new_date:
                result.append(_agg_bucket(bucket_candles))
            # else: cambio de día → descartar bucket_candles silenciosamente.
            bucket_candles = []
        current_key = key
        bucket_candles.append(candle)

    if bucket_candles:
        if include_partial:
            result.append(_agg_bucket(bucket_candles))
        else:
            # El bucket se considera cerrado solo si el siguiente minuto
            # esperado ya no pertenece al mismo bucket.
            from datetime import datetime, timedelta

            last = bucket_candles[-1]["dt"]
            t = datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
            next_min = (t + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
            if bucket_key_fn(next_min) != current_key:
                result.append(_agg_bucket(bucket_candles))
            # else: bucket parcial, descartar

    return result


def _agg_bucket(candles: list[dict]) -> dict:
    """OHLC + volumen sobre las 1-min del bucket. `dt` = primera 1-min."""
    return {
        "dt": candles[0]["dt"],
        "o": candles[0]["o"],
        "h": max(c["h"] for c in candles),
        "l": min(c["l"] for c in candles),
        "c": candles[-1]["c"],
        "v": sum(c["v"] for c in candles),
    }


def aggregate_to_15m(
    candles_1min: list[dict],
    until_dt: str | None = None,
    include_partial: bool = True,
) -> list[dict]:
    """Agrega 1-minuto a velas 15M usando bucket `(date, hour, m//15)`.

    Default `include_partial=True` porque el scanner Observatory
    construye la vela 15M en curso con los minutos disponibles.
    """
    return aggregate_1min(
        candles_1min, _bucket_key_15m, until_dt, include_partial,
    )


def aggregate_to_1h(
    candles_1min: list[dict],
    until_dt: str | None = None,
    include_partial: bool = True,
) -> list[dict]:
    """Agrega 1-minuto a velas 1H usando bucket `(date, hour)`.

    **Por default `include_partial=True`** (comportamiento genérico).
    Para paridad con Observatory en replay mode usar `include_partial=False`
    — la MA20/MA40 1H se calcula sobre buckets completamente cerrados.
    """
    return aggregate_1min(
        candles_1min, _bucket_key_1h, until_dt, include_partial,
    )
