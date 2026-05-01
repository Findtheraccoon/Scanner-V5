"""Tests del bootstrap del registry runtime (BUG-002).

El registry runtime se construye fuera del bloque `if use_real_scan_loop`
para que los endpoints `/slots` y `/fixtures` funcionen aún cuando el
backend arranca sin `SCANNER_TWELVEDATA_KEYS` (flujo "metelas por UI").

Tests cubren:
- `_ensure_registry_file` crea un slot_registry.json default si falta.
- `_ensure_registry_file` es no-op si el archivo ya existe.
- `_bootstrap_registry_runtime` deja un `RegistryRuntime` en
  `app.state.registry_runtime` con 6 slots disabled.
- Idempotente: dos llamadas seguidas no crashean ni re-escriben.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Para que `import main` funcione cuando pytest corre desde backend/.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def test_ensure_registry_file_creates_default(tmp_path: Path) -> None:
    from main import _ensure_registry_file

    path = tmp_path / "slot_registry.json"
    assert not path.exists()
    _ensure_registry_file(path)
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    # Estructura mínima válida.
    assert payload["registry_metadata"]["registry_version"] == "1.0.0"
    assert "engine_version_required" in payload["registry_metadata"]
    assert "generated_at" in payload["registry_metadata"]
    # 6 slots disabled.
    assert len(payload["slots"]) == 6
    assert {s["slot"] for s in payload["slots"]} == {1, 2, 3, 4, 5, 6}
    assert all(s["enabled"] is False for s in payload["slots"])
    assert all(s["ticker"] is None for s in payload["slots"])
    assert all(s["fixture"] is None for s in payload["slots"])


def test_ensure_registry_file_noop_if_exists(tmp_path: Path) -> None:
    from main import _ensure_registry_file

    path = tmp_path / "slot_registry.json"
    original = '{"keep_me": "as-is"}'
    path.write_text(original, encoding="utf-8")
    _ensure_registry_file(path)
    # No debe sobreescribir el archivo del usuario.
    assert path.read_text(encoding="utf-8") == original


def test_ensure_registry_file_creates_parent_dir(tmp_path: Path) -> None:
    from main import _ensure_registry_file

    path = tmp_path / "nested" / "subdir" / "slot_registry.json"
    assert not path.parent.exists()
    _ensure_registry_file(path)
    assert path.is_file()


@pytest.fixture
def fake_app() -> SimpleNamespace:
    """SimpleNamespace que simula `app.state` para los helpers."""
    return SimpleNamespace(state=SimpleNamespace())


def test_bootstrap_registry_runtime_attaches_to_app_state(
    tmp_path: Path, fake_app: SimpleNamespace,
) -> None:
    from main import _bootstrap_registry_runtime
    from settings import Settings

    registry_path = tmp_path / "slot_registry.json"
    settings = Settings(registry_path=str(registry_path))

    _bootstrap_registry_runtime(fake_app, settings)

    assert hasattr(fake_app.state, "registry_runtime")
    runtime = fake_app.state.registry_runtime
    assert runtime is not None
    # 6 slots, todos disabled tras bootstrap.
    assert len(runtime._registry.slots) == 6
    statuses = [s.status for s in runtime._registry.slots]
    assert all(st == "DISABLED" for st in statuses), statuses


def test_bootstrap_registry_runtime_idempotent(
    tmp_path: Path, fake_app: SimpleNamespace,
) -> None:
    """Segunda llamada con archivo ya existente — no rompe ni reescribe."""
    from main import _bootstrap_registry_runtime
    from settings import Settings

    registry_path = tmp_path / "slot_registry.json"
    settings = Settings(registry_path=str(registry_path))

    _bootstrap_registry_runtime(fake_app, settings)
    first_mtime = registry_path.stat().st_mtime

    _bootstrap_registry_runtime(fake_app, settings)
    second_mtime = registry_path.stat().st_mtime

    # Archivo no fue tocado en la segunda corrida.
    assert first_mtime == second_mtime


def test_bootstrap_registry_runtime_falls_back_on_invalid_file(
    tmp_path: Path, fake_app: SimpleNamespace,
) -> None:
    """BUG-007: ante archivo corrupto, en lugar de dejar registry_runtime
    en None y retornar 503 en /slots, se construye un fallback in-memory
    con 6 slots DISABLED. El error se persiste en `registry_load_error`
    para que /engine/health lo exponga.
    """
    from main import _bootstrap_registry_runtime
    from settings import Settings

    registry_path = tmp_path / "slot_registry.json"
    registry_path.write_text("not json at all", encoding="utf-8")
    settings = Settings(registry_path=str(registry_path))

    _bootstrap_registry_runtime(fake_app, settings)

    # registry_runtime existe (fallback), 6 slots DISABLED.
    runtime = getattr(fake_app.state, "registry_runtime", None)
    assert runtime is not None, (
        "BUG-007: el fallback in-memory debe poblar registry_runtime"
    )
    assert len(runtime._registry.slots) == 6
    assert all(s.status == "DISABLED" for s in runtime._registry.slots)
    # registry_load_error captura el código + detalle para la UI.
    err = getattr(fake_app.state, "registry_load_error", None)
    assert err is not None and "REG-" in err, err
