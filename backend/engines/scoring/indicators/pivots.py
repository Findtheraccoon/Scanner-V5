"""Pivot detection + key levels — soporte/resistencia para risks y output.

Port literal de Observatory `scoring.py:find_pivots()` líneas 95-129 y
`key_levels()` líneas 132-179. Dos roles:

1. **`find_pivots`** — detecta máximos/mínimos locales y los clusteriza
   por cercanía relativa. Usado por:
   - Risk fakeouts BB sup/inf (verifican si hay pivot cercano al
     fakeout, que confirma falsedad).
   - `key_levels()` (consumidor downstream).

2. **`key_levels`** — construye niveles ordenados de soporte/
   resistencia agregando MAs daily, BBs 1H/D y pivots, luego
   deduplica niveles cercanos. Es **output informativo** (no
   participa de confirms ni del score), pero forma parte del payload
   final del scanner.

**Paridad bit-a-bit:** se preservan exactamente:

- Estricto `>` y `<` en detección de pivot (no `>=`).
- Cluster: el threshold de tolerance se compara contra `group[0]`
  (primer valor agregado al grupo, no el promedio).
- Top-4 de cada lado por count `tx` descendente.
- Labels con flechas unicode `↑` `↓` y la `m` minúscula.
- Filtros `p > price * 1.001` y `p < price * 0.999` para evitar
  niveles "encima" del precio actual.
"""

from __future__ import annotations


def find_pivots(
    candles: list[dict],
    lookback: int = 50,
    tolerance: float = 0.003,
) -> dict:
    """Detecta pivots highs/lows en las últimas `lookback` velas y los
    agrupa en clusters por cercanía relativa.

    Un pivot high es un `h` estrictamente mayor que las 2 velas previas
    y las 2 posteriores (5 velas en total con la del medio como pico).
    Análogo para pivot lows con `l`.

    El **clustering** ordena los pivots y agrupa secuencialmente:
    cada nuevo pivot se agrega al grupo actual si su distancia
    relativa al `group[0]` (primer pivot del grupo, no el promedio)
    es menor que `tolerance`. Cada cluster reporta el promedio (`lv`)
    y la cantidad de toques (`tx`). Se devuelven los **top 4** por
    `tx` descendente.

    Args:
        candles: lista de velas (dicts con `h` y `l`).
        lookback: ventana hacia atrás para buscar pivots (default 50).
        tolerance: distancia relativa máxima dentro de un cluster
            (default 0.003 = 0.3%).

    Returns:
        Dict `{"r": [...], "s": [...]}` con resistencias (highs) y
        soportes (lows). Cada elemento es `{"lv": float, "tx": int}`.
        Vacío `{"r": [], "s": []}` si `len(candles) < lookback`.
    """
    if not candles or len(candles) < lookback:
        return {"r": [], "s": []}

    rec = candles[-lookback:]
    hi: list[float] = []
    lo: list[float] = []
    for i in range(2, len(rec) - 2):
        c = rec[i]
        if (
            c["h"] > rec[i - 1]["h"]
            and c["h"] > rec[i - 2]["h"]
            and c["h"] > rec[i + 1]["h"]
            and c["h"] > rec[i + 2]["h"]
        ):
            hi.append(c["h"])
        if (
            c["l"] < rec[i - 1]["l"]
            and c["l"] < rec[i - 2]["l"]
            and c["l"] < rec[i + 1]["l"]
            and c["l"] < rec[i + 2]["l"]
        ):
            lo.append(c["l"])

    return {"r": _cluster(hi, tolerance), "s": _cluster(lo, tolerance)}


def _cluster(arr: list[float], tolerance: float) -> list[dict]:
    """Clusteriza una lista de niveles por cercanía relativa.

    Ordena ascendente, agrupa secuencialmente comparando contra el
    primero del grupo (`group[0]`). Devuelve top 4 por count.
    """
    if not arr:
        return []
    sorted_arr = sorted(arr)
    clusters: list[dict] = []
    group: list[float] = [sorted_arr[0]]
    for i in range(1, len(sorted_arr)):
        if abs(sorted_arr[i] - group[0]) / group[0] < tolerance:
            group.append(sorted_arr[i])
        else:
            clusters.append({
                "lv": round(sum(group) / len(group), 2),
                "tx": len(group),
            })
            group = [sorted_arr[i]]
    clusters.append({
        "lv": round(sum(group) / len(group), 2),
        "tx": len(group),
    })
    return sorted(clusters, key=lambda x: x["tx"], reverse=True)[:4]


def key_levels(
    ind: dict,
    pivots_daily: dict,
    pivots_1h: dict,
    price: float,
) -> dict:
    """Construye listas de soportes y resistencias agregando MAs
    daily, BBs y pivots, deduplicando niveles cercanos (<0.2%).

    Es **output informativo** (no participa del score). Filtra
    niveles muy cercanos al precio actual con un buffer de 0.1%
    (`p > price * 1.001` para resistencias, `p < price * 0.999` para
    soportes) y devuelve los top 4 a cada lado.

    El parámetro `ind` debe tener (todos opcionales — se ignoran si
    son `None`):

    - `ma20D`, `ma40D`, `ma200D`: floats (medias móviles daily).
    - `bbH`: dict `{u, m, l}` (BB 1H).
    - `bbD`: dict `{u, l}` (BB daily).

    Args:
        ind: dict con indicadores (ver claves arriba).
        pivots_daily: salida de `find_pivots(candles_daily, ...)`.
        pivots_1h: salida de `find_pivots(candles_1h, ...)`.
        price: precio actual (último close).

    Returns:
        Dict `{"r": [...], "s": [...]}` con elementos
        `{"p": float, "l": str, "t": "r"|"s"}`. Top 4 cada lado.
    """
    all_levels: list[dict] = []

    # MAs daily como soporte/resistencia según posición vs precio
    for key, label in (("ma20D", "MA20D"), ("ma40D", "MA40D"), ("ma200D", "MA200D")):
        ma = ind.get(key)
        if ma:
            all_levels.append({
                "p": ma,
                "l": label,
                "t": "s" if price > ma else "r",
            })

    # BB 1H — upper resistencia, middle según precio, lower soporte
    bb_h = ind.get("bbH")
    if bb_h:
        all_levels.append({"p": bb_h["u"], "l": "BB↑1H", "t": "r"})
        all_levels.append({
            "p": bb_h["m"],
            "l": "BBm1H",
            "t": "s" if price > bb_h["m"] else "r",
        })
        all_levels.append({"p": bb_h["l"], "l": "BB↓1H", "t": "s"})

    # BB daily — upper resistencia, lower soporte (sin middle)
    bb_d = ind.get("bbD")
    if bb_d:
        all_levels.append({"p": bb_d["u"], "l": "BB↑D", "t": "r"})
        all_levels.append({"p": bb_d["l"], "l": "BB↓D", "t": "s"})

    # Pivots daily + 1H con count en el label
    for x in pivots_daily.get("r", []):
        all_levels.append({"p": x["lv"], "l": f"PivD({x['tx']}x)", "t": "r"})
    for x in pivots_daily.get("s", []):
        all_levels.append({"p": x["lv"], "l": f"PivD({x['tx']}x)", "t": "s"})
    for x in pivots_1h.get("r", []):
        all_levels.append({"p": x["lv"], "l": f"Piv1H({x['tx']}x)", "t": "r"})
    for x in pivots_1h.get("s", []):
        all_levels.append({"p": x["lv"], "l": f"Piv1H({x['tx']}x)", "t": "s"})

    # Dedup niveles cercanos (<0.2%): si el nuevo es un Piv, se
    # fusiona appendeando al label del existente. Si no, se descarta.
    deduped: list[dict] = []
    for lv in sorted(all_levels, key=lambda x: x["p"]):
        existing = next(
            (d for d in deduped if abs(d["p"] - lv["p"]) / lv["p"] < 0.002),
            None,
        )
        if existing is None:
            deduped.append(lv)
        elif "Piv" in lv["l"]:
            existing["l"] += " +" + lv["l"]

    resistances = sorted(
        [lv for lv in deduped if lv["p"] > price * 1.001],
        key=lambda x: x["p"],
    )[:4]
    supports = sorted(
        [lv for lv in deduped if lv["p"] < price * 0.999],
        key=lambda x: x["p"],
        reverse=True,
    )[:4]
    return {"r": resistances, "s": supports}
