"""Helper de lookup de métricas (WR@30) por banda desde el sibling
`<fixture_id>.metrics.json` del canonical.

Cada canonical tiene un archivo `<fixture_id>.metrics.json` adyacente que
incluye `metrics_training.by_band[BAND].wr_pct` y `mfe_mae`. Este helper
expone una función `get_band_metrics(fixtures_dir, fixture_id, band)`
que devuelve el `wr_pct` (float) o `None` si no hay datos.

Cache LRU para evitar re-leer el JSON en cada request.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

# Mapeo de band literal → key en metrics. El canonical usa "A_plus" / "S_plus"
# (snake_case con guión bajo) mientras que las signals usan "A+" / "S+".
_BAND_KEY_MAP: dict[str, str] = {
    "S+": "S_plus",
    "S": "S",
    "A+": "A_plus",
    "A": "A",
    "B": "B",
    "REVISAR": "REVISAR",
}


@lru_cache(maxsize=32)
def _load_metrics(metrics_path: str) -> dict | None:
    """Lee el archivo de métricas. Cache por path absoluto."""
    p = Path(metrics_path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def get_band_wr_pct(
    fixtures_dir: Path | str,
    fixture_id: str,
    band: str | None,
) -> float | None:
    """Devuelve `wr_pct` para `band` del canonical `fixture_id`.

    Returns:
        float (0..100) si el band tiene métrica, `None` si:
        - El archivo `<fixture_id>.metrics.json` no existe
        - El band no está en el mapa de bandas conocidas
        - El band no tiene métrica training
    """
    if not band or band not in _BAND_KEY_MAP:
        return None
    metrics_path = Path(fixtures_dir) / f"{fixture_id}.metrics.json"
    metrics = _load_metrics(str(metrics_path.resolve()))
    if metrics is None:
        return None
    by_band = (metrics.get("metrics_training") or {}).get("by_band") or {}
    band_key = _BAND_KEY_MAP[band]
    band_metrics = by_band.get(band_key)
    if not isinstance(band_metrics, dict):
        return None
    wr = band_metrics.get("wr_pct")
    return float(wr) if isinstance(wr, (int, float)) else None
