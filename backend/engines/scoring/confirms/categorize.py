"""Categorización y dedup de confirms para el cálculo de score final.

Port literal de Observatory `scoring.py:_categorize_confirm()` líneas
203-215. Mapea la descripción (`d`) de un confirm a una de las 10
categorías canónicas. El orden de los `if` sigue el Observatory
bit-a-bit — no reordenar sin revisar todos los casos de paridad.

**Ambigüedad resuelta por orden:** un string puede matchear varios
prefijos (ej. "BB sup 1H" también empieza con "BB"). Observatory
siempre chequea la categoría más específica primero (BB sup/inf
Daily → BB sup/inf 1H, etc.). Preservamos ese orden.

**Paridad crítica con `_categorize_confirm` Observatory:**

    FzaRel            → `desc.startswith("FzaRel")`
    BBsup_D           → `desc.startswith("BB sup D")`
    BBinf_D           → `desc.startswith("BB inf D")`
    BBsup_1H          → `desc.startswith("BB sup 1H")`
    BBinf_1H          → `desc.startswith("BB inf 1H")`
    VolSeq            → `desc.startswith("Vol creciente")`
    VolHigh           → `"x avg" in desc`  (no es prefix, es substring)
    Gap               → `desc.startswith("Gap")`
    SqExp             → `desc.startswith("Squeeze")`
    DivSPY            → `desc.startswith("Div SPY")`
"""

from __future__ import annotations


def categorize_confirm(desc: str) -> str | None:
    """Mapea la descripción de un confirm a su categoría canónica.

    Args:
        desc: el campo `d` del `ConfirmDict`.

    Returns:
        Uno de los 10 labels de categoría, o `None` si el string no
        matchea ninguno (no debería pasar con confirms emitidos por
        el motor V5, pero el fallback a `None` permite que los pesos
        se descarten silenciosamente — paridad Observatory).
    """
    if desc.startswith("FzaRel"):
        return "FzaRel"
    if desc.startswith("BB sup D"):
        return "BBsup_D"
    if desc.startswith("BB inf D"):
        return "BBinf_D"
    if desc.startswith("BB sup 1H"):
        return "BBsup_1H"
    if desc.startswith("BB inf 1H"):
        return "BBinf_1H"
    if desc.startswith("Vol creciente"):
        return "VolSeq"
    if "x avg" in desc:
        return "VolHigh"
    if desc.startswith("Gap"):
        return "Gap"
    if desc.startswith("Squeeze"):
        return "SqExp"
    if desc.startswith("Div SPY"):
        return "DivSPY"
    return None


def apply_confirm_weights(
    confirms: list[dict],
    weights: dict[str, float],
) -> tuple[float, list[dict]]:
    """Suma los pesos del fixture aplicando dedup por categoría.

    Port literal de Observatory `scoring.py` líneas 310-318:

        new_confirm_sum = 0
        seen_cats = set()
        for p in confirms:
            cat = _categorize_confirm(p["d"])
            if cat and cat not in seen_cats:
                seen_cats.add(cat)
                new_confirm_sum += NEW_CONFIRM_WEIGHTS.get(cat, 0)

    Si un confirm dispara dos variantes de la misma categoría (ej. dos
    confirms de BB inf 1H con precios distintos), solo el **primero**
    suma — los subsiguientes se deduplican. El orden del input determina
    cuál gana, igual que Observatory.

    Args:
        confirms: lista de confirms (`ConfirmDict`), típicamente ya
            filtrada por dirección y tipo (`cat=="CONFIRM"`).
        weights: mapeo `{"BBinf_1H": 3.0, "FzaRel": 4.0, ...}` del
            `fixture.confirm_weights`. Faltantes se tratan como 0.

    Returns:
        Tupla `(confirm_sum, items)` donde `items` es la lista de
        `{"category": str, "weight": float, "desc": str, ...}` de los
        confirms que efectivamente contribuyeron al score (sin
        duplicados). Útil para trazabilidad en `layers.confirm.items`.
    """
    total: float = 0.0
    seen: set[str] = set()
    items: list[dict] = []
    for c in confirms:
        cat = categorize_confirm(c["d"])
        if cat is None or cat in seen:
            continue
        seen.add(cat)
        weight = weights.get(cat, 0.0)
        total += weight
        items.append({
            "category": cat,
            "weight": weight,
            "desc": c["d"],
            "tf": c.get("tf", ""),
            "sg": c.get("sg", ""),
        })
    return round(total, 2), items
