"""Regression guard — parity 100%.

Post cierre Fase 5.4 (2 fixes: aggregator.reset_day + ORB.vol_ratio_intraday),
el motor de scoring matchea bit-a-bit al Observatory sobre 245 señales
del sample canonical QQQ. Este test falla si alguien introduce un cambio
que baja el match rate — protección contra regresiones en:

- `engines/scoring/aggregator.py` (bucket semantics, reset_day).
- `engines/scoring/analyze.py` (`vol_ratio_intraday` wiring al ORB gate).
- Detección de triggers/confirms si se agregan nuevos.

**Marcado como `slow`:** tarda ~2min (245 llamadas a `analyze()` con
slicing completo por timestamp). Se excluye del `pytest -q` estándar;
correr explícito con `pytest -m slow` antes de cerrar un PR que toque
scoring/aggregator/triggers.
"""

from __future__ import annotations

import pytest

from modules.validator.checks import f_parity


@pytest.mark.slow
@pytest.mark.parity
@pytest.mark.asyncio
async def test_parity_100_percent_vs_observatory_sample() -> None:
    """El motor matchea exacto las 245 señales del sample canonical.

    Post-Fase 5.4. Si este test falla, revisar:
    - `sample_diffs` del resultado para ver qué campos divergen.
    - Gotchas #16 (aggregator reset_day) y #17 (ORB vol_ratio_intraday)
      en `CLAUDE.md` — probablemente una regresión sobre esos fixes.
    """
    result = await f_parity.run(limit=None)
    stats = result.details

    # No debe haber errores (el motor nunca debe lanzar I3).
    assert stats["errors"] == 0, (
        f"motor lanzó en {stats['errors']} señales: {stats.get('sample_diffs')}"
    )

    # Sin mismatches ni errores → match rate = 100%.
    assert stats["match_rate"] == 1.0, (
        f"parity {stats['matches']}/{stats['total']} = "
        f"{stats['match_rate']:.2%} — regression detectada. "
        f"Primeros diffs: {stats.get('sample_diffs', [])[:3]}"
    )

    # Paranoia: el total debe ser exactamente el del sample.
    assert stats["total"] == 245
