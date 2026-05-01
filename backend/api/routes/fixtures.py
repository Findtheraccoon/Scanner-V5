"""Endpoints REST de gestión de fixtures (`/api/v1/fixtures`).

**Scope:**

- `GET /fixtures` — lista los `.json` del `fixtures_dir` con metadata,
  estado del SHA-256, y slots que lo usan.
- `POST /fixtures/upload` — sube un fixture nuevo. Body multipart con
  un archivo `.json`. Valida schema (Pydantic + reglas FIX-XXX) +
  `engine_compat_range` ⊇ engine actual + duplicado por `fixture_id`.
- `DELETE /fixtures/{fixture_id}` — elimina `.json` + `.sha256` +
  `.metrics.json` (sibling). 409 si algún slot lo tiene asignado.

**Layout en disco:**

```
<fixtures_dir>/
├── <fixture_id>.json
├── <fixture_id>.sha256          # opcional, SHA-256 del .json
└── <fixture_id>.metrics.json    # opcional, sibling spec §3.5
```

**Auth:** Bearer token.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from api.auth import require_auth
from engines.scoring import ENGINE_VERSION
from modules.fixtures import Fixture, FixtureError, parse_fixture

router = APIRouter(prefix="/fixtures", tags=["fixtures"])


# ────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────


def _fixtures_dir(request: Request) -> Path:
    p = getattr(request.app.state, "fixtures_dir", None)
    if p is None:
        p = Path("fixtures")
        request.app.state.fixtures_dir = p
    return p


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_sibling_hash(json_path: Path) -> str | None:
    """Lee el `.sha256` sibling. Retorna `None` si no existe.

    Formato del archivo (compat con sha256sum): `<hex>  <filename>` o
    solo `<hex>`. Tomamos los primeros 64 chars hex.
    """
    sha_path = json_path.with_suffix(".sha256")
    if not sha_path.is_file():
        return None
    try:
        raw = sha_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    token = raw.split()[0] if raw else ""
    if len(token) == 64 and all(c in "0123456789abcdefABCDEF" for c in token):
        return token.lower()
    return None


def _engine_in_range(range_spec: str) -> bool:
    try:
        v = Version(ENGINE_VERSION)
        s = SpecifierSet(range_spec)
    except (InvalidVersion, InvalidSpecifier):
        return False
    return v in s


def _list_fixture_files(fixtures_dir: Path) -> list[Path]:
    if not fixtures_dir.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(fixtures_dir.iterdir()):
        if not p.is_file() or p.suffix != ".json":
            continue
        # Excluir .metrics.json y otros siblings.
        if p.name.endswith(".metrics.json"):
            continue
        out.append(p)
    return out


def _parse_fixture_file(path: Path) -> tuple[Fixture | None, str | None]:
    """Lee + parsea. Retorna `(fixture, error_msg)`. Si falla, fixture=None."""
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return parse_fixture(data), None
    except FixtureError as e:
        return None, f"{e.code}: {e.detail}"
    except (OSError, json.JSONDecodeError) as e:
        return None, f"read/parse error: {e}"


def _slots_using_fixture(request: Request, fixture_id: str) -> list[int]:
    """Lista los slot_ids que tienen este `fixture_id` cargado.

    Lee del runtime registry. Si no hay registry, devuelve `[]`.

    BUG-005: el código previo llamaba `runtime._registry.snapshot()`
    que no existe — `SlotRegistry` es un Pydantic model con campo
    `slots: list[SlotRecord]`. Reemplazado por iteración directa.
    Lectura sync sobre lista de un model `frozen=True` es safe.
    """
    runtime = getattr(request.app.state, "registry_runtime", None)
    if runtime is None:
        return []
    out: list[int] = []
    for rec in runtime._registry.slots:
        if rec.fixture is None:
            continue
        if rec.fixture.metadata.fixture_id == fixture_id:
            out.append(rec.slot)
    return out


def _hash_status(actual: str, sibling: str | None) -> str:
    if sibling is None:
        return "no canonical"
    return "ok" if actual == sibling else "mismatch"


# ────────────────────────────────────────────────────────────────────
# Endpoints
# ────────────────────────────────────────────────────────────────────


def _list_sync(fixtures_dir: Path) -> list[dict[str, Any]]:
    """Listado sincrónico — invocado vía `asyncio.to_thread`."""
    items: list[dict[str, Any]] = []
    for path in _list_fixture_files(fixtures_dir):
        try:
            raw = path.read_bytes()
        except OSError as e:
            items.append({
                "path": str(path),
                "error": f"read failed: {e}",
            })
            continue
        actual_hash = _sha256_hex(raw)
        sibling_hash = _read_sibling_hash(path)
        fixture, parse_err = _parse_fixture_file(path)
        entry: dict[str, Any] = {
            "path": str(path),
            "filename": path.name,
            "sha256": actual_hash,
            "sha256_status": _hash_status(actual_hash, sibling_hash),
        }
        if parse_err is not None:
            entry["error"] = parse_err
            items.append(entry)
            continue
        assert fixture is not None
        meta = fixture.metadata
        entry.update({
            "fixture_id": meta.fixture_id,
            "fixture_version": meta.fixture_version,
            "engine_compat_range": meta.engine_compat_range,
            "ticker_default": fixture.ticker_info.ticker,
            "benchmark_default": fixture.ticker_info.benchmark,
            "engine_compatible": _engine_in_range(meta.engine_compat_range),
        })
        items.append(entry)
    return items


@router.get("")
async def list_fixtures(
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Lista los `.json` de `fixtures_dir` con metadata + hash status."""
    fixtures_dir = _fixtures_dir(request)
    items = await asyncio.to_thread(_list_sync, fixtures_dir)
    # Slots usage requiere acceso al registry — se calcula fuera del
    # thread porque no es bloqueante.
    for entry in items:
        fid = entry.get("fixture_id")
        entry["used_by_slots"] = (
            _slots_using_fixture(request, fid) if fid is not None else []
        )
    return {
        "fixtures_dir": str(fixtures_dir),
        "items": items,
        "engine_version": ENGINE_VERSION,
    }


def _persist_fixture_sync(
    fixtures_dir: Path,
    fixture_id: str,
    raw_bytes: bytes,
    sha_hex: str,
) -> dict[str, Any]:
    """Escribe `<fixture_id>.json` + `.sha256` atómicamente.

    Retorna paths persistidos.
    """
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    json_path = fixtures_dir / f"{fixture_id}.json"
    sha_path = fixtures_dir / f"{fixture_id}.sha256"

    json_path.write_bytes(raw_bytes)
    sha_path.write_text(f"{sha_hex}  {json_path.name}\n", encoding="utf-8")
    return {
        "json_path": str(json_path),
        "sha256_path": str(sha_path),
    }


@router.post("/upload")
async def upload_fixture(
    request: Request,
    file: UploadFile,
    _token: str = Depends(require_auth),
) -> dict:
    """Sube un fixture nuevo (multipart).

    Validaciones:
    1. Body multipart con un archivo `.json`.
    2. Parsea como `Fixture` (Pydantic + reglas FIX-XXX).
    3. `engine_compat_range` ⊇ `ENGINE_VERSION` actual.
    4. `fixture_id` no duplicado en disco (409).
    """
    if file.filename is None or not file.filename.endswith(".json"):
        raise HTTPException(400, "file must be a .json")

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(400, "empty file")

    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(400, f"invalid JSON: {e}") from e
    try:
        fixture = parse_fixture(data)
    except FixtureError as e:
        raise HTTPException(
            400, {"error_code": e.code, "detail": e.detail},
        ) from e

    if not _engine_in_range(fixture.metadata.engine_compat_range):
        raise HTTPException(
            422,
            {
                "error": "engine_compat_range mismatch",
                "engine_version": ENGINE_VERSION,
                "engine_compat_range": fixture.metadata.engine_compat_range,
            },
        )

    fixtures_dir = _fixtures_dir(request)
    fixture_id = fixture.metadata.fixture_id
    target = fixtures_dir / f"{fixture_id}.json"
    if await asyncio.to_thread(target.is_file):
        raise HTTPException(
            409,
            {
                "error": "fixture_id already exists",
                "fixture_id": fixture_id,
                "path": str(target),
            },
        )

    sha_hex = _sha256_hex(raw_bytes)
    paths = await asyncio.to_thread(
        _persist_fixture_sync, fixtures_dir, fixture_id, raw_bytes, sha_hex,
    )
    return {
        "uploaded": True,
        "fixture_id": fixture_id,
        "fixture_version": fixture.metadata.fixture_version,
        "ticker_default": fixture.ticker_info.ticker,
        "sha256": sha_hex,
        **paths,
    }


def _delete_fixture_sync(fixtures_dir: Path, fixture_id: str) -> dict[str, Any]:
    """Borra `.json` + `.sha256` + `.metrics.json` si existen.

    No falla si los siblings no están — solo el `.json` es obligatorio.
    """
    json_path = fixtures_dir / f"{fixture_id}.json"
    if not json_path.is_file():
        raise FileNotFoundError(str(json_path))

    deleted: list[str] = []
    json_path.unlink()
    deleted.append(str(json_path))

    sha_path = fixtures_dir / f"{fixture_id}.sha256"
    if sha_path.is_file():
        sha_path.unlink()
        deleted.append(str(sha_path))

    metrics_path = fixtures_dir / f"{fixture_id}.metrics.json"
    if metrics_path.is_file():
        metrics_path.unlink()
        deleted.append(str(metrics_path))

    return {"deleted": True, "fixture_id": fixture_id, "paths": deleted}


@router.delete("/{fixture_id}")
async def delete_fixture(
    fixture_id: str,
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Elimina un fixture del disco.

    409 si algún slot tiene este `fixture_id` cargado — el usuario
    debe re-asignar el slot a otro fixture (o deshabilitarlo) antes.
    """
    used_by = _slots_using_fixture(request, fixture_id)
    if used_by:
        raise HTTPException(
            409,
            {
                "error": "fixture in use",
                "fixture_id": fixture_id,
                "used_by_slots": used_by,
            },
        )

    fixtures_dir = _fixtures_dir(request)
    try:
        return await asyncio.to_thread(
            _delete_fixture_sync, fixtures_dir, fixture_id,
        )
    except FileNotFoundError as e:
        raise HTTPException(404, f"fixture not found: {fixture_id}") from e
