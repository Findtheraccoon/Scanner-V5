"""Endpoints REST de slots del registry (`/api/v1/slots`).

**Scope SR.3:**

- `GET /api/v1/slots` — lista los 6 slots con status runtime
  (`active`, `warming_up`, `degraded`, `disabled`) + metadata.
- `GET /api/v1/slots/{slot_id}` — detalle de un slot.
- `PATCH /api/v1/slots/{slot_id}` — cambios MVP:
  - `{enabled: false}` → deshabilita el slot. Broadcast
    `slot.status=disabled`.
  - Otros payloads (enable con ticker nuevo, cambiar fixture) quedan
    para fase siguiente (requiere reload de fixture desde disco y
    warmup explícito).

**Auth:** Bearer token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from api.auth import require_auth
from api.events import EVENT_SLOT_STATUS

router = APIRouter(prefix="/slots", tags=["slots"])


class SlotPatchRequest(BaseModel):
    """Payload del PATCH. MVP: solo `enabled=False` soportado."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None


def _get_runtime(request: Request):
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
    """Modifica un slot. MVP: solo `enabled=False` (disable).

    - Cambios en memoria (no toca `slot_registry.json` en disco).
    - Broadcast `slot.status` con el estado nuevo.
    - Devuelve el slot actualizado.
    """
    runtime = _get_runtime(request)
    slot = await runtime.get_slot(slot_id)
    if slot is None:
        raise HTTPException(404, f"Slot {slot_id} not found")

    if req.enabled is False:
        changed = await runtime.disable_slot(slot_id)
        if not changed:
            # No debería pasar porque ya validamos con get_slot
            raise HTTPException(500, "disable_slot returned False")
        broadcaster = request.app.state.broadcaster
        await broadcaster.broadcast(
            EVENT_SLOT_STATUS,
            {
                "slot_id": slot_id,
                "status": "disabled",
                "message": "disabled by user",
            },
        )
        return await runtime.get_slot(slot_id)

    # MVP: enable + cambio de ticker/fixture no soportado todavía.
    raise HTTPException(
        status_code=400,
        detail=(
            "MVP: only `{\"enabled\": false}` is supported. "
            "Enable + ticker/fixture swap require file-based reload "
            "(out of scope for SR.3)."
        ),
    )
