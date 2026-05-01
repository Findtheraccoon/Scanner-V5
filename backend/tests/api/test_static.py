"""Tests del SPA fallback con assertion de containment (SEC-001).

`_mount_frontend` sirve los assets del frontend buildeado debajo de
`/` con un fallback al `index.html` para que React Router maneje el
routing. El handler antes era vulnerable a path traversal: una request
del estilo `/..%2Fdata%2Fbearer.txt` traversaba fuera del static dir
y filtraba archivos sensibles del backend cwd al caller anónimo.

Estos tests cubren:
- Servir el index al root + a un path arbitrario (SPA fallback).
- Servir un archivo real dentro del static dir.
- Rechazar path traversal con `..` y variantes URL-encoded.
- Rechazar paths absolutos (`/etc/passwd` style).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api import create_app
from modules.db import init_db


@pytest.fixture
def static_workspace(tmp_path: Path) -> tuple[Path, Path]:
    """Workspace con un static_dir minimalista y un archivo sensible
    afuera, simulando el bearer.txt del launcher productivo."""
    base = tmp_path / "static"
    base.mkdir()
    (base / "index.html").write_text(
        "<html><head></head><body>scanner spa marker</body></html>",
        encoding="utf-8",
    )
    (base / "assets").mkdir()
    (base / "assets" / "app.js").write_text(
        "console.log('asset')", encoding="utf-8",
    )
    (base / "favicon.ico").write_bytes(b"\x00\x00")
    # Archivo sensible afuera del static dir — objetivo del traversal.
    sensitive = tmp_path / "bearer.txt"
    sensitive.write_text("super-secret-bearer-token", encoding="utf-8")
    return base, sensitive


@pytest_asyncio.fixture
async def static_client(static_workspace: tuple[Path, Path]):
    base, _ = static_workspace
    app = create_app(
        valid_api_keys={"sk-test"},
        db_url="sqlite+aiosqlite:///:memory:",
        auto_init_db=False,
        static_dir=str(base),
        frontend_bearer="injected-bearer",
    )
    await init_db(app.state.db_engine)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await app.state.db_engine.dispose()


# ═══════════════════════════════════════════════════════════════════════════
# Comportamiento esperado del SPA fallback
# ═══════════════════════════════════════════════════════════════════════════


class TestSpaFallback:
    @pytest.mark.asyncio
    async def test_root_serves_index_with_bearer_meta(self, static_client) -> None:
        r = await static_client.get("/")
        assert r.status_code == 200
        assert "scanner spa marker" in r.text
        assert 'name="scanner-bearer"' in r.text

    @pytest.mark.asyncio
    async def test_unknown_path_falls_back_to_index(self, static_client) -> None:
        """React Router maneja rutas SPA — la respuesta es el index."""
        r = await static_client.get("/cockpit")
        assert r.status_code == 200
        assert "scanner spa marker" in r.text

    @pytest.mark.asyncio
    async def test_real_file_inside_static_is_served(self, static_client) -> None:
        r = await static_client.get("/favicon.ico")
        assert r.status_code == 200
        assert r.content == b"\x00\x00"


# ═══════════════════════════════════════════════════════════════════════════
# SEC-001 — path traversal
# ═══════════════════════════════════════════════════════════════════════════


class TestPathTraversalRejection:
    @pytest.mark.asyncio
    async def test_dotdot_url_encoded_returns_spa_index_not_file(
        self, static_client,
    ) -> None:
        """`/..%2Fbearer.txt` no debe leer el archivo afuera del static."""
        r = await static_client.get("/..%2Fbearer.txt")
        assert r.status_code == 200
        assert "super-secret-bearer-token" not in r.text
        assert "scanner spa marker" in r.text

    @pytest.mark.asyncio
    async def test_dotdot_double_url_encoded(self, static_client) -> None:
        """Variante `%2E%2E%2Fbearer.txt`."""
        r = await static_client.get("/%2E%2E%2Fbearer.txt")
        assert r.status_code == 200
        assert "super-secret-bearer-token" not in r.text

    @pytest.mark.asyncio
    async def test_dotdot_segment_in_middle(self, static_client) -> None:
        """`/assets/..%2F..%2Fbearer.txt` también debe rechazarse.

        Cae en el mount de StaticFiles (que ya rechaza traversal con
        404), no en el spa_fallback. Lo crítico es que el contenido
        sensible no aparezca en la respuesta — el status puede ser 404."""
        r = await static_client.get("/assets/..%2F..%2Fbearer.txt")
        assert r.status_code in (200, 404)
        assert "super-secret-bearer-token" not in r.text

    @pytest.mark.asyncio
    async def test_absolute_path_falls_back_to_index(self, static_client) -> None:
        """Un cliente que mande `//etc/passwd` no debe leer del root del SO."""
        r = await static_client.get("//etc/passwd")
        # Aceptamos 200 (SPA fallback) o 404 — lo crítico es que no
        # devuelva el contenido del archivo del sistema.
        assert r.status_code in (200, 404)
        assert "root:" not in r.text  # /etc/passwd típico

    @pytest.mark.asyncio
    async def test_api_path_returns_404_not_index(self, static_client) -> None:
        """Mantener el contrato anterior: paths bajo /api/ no caen al SPA."""
        r = await static_client.get("/api/v1/nonexistent")
        # 404 (sin auth, no hay route registrada) — NO el SPA index.
        assert r.status_code in (401, 404)
        assert "scanner spa marker" not in r.text
