"""Módulo API — FastAPI app + routers REST + WebSocket.

Expone `create_app(...)` como único factory público. La configuración
(API keys válidas, URL de DB, etc.) se pasa vía parámetros — la app
es creable múltiples veces en tests con settings distintos.
"""

from api.app import create_app

__all__ = ["create_app"]
