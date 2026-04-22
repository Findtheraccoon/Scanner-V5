"""Check E — Test end-to-end del pipeline de scan.

Verifica que el pipeline completo (fetch → analyze → scan_and_emit
con `persist=False`) corre sin crashear y devuelve un output con la
shape esperada. Usa el flag `is_validator_test` = `persist=False` del
pipeline para NO contaminar la DB de producción ni emitir `signal.new`
al WebSocket (spec §3.2).

**Diseño con `scan_executor` inyectable:**

El check no conoce al `DataEngine` ni al `RegistryRuntime` directo —
recibe un callable async `scan_executor() -> dict` que encapsula la
coordinación (fetch del ticker + build fixture + invocación de
`scan_and_emit` con `persist=False`). Esto:

- Mantiene el check testeable sin mockear toda la cadena Data Engine +
  registry + DB.
- Permite al wiring (V.7) construir el executor con referencias
  reales — el Validator no depende de ninguna capa.

**Severidad:**

- Executor retorna dict con shape esperada → `pass`.
- Executor lanza o devuelve shape inválida → `fail / fatal` (si el
  pipeline E2E no corre, el sistema no puede operar).
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from modules.validator.models import TestResult

ScanExecutor = Callable[[], Awaitable[dict]]


# Claves que `scan_and_emit` siempre devuelve, independiente del resultado.
# El check E las verifica para confirmar que el pipeline corrió completo.
_REQUIRED_KEYS: frozenset[str] = frozenset({
    "ticker",
    "signal",
    "score",
    "persisted",
})


async def run(*, scan_executor: ScanExecutor | None) -> TestResult:
    start = time.perf_counter()

    if scan_executor is None:
        return TestResult(
            test_id="E",
            status="skip",
            message="scan_executor no provisto",
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )

    try:
        out = await scan_executor()
    except Exception as e:
        return TestResult(
            test_id="E",
            status="fail",
            severity="fatal",
            message=f"pipeline E2E lanzó excepción: {e.__class__.__name__}: {e}",
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )

    if not isinstance(out, dict):
        return TestResult(
            test_id="E",
            status="fail",
            severity="fatal",
            message=f"scan_executor devolvió {type(out).__name__}, esperaba dict",
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )

    missing = sorted(_REQUIRED_KEYS - set(out.keys()))
    if missing:
        return TestResult(
            test_id="E",
            status="fail",
            severity="fatal",
            message=f"output del pipeline sin claves esperadas: {missing}",
            details={"output_keys": sorted(out.keys())},
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )

    # Invariante: el check E usa persist=False. Si el executor se usó
    # para persistir, es un bug del wiring.
    if out.get("persisted") is True:
        return TestResult(
            test_id="E",
            status="fail",
            severity="fatal",
            message=(
                "scan_executor persistió la señal — is_validator_test debe "
                "usar persist=False para no contaminar la DB"
            ),
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )

    duration_ms = (time.perf_counter() - start) * 1000.0
    return TestResult(
        test_id="E",
        status="pass",
        details={
            "ticker": out.get("ticker"),
            "signal": out.get("signal"),
            "score": out.get("score"),
            "persisted": out.get("persisted"),
        },
        duration_ms=duration_ms,
    )
