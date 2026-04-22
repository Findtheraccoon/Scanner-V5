"""Writer del `slot_registry.json` — contraparte de `loader.py`.

Serializa un `SlotRegistry` ya evaluado de vuelta al schema que el
loader entiende, aplicando escritura atómica (tempfile + `os.replace`)
para que un crash a mitad de escritura no deje el archivo corrupto.

**Mapeo `SlotRecord` → JSON:**

    - `enabled`: `rec.status != "DISABLED"` — `OPERATIVE` y `DEGRADED`
      quedan enabled. El degrade es transitorio (runtime), no una
      decisión del trader que deba persistirse.
    - Campos preservados tal cual: `slot`, `ticker`, `fixture`
      (derivado de `fixture_path`), `benchmark`, `priority`, `notes`.
    - Campos derivados/runtime no se escriben: `status`, `error_code`,
      `error_detail`, `fixture` parseado. El loader los reconstruye al
      re-cargar.

**No persiste `warnings`** — son runtime-only.

**Uso típico:** `RegistryRuntime.disable_slot()` lo invoca después de
mutar memoria, con rollback si la escritura falla.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from modules.slot_registry.models import SlotRecord, SlotRegistry


def save_registry(registry: SlotRegistry, path: str | Path) -> None:
    """Escribe `registry` a `path` de forma atómica.

    Args:
        registry: el `SlotRegistry` a serializar.
        path: path destino del archivo JSON.

    Raises:
        OSError: si la escritura al disco falla (sin dejar archivo
            parcial en `path`).
    """
    target = Path(path)
    payload = _serialize_registry(registry)
    raw = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    # Atomic write: tempfile en el mismo dir + os.replace.
    # `os.replace` es atómico dentro del mismo filesystem en POSIX y
    # Windows (Python ≥3.3).
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(raw)
        os.replace(tmp_path, target)
    except Exception:
        # Limpiar tempfile si el replace falló o la escritura murió.
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def _serialize_registry(registry: SlotRegistry) -> dict[str, Any]:
    return {
        "registry_metadata": registry.metadata.model_dump(
            mode="json", exclude_none=True,
        ),
        "slots": [_serialize_slot(s) for s in registry.slots],
    }


def _serialize_slot(rec: SlotRecord) -> dict[str, Any]:
    return {
        "slot": rec.slot,
        "enabled": rec.status != "DISABLED",
        "ticker": rec.ticker,
        "fixture": rec.fixture_path,
        "benchmark": rec.benchmark,
        "priority": rec.priority,
        "notes": rec.notes,
    }
