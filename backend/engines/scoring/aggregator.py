"""Agregación de velas 1-minuto a 15M y 1H.

Port de la convención que usa el Observatory scanner sobre velas
1-minuto de TwelveData: buckets **open-timestamped** (el `dt` del
bucket es el minuto de apertura, no el de cierre), con la última
vela **parcial** si el timestamp de corte cae dentro del bucket.

**Convención verificada con `parity_qqq_sample.json`:**

    signal.timestamp = "2025-01-02 12:30:00"
    signal.price_at_signal = 509.086395
    → close de 1min "12:30:00" = 509.086 ✓

    signal.timestamp = "2025-01-07 09:45:00"
    signal.price_at_signal = 525.35901
    → close de 1min "09:45:00" = 525.359 ✓

En ambos casos, el `price_at_signal` coincide con el close de la vela
1-minuto cuyo `dt` matchea el timestamp de la señal. Esto significa
que el scanner al momento T construye la vela 15M "T" con el primer
minuto ya disponible y lo usa como "close en formación".

**Buckets:**

    15M "T" = agg de 1min [T, T+14] inclusive, `dt=T`.
    1H  "T" = agg de 1min [T, T+59] inclusive, `dt=T`, alineado a HH:00.

**Última vela parcial:**

    Si el timestamp de corte `until_dt` cae dentro del bucket abierto,
    se emite la vela parcial con los minutos disponibles
    [bucket_open, until_dt] (inclusive ambos lados).

**OHLC agregación:**

    o = primer open del bucket
    h = max de highs
    l = min de lows
    c = último close del bucket
    v = suma de volumes
"""

from __future__ import annotations


def _parse_dt(dt: str) -> tuple[str, int, int]:
    """Descompone `YYYY-MM-DD HH:MM:SS` en `(date, hour, minute)`."""
    return dt[:10], int(dt[11:13]), int(dt[14:16])


def _bucket_15m_open(dt: str) -> str:
    """Calcula el `dt` del bucket 15M open-stamped al que pertenece `dt`.

    El bucket 15M cubre `[bucket_dt, bucket_dt + 14min]` inclusive. El
    minuto se redondea hacia abajo al múltiplo de 15 más cercano.
    """
    date, h, m = _parse_dt(dt)
    bucket_m = (m // 15) * 15
    return f"{date} {h:02d}:{bucket_m:02d}:00"


def _bucket_1h_open(dt: str) -> str:
    """Calcula el `dt` del bucket 1H open-stamped al que pertenece `dt`.

    Alineado a HH:00. Bucket cubre `[HH:00, HH:59]` inclusive.
    """
    date, h, _ = _parse_dt(dt)
    return f"{date} {h:02d}:00:00"


def aggregate_1min(
    candles_1min: list[dict],
    bucket_fn,
    until_dt: str | None = None,
    include_partial: bool = True,
) -> list[dict]:
    """Agrega velas 1-minuto según `bucket_fn` (función que recibe dt
    y devuelve el dt del bucket).

    Args:
        candles_1min: lista ordenada (oldest→newest) de velas 1-minuto
            con claves `dt, o, h, l, c, v`.
        bucket_fn: `_bucket_15m_open` o `_bucket_1h_open`.
        until_dt: si se pasa, descarta velas 1min con `dt > until_dt`
            (permite slicing sin look-ahead).
        include_partial: si `False`, descarta el último bucket si es
            parcial (no tuvo el minuto final del bucket). Útil para
            emular la convención Observatory donde 1H solo usa buckets
            completamente cerrados mientras 15M sí incluye la parcial.

    Returns:
        Lista ordenada de velas agregadas.
    """
    if not candles_1min:
        return []
    if until_dt is not None:
        candles_1min = [c for c in candles_1min if c["dt"] <= until_dt]
    if not candles_1min:
        return []

    result: list[dict] = []
    current_bucket: str | None = None
    bucket_candles: list[dict] = []

    for candle in candles_1min:
        bucket_dt = bucket_fn(candle["dt"])
        if bucket_dt != current_bucket:
            if bucket_candles:
                result.append(_agg_bucket(current_bucket, bucket_candles))
            current_bucket = bucket_dt
            bucket_candles = [candle]
        else:
            bucket_candles.append(candle)

    if bucket_candles:
        result.append(_agg_bucket(current_bucket, bucket_candles))

    if not include_partial and result and until_dt is not None:
        # El último bucket es parcial si su "next open" es posterior a until_dt.
        # Para 15M [T, T+14]: bucket cerró cuando hay vela del bucket siguiente.
        # Simplificación: detectar si el último 1min del bucket es el último
        # minuto esperado (T+14 para 15M, HH:59 para 1H). Si no, descartar.
        last_bucket = result[-1]
        last_1min = bucket_candles[-1]
        # Si el bucket no tiene la vela final esperada, es parcial.
        if _is_partial_bucket(last_bucket["dt"], last_1min["dt"], bucket_fn):
            result.pop()
    return result


def _is_partial_bucket(bucket_dt: str, last_1min_dt: str, bucket_fn) -> bool:
    """Heurística: un bucket es parcial si el siguiente minuto después
    del último 1min sigue perteneciendo al mismo bucket."""
    from datetime import datetime, timedelta
    t = datetime.strptime(last_1min_dt, "%Y-%m-%d %H:%M:%S")
    next_min = (t + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
    return bucket_fn(next_min) == bucket_dt


def _agg_bucket(bucket_dt: str, candles: list[dict]) -> dict:
    """Aplica OHLC aggregation sobre las velas del bucket."""
    return {
        "dt": bucket_dt,
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
    """Agrega 1-minuto a velas 15M open-stamped.

    Buckets: [HH:00, HH:14], [HH:15, HH:29], [HH:30, HH:44], [HH:45, HH:59].

    **Por default `include_partial=True`** porque el scanner Observatory
    construye la vela 15M en curso con los minutos disponibles — el
    close del bucket abierto matchea `price_at_signal` del sample.
    """
    return aggregate_1min(candles_1min, _bucket_15m_open, until_dt, include_partial)


def aggregate_to_1h(
    candles_1min: list[dict],
    until_dt: str | None = None,
    include_partial: bool = True,
) -> list[dict]:
    """Agrega 1-minuto a velas 1H open-stamped alineadas a HH:00.

    **Por default `include_partial=True`** (comportamiento genérico).
    Para paridad con Observatory en replay mode se recomienda pasar
    `include_partial=False` — la MA20/MA40 1H se calcula sobre buckets
    completamente cerrados únicamente, y `candles_1h[-1]` es la última
    hora cerrada (no la en curso).
    """
    return aggregate_1min(candles_1min, _bucket_1h_open, until_dt, include_partial)
