"""Check C — Validación del Slot Registry.

Re-carga el archivo `slot_registry.json` con `load_registry()` y
reporta los códigos REG-XXX detectados.

**Severidad:**

- Registry carga sin errores y con 0 slots DEGRADED → `pass`.
- Registry carga pero hay slots DEGRADED → `fail / degraded` (otros
  slots siguen operables).
- `RegistryError` fatal (REG-001/002/003/004/020/030) → `fail / fatal`.

Este check verifica la **consistencia del archivo en disco** — útil
tras hot-reload o edición manual. Complementa al Check A (fixtures)
reportando errores a nivel de la topología del registry.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from engines.scoring import ENGINE_VERSION
from modules.slot_registry import RegistryError, load_registry
from modules.validator.models import TestResult


async def run(
    *,
    registry_path: Path | None,
    engine_version: str = ENGINE_VERSION,
    fixtures_root: Path | None = None,
) -> TestResult:
    start = time.perf_counter()

    if registry_path is None:
        return TestResult(
            test_id="C",
            status="skip",
            message="registry_path no provisto",
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )

    try:
        registry = load_registry(
            registry_path,
            engine_version=engine_version,
            fixtures_root=fixtures_root,
        )
    except RegistryError as e:
        duration_ms = (time.perf_counter() - start) * 1000.0
        return TestResult(
            test_id="C",
            status="fail",
            severity="fatal",
            error_code=e.code,
            message=e.detail,
            duration_ms=duration_ms,
        )

    degraded: list[dict[str, Any]] = [
        {
            "slot": s.slot,
            "error_code": s.error_code,
            "detail": s.error_detail,
        }
        for s in registry.degraded_slots
    ]

    details: dict[str, Any] = {
        "operative_count": len(registry.operative_slots),
        "degraded_count": len(degraded),
        "disabled_count": len(registry.disabled_slots),
        "warnings": list(registry.warnings),
    }
    if degraded:
        details["degraded_slots"] = degraded

    duration_ms = (time.perf_counter() - start) * 1000.0

    if not degraded:
        return TestResult(
            test_id="C",
            status="pass",
            details=details,
            duration_ms=duration_ms,
        )

    return TestResult(
        test_id="C",
        status="fail",
        severity="degraded",
        error_code=degraded[0]["error_code"],
        message=f"{len(degraded)} slot(s) en DEGRADED",
        details=details,
        duration_ms=duration_ms,
    )
