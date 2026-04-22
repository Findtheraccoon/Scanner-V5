"""Endpoints REST de slots del registry (`/api/v1/slots`).

**Scope:**

- `GET /api/v1/slots` — lista los 6 slots con status runtime
  (`active`, `warming_up`, `degraded`, `disabled`) + metadata.
- `GET /api/v1/slots/{slot_id}` — detalle de un slot.
- `PATCH /api/v1/slots/{slot_id}` — edita el slot:
  - `{enabled: false}` → deshabilita. Broadcast `slot.status=disabled`.
  - `{enabled: true, ticker, fixture, benchmark?}` → habilita (o
    re-asigna) con ticker/fixture nuevos. Flujo hot-reload:
      1. Valida fixture en disco + coherencia con lo pedido.
      2. Muta registry + persiste `slot_registry.json`.
      3. Marca slot `warming_up` + broadcast `slot.status=warming_up`.
      4. Spawn background task: `DataEngine.warmup([ticker])` →
         `mark_warmed` + broadcast `slot.status=active`.

**Auth:** Bearer token.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, ConfigDict

from api.auth import require_auth
from api.events import EVENT_SLOT_STATUS
from engines.registry_runtime import RegistryRuntime
from engines.scoring import ENGINE_VERSION
from modules.fixtures import FixtureError
from modules.slot_registry import RegistryError
from modules.validator import Validator

router = APIRouter(prefix="/slots", tags=["slots"])


class SlotPatchRequest(BaseModel):
    """Payload del PATCH.

    - `enabled=False`: deshabilita (campos adicionales ignorados).
    - `enabled=True`: requiere `ticker` y `fixture`; `benchmark`
      opcional (si la fixture declara benchmark, debe coincidir).
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    ticker: str | None = None
    fixture: str | None = None
    benchmark: str | None = None


def _get_runtime(request: Request) -> RegistryRuntime:
    runtime = getattr(request.app.state, "registry_runtime", None)
    if runtime is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Registry not initialized. The scan loop requires a "
                "slot_registry.json configured via SCANNER_REGISTRY_PATH."
            ),
        )
    return runtime


def _get_data_engine(request: Request):
    de = getattr(request.app.state, "data_engine", None)
    if de is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Data Engine not initialized. Enabling a slot requires a "
                "live Data Engine to perform the warmup."
            ),
        )
    return de


def _get_fixtures_root(request: Request) -> Path:
    runtime: RegistryRuntime = request.app.state.registry_runtime
    # La convención actual (igual que load_registry) es que el
    # directorio del `slot_registry.json` es la raíz de paths relativos.
    path = runtime._registry_path
    if path is None:
        raise HTTPException(
            status_code=503,
            detail="Registry runtime sin registry_path — enable requiere paths resolvibles.",
        )
    return path.parent


@router.get("")
async def list_slots(
    request: Request,
    _token: str = Depends(require_auth),
) -> list[dict]:
    """Lista los 6 slots con status runtime + metadata."""
    runtime = _get_runtime(request)
    return await runtime.list_slots()


@router.get("/{slot_id}")
async def get_slot(
    slot_id: int,
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    runtime = _get_runtime(request)
    slot = await runtime.get_slot(slot_id)
    if slot is None:
        raise HTTPException(404, f"Slot {slot_id} not found")
    return slot


@router.patch("/{slot_id}")
async def patch_slot(
    slot_id: int,
    req: SlotPatchRequest,
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Modifica un slot. Ver docstring del módulo para los 2 flujos."""
    runtime = _get_runtime(request)
    slot = await runtime.get_slot(slot_id)
    if slot is None:
        raise HTTPException(404, f"Slot {slot_id} not found")

    broadcaster = request.app.state.broadcaster

    if req.enabled is False:
        changed = await runtime.disable_slot(slot_id)
        if not changed:
            raise HTTPException(500, "disable_slot returned False")
        await broadcaster.broadcast(
            EVENT_SLOT_STATUS,
            {
                "slot_id": slot_id,
                "status": "disabled",
                "message": "disabled by user",
            },
        )
        _spawn_revalidation(request)
        return await runtime.get_slot(slot_id)

    if req.enabled is True:
        if not req.ticker or not req.fixture:
            raise HTTPException(
                status_code=400,
                detail="enable requires `ticker` and `fixture` in body",
            )
        data_engine = _get_data_engine(request)
        fixtures_root = _get_fixtures_root(request)

        try:
            await runtime.enable_slot(
                slot_id,
                ticker=req.ticker,
                fixture_path=req.fixture,
                benchmark=req.benchmark,
                fixtures_root=fixtures_root,
                engine_version=ENGINE_VERSION,
            )
        except FixtureError as e:
            raise HTTPException(
                status_code=400,
                detail={"error_code": e.code, "detail": e.detail},
            ) from e
        except RegistryError as e:
            raise HTTPException(
                status_code=400,
                detail={"error_code": e.code, "detail": e.detail},
            ) from e

        await broadcaster.broadcast(
            EVENT_SLOT_STATUS,
            {
                "slot_id": slot_id,
                "status": "warming_up",
                "ticker": req.ticker,
            },
        )

        # Background task: warmup → mark_warmed + broadcast active.
        # Guardamos la ref en app.state para que no la recoja el GC
        # antes de terminar (RUF006).
        task = asyncio.create_task(
            _run_warmup_and_activate(
                runtime=runtime,
                data_engine=data_engine,
                broadcaster=broadcaster,
                slot_id=slot_id,
                ticker=req.ticker,
            ),
            name=f"warmup_slot_{slot_id}",
        )
        warmup_tasks = getattr(request.app.state, "warmup_tasks", None)
        if warmup_tasks is None:
            warmup_tasks = set()
            request.app.state.warmup_tasks = warmup_tasks
        warmup_tasks.add(task)
        task.add_done_callback(warmup_tasks.discard)

        _spawn_revalidation(request)
        return await runtime.get_slot(slot_id)

    raise HTTPException(
        status_code=400,
        detail="PATCH requires `enabled` true or false",
    )


def _spawn_revalidation(request: Request) -> None:
    """Dispara `Validator.run_slot_revalidation()` en background.

    Silencioso: si no hay validator configurado en app.state, no-op
    (evita romper tests que no montan Validator).
    """
    validator: Validator | None = getattr(
        request.app.state, "validator", None,
    )
    if validator is None:
        return

    async def _run() -> None:
        try:
            report = await validator.run_slot_revalidation()
            request.app.state.last_validator_report = report
        except Exception:
            logger.exception("slot revalidation background task failed")

    task = asyncio.create_task(_run(), name="slot_revalidation")
    tasks = getattr(request.app.state, "revalidation_tasks", None)
    if tasks is None:
        tasks = set()
        request.app.state.revalidation_tasks = tasks
    tasks.add(task)
    task.add_done_callback(tasks.discard)


async def _run_warmup_and_activate(
    *,
    runtime: RegistryRuntime,
    data_engine,
    broadcaster,
    slot_id: int,
    ticker: str,
) -> None:
    """Warmup async post-enable. Si falla, libera el overlay igual y
    emite slot.status=degraded con código ENG-060 (mismo código que
    el retry policy del scan loop)."""
    try:
        await data_engine.warmup([ticker])
    except Exception:
        logger.exception(
            f"warmup failed for slot {slot_id} ticker={ticker} — "
            "marcando slot como degraded",
        )
        await runtime.mark_warmed(slot_id)
        await broadcaster.broadcast(
            EVENT_SLOT_STATUS,
            {
                "slot_id": slot_id,
                "status": "degraded",
                "ticker": ticker,
                "error_code": "ENG-060",
                "message": "warmup failed after enable",
            },
        )
        return

    await runtime.mark_warmed(slot_id)
    await broadcaster.broadcast(
        EVENT_SLOT_STATUS,
        {
            "slot_id": slot_id,
            "status": "active",
            "ticker": ticker,
            "message": "warmup complete",
        },
    )
