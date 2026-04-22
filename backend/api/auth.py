"""Autenticación Bearer token para endpoints REST (ADR-0001).

Cada request debe traer `Authorization: Bearer sk-XXX` con una key
válida. Las keys válidas viven en `app.state.valid_api_keys` — se
configuran en `create_app()` al inicializar la app.

**Errores:**

- 401 si falta el header `Authorization`.
- 401 si el scheme no es `Bearer`.
- 401 si el token no está en el set de keys válidas.
- 500 si la app no tiene `valid_api_keys` configuradas (bug).

**WebSocket:** el handshake usa `?token=sk-XXX` — la verificación
corresponde al endpoint WebSocket, no a este middleware (ver C5.5).
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_auth(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    """Dependency que valida el Bearer token contra `app.state.valid_api_keys`.

    Retorna el token (para trazabilidad en logs). Los handlers que
    quieran saber qué key autenticó el request lo reciben como arg.

    Args:
        request: request FastAPI (acceso a `app.state`).
        creds: credenciales parseadas del header (o `None` si falta).

    Raises:
        HTTPException 401: header faltante o token inválido.
        HTTPException 500: app mal configurada.
    """
    valid = getattr(request.app.state, "valid_api_keys", None)
    if valid is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth not configured",
        )
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    if creds.credentials not in valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return creds.credentials
