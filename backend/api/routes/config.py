"""Endpoints REST del Config del usuario (`/api/v1/config`).

**Modelo:** el `.config` es un archivo portable plaintext que el
usuario maneja como un documento (Cargar / Guardar / LAST). El
sistema persiste solo el path del último cargado en
`data/last_config_path.json`. Sin `.config` cargado, el scanner
arranca de cero (UserConfig vacío en runtime).

**Estado runtime:**

- `app.state.user_config: UserConfig | None`
- `app.state.user_config_path: Path | None`
- `app.state.last_config_path_file: Path` — track del LAST en disco.

**Endpoints:**

| Método | Path | Acción |
|---|---|---|
| POST | /config/load | Carga `.config` del path al runtime |
| POST | /config/save | Guarda runtime al path actual |
| POST | /config/save_as | Guarda runtime al path nuevo |
| POST | /config/clear | Wipe del runtime |
| GET | /config/last | Path del último `.config` cargado |
| GET | /config/current | UserConfig runtime (con secretos redactados por default) |
| PUT | /config/twelvedata_keys | Edita keys + reload del KeyPool |
| PUT | /config/s3 | Edita credenciales S3 |
| PUT | /config/startup_flags | Edita flags de arranque |
| POST | /config/reload-policies | Hot-reload de `db_size_limit_mb` |

**Auth:** Bearer token.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, ConfigDict, ValidationError

from api.auth import require_auth
from engines.data import ApiKeyConfig, KeyPool
from modules.config import (
    S3Config,
    StartupFlags,
    TDKeyConfig,
    UserConfig,
    load_config,
    save_config,
)

router = APIRouter(prefix="/config", tags=["config"])

_REDACTED = "***"


def _expand_path(raw: str) -> Path:
    """`Path(raw).expanduser()` ejecutado en un thread separado por
    `asyncio.to_thread` — `expanduser()` toca filesystem (resolución
    de `~`) y la regla `ASYNC240` lo prohíbe en el event loop."""
    return Path(raw).expanduser()


class LoadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str


class SaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str | None = None


class SaveAsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str


class TDKeysRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    twelvedata_keys: list[TDKeyConfig]


class S3Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    s3_config: S3Config | None


class StartupFlagsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    startup_flags: StartupFlags


def _redact_user_config(cfg: UserConfig) -> dict[str, Any]:
    """Devuelve el `UserConfig` como dict con los secretos enmascarados."""
    payload = cfg.model_dump(mode="json")
    if payload.get("twelvedata_keys"):
        for k in payload["twelvedata_keys"]:
            if k.get("secret"):
                k["secret"] = _REDACTED
    if (
        payload.get("s3_config")
        and payload["s3_config"].get("secret_access_key")
    ):
        payload["s3_config"]["secret_access_key"] = _REDACTED
    if payload.get("api_bearer_token"):
        payload["api_bearer_token"] = _REDACTED
    return payload


def _last_config_path_file(request: Request) -> Path:
    p = getattr(request.app.state, "last_config_path_file", None)
    if p is None:
        p = Path("data/last_config_path.json")
        request.app.state.last_config_path_file = p
    return p


def _write_last_config_path_sync(target: Path, path: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "path": str(path),
        "loaded_at": datetime.utcnow().isoformat() + "Z",
    }
    raw = json.dumps(payload, indent=2) + "\n"
    fd, tmp = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(raw)
        os.replace(tmp, target)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _read_last_config_path_sync(target: Path) -> dict | None:
    if not target.is_file():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _set_runtime(request: Request, cfg: UserConfig, path: Path | None) -> None:
    request.app.state.user_config = cfg
    request.app.state.user_config_path = path


def _get_runtime_or_empty(request: Request) -> UserConfig:
    cfg = getattr(request.app.state, "user_config", None)
    if cfg is None:
        return UserConfig()
    return cfg


async def _reload_key_pool(request: Request, cfg: UserConfig) -> bool:
    """Hot-reload (o bootstrap) del KeyPool con las TD keys del runtime.

    También reconstruye el `td_probe` del Validator si hay un client
    disponible — sin eso, `POST /validator/connectivity` sigue
    devolviendo `td_keys: []` aun después de cargar keys (BUG-001).

    Caso bootstrap: si `app.state.key_pool` es `None` (backend
    arrancó sin `SCANNER_TWELVEDATA_KEYS` env var), se crea un
    `KeyPool` + `TwelveDataClient` ahora con las keys del UserConfig
    y se exponen en `app.state`. Sin esto el Validator quedaría con
    `td_probe=None` para siempre y el botón "probar" del frontend
    quedaría silencioso.
    """
    if not cfg.twelvedata_keys:
        return False
    api_keys = [
        ApiKeyConfig(
            key_id=k.key_id,
            secret=k.secret,
            credits_per_minute=k.credits_per_minute,
            credits_per_day=k.credits_per_day,
            enabled=k.enabled,
        )
        for k in cfg.twelvedata_keys
    ]
    pool: KeyPool | None = getattr(request.app.state, "key_pool", None)
    if pool is None:
        # Bootstrap: el lifespan no creó scan_context al startup.
        # Construimos KeyPool + TwelveDataClient + DataEngine ahora
        # para que el Validator pueda probar las keys + el enable_slot
        # de Box 4 pueda disparar warmup sin restart (BUG-002 cierre).
        from engines.data.engine import DataEngine
        from engines.data.fetcher import TwelveDataClient

        pool = KeyPool(api_keys)
        client = TwelveDataClient(pool)
        request.app.state.key_pool = pool
        request.app.state.td_client = client
        request.app.state.data_engine = DataEngine(
            pool=pool,
            client=client,
            session_factory=request.app.state.session_factory,
        )
    else:
        await pool.reload(api_keys)
    _rebuild_validator_td_probe(request, api_keys)
    return True


def _rebuild_validator_td_probe(
    request: Request, api_keys: list[ApiKeyConfig],
) -> None:
    """Reasigna `validator.td_probe` con las keys actuales.

    Silencioso ante ausencia de validator/client en `app.state` — el
    backend puede arrancar sin scan_context (sin keys vía env var) y
    en ese caso el probe queda como estaba (None). Cuando el usuario
    cargue keys + reinicie, el lifespan reconstruye todo. La función
    se usa para keep-it-fresh en runtime cuando ya hay un client.
    """
    validator = getattr(request.app.state, "validator", None)
    td_client = getattr(request.app.state, "td_client", None)
    if validator is None or td_client is None:
        return
    from engines.data.probes import build_td_probe

    validator.set_td_probe(build_td_probe(api_keys, td_client))


# ────────────────────────────────────────────────────────────────────
# Endpoints
# ────────────────────────────────────────────────────────────────────


@router.post("/load")
async def config_load(
    req: LoadRequest,
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Carga un `.config` del disco al runtime."""
    path = await asyncio.to_thread(_expand_path, req.path)
    is_file = await asyncio.to_thread(path.is_file)
    if not is_file:
        raise HTTPException(404, f"file not found: {path}")
    try:
        cfg = await asyncio.to_thread(load_config, path)
    except ValidationError as e:
        raise HTTPException(400, {"error": "invalid schema", "detail": e.errors()}) from e
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"invalid JSON: {e}") from e

    _set_runtime(request, cfg, path)
    last_target = _last_config_path_file(request)
    try:
        await asyncio.to_thread(_write_last_config_path_sync, last_target, path)
    except OSError:
        logger.exception("could not persist last_config_path")

    pool_reloaded = await _reload_key_pool(request, cfg)
    return {
        "loaded": True,
        "path": str(path),
        "name": cfg.name,
        "key_pool_reloaded": pool_reloaded,
    }


@router.post("/save")
async def config_save(
    req: SaveRequest,
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Guarda el `UserConfig` runtime al path actual (o al de `req.path`).

    Si no hay path actual ni en el body → 400.
    """
    cfg = getattr(request.app.state, "user_config", None)
    if cfg is None:
        raise HTTPException(400, "no config loaded — load or set fields first")

    if req.path is not None:
        target_path = await asyncio.to_thread(_expand_path, req.path)
    else:
        current = getattr(request.app.state, "user_config_path", None)
        if current is None:
            raise HTTPException(
                400,
                "no current path — pass `path` in the body or use /save_as",
            )
        target_path = current

    try:
        await asyncio.to_thread(save_config, cfg, target_path)
    except OSError as e:
        raise HTTPException(500, f"could not write config: {e}") from e

    request.app.state.user_config_path = target_path
    last_target = _last_config_path_file(request)
    try:
        await asyncio.to_thread(
            _write_last_config_path_sync, last_target, target_path,
        )
    except OSError:
        logger.exception("could not persist last_config_path")

    return {"saved": True, "path": str(target_path)}


@router.post("/save_as")
async def config_save_as(
    req: SaveAsRequest,
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    cfg = getattr(request.app.state, "user_config", None)
    if cfg is None:
        raise HTTPException(400, "no config loaded — load or set fields first")
    path = await asyncio.to_thread(_expand_path, req.path)
    try:
        await asyncio.to_thread(save_config, cfg, path)
    except OSError as e:
        raise HTTPException(500, f"could not write config: {e}") from e
    request.app.state.user_config_path = path
    last_target = _last_config_path_file(request)
    try:
        await asyncio.to_thread(
            _write_last_config_path_sync, last_target, path,
        )
    except OSError:
        logger.exception("could not persist last_config_path")
    return {"saved": True, "path": str(path)}


@router.post("/clear")
async def config_clear(
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Wipe del runtime — vuelve al estado "sistema sin config cargado"."""
    request.app.state.user_config = None
    request.app.state.user_config_path = None
    return {"cleared": True}


@router.get("/last")
async def config_last(
    request: Request,
    _token: str = Depends(require_auth),
) -> dict | None:
    """Path del último `.config` cargado/guardado.

    Retorna `null` si nunca se cargó/guardó nada.
    """
    target = _last_config_path_file(request)
    return await asyncio.to_thread(_read_last_config_path_sync, target)


@router.get("/current")
async def config_current(
    request: Request,
    include_secrets: bool = False,
    _token: str = Depends(require_auth),
) -> dict:
    """Retorna el `UserConfig` runtime.

    Por default los secretos van enmascarados con `***`. Pasar
    `?include_secrets=true` retorna el config raw (uso interno del
    frontend al editar formularios).
    """
    cfg = getattr(request.app.state, "user_config", None)
    path = getattr(request.app.state, "user_config_path", None)
    if cfg is None:
        return {"loaded": False, "config": None, "path": None}
    body = (
        cfg.model_dump(mode="json")
        if include_secrets
        else _redact_user_config(cfg)
    )
    return {
        "loaded": True,
        "config": body,
        "path": str(path) if path else None,
    }


@router.put("/twelvedata_keys")
async def config_put_td_keys(
    req: TDKeysRequest,
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Edita las TD keys del runtime + reload del KeyPool.

    BUG-029: el endpoint `/config/current` enmascara los secrets con
    "***" para no exponerlos en la UI. Cuando el usuario agrega una
    key nueva (slot N+1), el frontend re-envía la lista completa,
    incluyendo entries previas con `secret="***"` (el valor masked
    que recibió). Antes el backend tomaba ese "***" literal y lo
    guardaba como secret real → la key vieja quedaba inválida (TD
    rechazaba con 401: "**apikey** parameter is incorrect").

    Fix: si el body trae `secret == "***"` para un `key_id` que ya
    existe en runtime, se preserva el secret original. El usuario
    puede sobrescribirlo enviando un secret distinto explícitamente.
    """
    current = _get_runtime_or_empty(request)

    # Mapa key_id → secret existente para preservar secretos masked
    existing_secrets = {
        k.key_id: k.secret for k in current.twelvedata_keys
    }

    merged_keys: list[TDKeyConfig] = []
    preserved_count = 0
    for incoming in req.twelvedata_keys:
        # `_REDACTED` es el placeholder que `_redact_user_config` emite
        # en GET /config/current. Si llega de vuelta significa que el
        # frontend está re-enviándonos el masked sin haberlo cambiado.
        if incoming.secret == _REDACTED and incoming.key_id in existing_secrets:
            preserved = incoming.model_copy(
                update={"secret": existing_secrets[incoming.key_id]},
            )
            merged_keys.append(preserved)
            preserved_count += 1
        else:
            merged_keys.append(incoming)

    new_cfg = current.model_copy(update={"twelvedata_keys": merged_keys})
    _set_runtime(
        request, new_cfg, getattr(request.app.state, "user_config_path", None),
    )
    pool_reloaded = await _reload_key_pool(request, new_cfg)
    return {
        "updated": True,
        "count": len(new_cfg.twelvedata_keys),
        "key_pool_reloaded": pool_reloaded,
        "preserved_redacted": preserved_count,
    }


@router.put("/s3")
async def config_put_s3(
    req: S3Request,
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Edita las credenciales S3 del runtime."""
    current = _get_runtime_or_empty(request)
    new_cfg = current.model_copy(update={"s3_config": req.s3_config})
    _set_runtime(
        request, new_cfg, getattr(request.app.state, "user_config_path", None),
    )
    return {"updated": True, "configured": new_cfg.s3_config is not None}


@router.put("/startup_flags")
async def config_put_startup_flags(
    req: StartupFlagsRequest,
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Edita los flags de arranque del runtime.

    Los cambios se aplican al próximo arranque del backend (algunos
    valores requieren reinicio porque el lifecycle ya cableó workers
    con la config previa). El frontend muestra el aviso correspondiente.

    Excepción: `db_size_limit_mb` se sincroniza con
    `app.state.db_size_limit_mb` para que el endpoint
    `/database/rotate/aggressive` lo lea en caliente.
    """
    current = _get_runtime_or_empty(request)
    new_cfg = current.model_copy(update={"startup_flags": req.startup_flags})
    _set_runtime(
        request, new_cfg, getattr(request.app.state, "user_config_path", None),
    )
    request.app.state.db_size_limit_mb = req.startup_flags.db_size_limit_mb
    return {
        "updated": True,
        "applied_immediately": ["db_size_limit_mb"],
        "requires_restart": [
            "validator_run_at_startup",
            "validator_parity_enabled",
            "validator_parity_limit",
            "heartbeat_interval_s",
            "rotate_on_shutdown",
            "aggressive_rotation_enabled",
            "aggressive_rotation_interval_s",
        ],
    }


@router.post("/reload-policies")
async def config_reload_policies(
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Hot-reload de las policies que se pueden aplicar sin reiniciar.

    Hoy: solo `db_size_limit_mb`. Cambios al
    `aggressive_rotation_interval_s` o al toggle del watchdog
    requieren restart porque el task ya está iniciado.
    """
    cfg = getattr(request.app.state, "user_config", None)
    if cfg is None:
        return {"applied": [], "reason": "no config loaded"}
    request.app.state.db_size_limit_mb = cfg.startup_flags.db_size_limit_mb
    return {
        "applied": ["db_size_limit_mb"],
        "current_db_size_limit_mb": cfg.startup_flags.db_size_limit_mb,
    }
