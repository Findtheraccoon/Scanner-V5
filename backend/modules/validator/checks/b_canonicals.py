"""Check B — Validación de canonicals (hash SHA-256).

Para cada slot enabled con fixture válida que declara un
`canonical_ref`, recomputa el SHA-256 del `.json` del canonical y lo
compara con el `.sha256` en disco.

**Severidad:**

- Todos los hashes coinciden → `pass`.
- Al menos uno diverge o falta → `fail / fatal` (integridad crítica,
  spec §8 del registry: REG-020 es fatal).

Re-usa la lógica de `modules.slot_registry.loader` para mantener una
sola fuente de verdad de cómo se validan hashes, evitando divergencias.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from modules.fixtures import FixtureError, load_fixture
from modules.slot_registry import REG_020
from modules.validator.models import TestResult

if TYPE_CHECKING:
    from engines.registry_runtime import RegistryRuntime


async def run(
    *,
    registry: RegistryRuntime | None,
    fixtures_root: Path | None,
) -> TestResult:
    start = time.perf_counter()

    if registry is None or fixtures_root is None:
        return TestResult(
            test_id="B",
            status="skip",
            message="registry o fixtures_root no provistos",
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )

    slots = await registry.list_slots()
    results: list[dict[str, Any]] = []
    failures = 0

    for slot in slots:
        if slot["status"] == "disabled" or not slot.get("fixture_path"):
            continue
        fixture_path = fixtures_root / slot["fixture_path"]
        try:
            fixture = load_fixture(fixture_path)
        except FixtureError:
            # Check A ya reporta fixtures rotas — acá solo canonicals.
            continue

        canonical_ref = fixture.metadata.canonical_ref
        if not canonical_ref:
            continue

        canonical_dir = fixture_path.parent
        json_path = canonical_dir / f"{canonical_ref}.json"
        hash_path = canonical_dir / f"{canonical_ref}.sha256"

        if not json_path.is_file() or not hash_path.is_file():
            failures += 1
            results.append(
                {
                    "slot": slot["slot"],
                    "canonical_ref": canonical_ref,
                    "status": "missing",
                    "detail": (
                        f"expected {json_path.name} + {hash_path.name} "
                        f"in {canonical_dir}"
                    ),
                },
            )
            continue

        actual = hashlib.sha256(json_path.read_bytes()).hexdigest().lower()
        expected = hash_path.read_text(encoding="utf-8").split()[0].strip().lower()

        if actual != expected:
            failures += 1
            results.append(
                {
                    "slot": slot["slot"],
                    "canonical_ref": canonical_ref,
                    "status": "hash_mismatch",
                    "expected": expected,
                    "actual": actual,
                },
            )
        else:
            results.append(
                {
                    "slot": slot["slot"],
                    "canonical_ref": canonical_ref,
                    "status": "ok",
                },
            )

    duration_ms = (time.perf_counter() - start) * 1000.0

    if failures == 0:
        return TestResult(
            test_id="B",
            status="pass",
            details={"canonicals": results},
            duration_ms=duration_ms,
        )

    return TestResult(
        test_id="B",
        status="fail",
        severity="fatal",
        error_code=REG_020,
        message=f"{failures} canonical(s) con hash mismatch o ausente",
        details={"canonicals": results},
        duration_ms=duration_ms,
    )
