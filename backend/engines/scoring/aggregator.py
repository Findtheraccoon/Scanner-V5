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
) -> list[dict]:
    """Agrega velas 1-minuto según `bucket_fn` (función que recibe dt
    y devuelve el dt del bucket).

    Args:
        candles_1min: lista ordenada (oldest→newest) de velas 1-minuto
            con claves `dt, o, h, l, c, v`.
        bucket_fn: `_bucket_15m_open` o `_bucket_1h_open`.
        until_dt: si se pasa, descarta velas 1min con `dt > until_dt`
            (permite slicing sin look-ahead).

    Returns:
        Lista ordenada de velas agregadas. La última puede ser parcial
        si `until_dt` cae dentro de un bucket.
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
    return result


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
) -> list[dict]:
    """Agrega 1-minuto a velas 15M open-stamped.

    Buckets: [HH:00, HH:14], [HH:15, HH:29], [HH:30, HH:44], [HH:45, HH:59].
    """
    return aggregate_1min(candles_1min, _bucket_15m_open, until_dt)


def aggregate_to_1h(
    candles_1min: list[dict],
    until_dt: str | None = None,
) -> list[dict]:
    """Agrega 1-minuto a velas 1H open-stamped alineadas a HH:00.

    El primer bucket de cada día (09:00 en US market) puede ser parcial
    — agrupa desde 09:30 en vez de 09:00.
    """
    return aggregate_1min(candles_1min, _bucket_1h_open, until_dt)
