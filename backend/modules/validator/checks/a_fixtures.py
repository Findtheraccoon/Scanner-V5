"""Check A — Validación de fixtures.

Recorre cada slot del `RegistryRuntime` (excluye `disabled`) y corre
`load_fixture()` fresh sobre el path declarado. Captura `FixtureError`
con su `FIX-XXX` y arma un reporte por-slot.

**Severidad:**

- Todas las fixtures cargan → `pass`.
- Al menos una falla → `fail / degraded` (otros slots siguen operables).

El error código FIX-XXX específico del primer fallo se reporta en
`error_code` del `TestResult`; el detalle por-slot vive en
`details["fixtures"]`.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from modules.fixtures import FixtureError, load_fixture
from modules.validator.models import TestResult

if TYPE_CHECKING:
    from engines.registry_runtime import RegistryRuntime


async def run(
    *,
    registry: RegistryRuntime | None,
    fixtures_root: Path | None,
) -> TestResult:
    """Valida cada fixture referenciada por slots no-disabled.

    Si `registry` o `fixtures_root` son `None`, retorna `skip` con el
    motivo — el caller (arranque del backend sin scan loop) puede no
    tener la info.
    """
    start = time.perf_counter()

    if registry is None or fixtures_root is None:
        return TestResult(
            test_id="A",
            status="skip",
            message="registry o fixtures_root no provistos",
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )

    slots = await registry.list_slots()
    results: list[dict[str, Any]] = []
    first_error_code: str | None = None
    failures = 0

    for slot in slots:
        if slot["status"] == "disabled" or not slot.get("fixture_path"):
            continue
        fixture_path = fixtures_root / slot["fixture_path"]
        try:
            load_fixture(fixture_path)
            results.append(
                {"slot": slot["slot"], "fixture_path": slot["fixture_path"], "status": "ok"},
            )
        except FixtureError as e:
            failures += 1
            if first_error_code is None:
                first_error_code = e.code
            results.append(
                {
                    "slot": slot["slot"],
                    "fixture_path": slot["fixture_path"],
                    "status": "fail",
                    "error_code": e.code,
                    "detail": e.detail,
                },
            )

    duration_ms = (time.perf_counter() - start) * 1000.0

    if failures == 0:
        return TestResult(
            test_id="A",
            status="pass",
            details={"fixtures": results},
            duration_ms=duration_ms,
        )

    return TestResult(
        test_id="A",
        status="fail",
        severity="degraded",
        error_code=first_error_code,
        message=f"{failures} fixture(s) fallaron validación",
        details={"fixtures": results},
        duration_ms=duration_ms,
    )
