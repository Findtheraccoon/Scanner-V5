"""Construcción del callable de probe de TD keys que consume el
Validator Check G.

Antes vivía como `_build_td_probe` privado en `backend/main.py`. Se
extrajo cuando `api/routes/config.py` necesitó reconstruir el probe
al hot-reload de keys vía UI (BUG-001 capa 2): el lifespan original
construía el probe sólo si `SCANNER_TWELVEDATA_KEYS` venía por env
var, así que cuando el usuario las cargaba desde Configuración el
Validator quedaba con `td_probe=None` y el endpoint
`POST /validator/connectivity` devolvía `skip` para siempre.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from engines.data.api_keys import ApiKeyConfig
    from engines.data.fetcher import TwelveDataClient

TDProbe = Callable[[], Awaitable[list[dict[str, Any]]]]


def build_td_probe(
    keys: list[ApiKeyConfig], client: TwelveDataClient,
) -> TDProbe:
    """Devuelve un async callable que prueba cada key con `test_key`.

    El callable retorna una lista de dicts
    `[{"key_id": str, "ok": bool, "error"?: str}, ...]` que el Check G
    consume directamente.
    """

    async def probe() -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for key in keys:
            try:
                ok = await client.test_key(key)
                results.append({"key_id": key.key_id, "ok": ok})
            except Exception as e:
                results.append(
                    {
                        "key_id": key.key_id,
                        "ok": False,
                        "error": f"{type(e).__name__}: {e}",
                    },
                )
        return results

    return probe
