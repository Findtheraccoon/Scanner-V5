"""Check G — Healthcheck de conectividad externa.

Verifica que los providers externos responden:

- **Twelve Data:** llamada barata a `/quote?symbol=SPY` por cada API
  key configurada (via `TwelveDataClient.test_key`).
- **S3 (opcional):** ping al bucket/endpoint de backup, si está
  configurado por el trader.

**Diseño con callables inyectables:**

El check no importa `TwelveDataClient` ni `boto3` directamente —
recibe 2 callables async que encapsulan la llamada a cada provider.
Esto mantiene el check testeable sin red y desacoplado de las
librerías específicas.

- `td_probe() -> list[dict]`: `[{"key_id": str, "ok": bool, "error"?: str}, ...]`.
- `s3_probe() -> dict`: `{"ok": bool, "error"?: str}` o `None` si S3
  no está configurado.

**Severidad:**

- Ambas probes vacías (`None`) → `skip`.
- Todas las keys TD OK + S3 OK (o ausente) → `pass`.
- Al menos una key TD falla pero otras funcionan → `fail / warning`
  (el sistema puede operar con las keys restantes).
- **Todas** las keys TD fallan → `fail / fatal` (sin provider = sin datos).
- S3 falla → `fail / warning` (backup no operativo, no bloquea scan).
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from modules.validator.models import TestResult

TDProbe = Callable[[], Awaitable[list[dict[str, Any]]]]
S3Probe = Callable[[], Awaitable[dict[str, Any]]]


async def run(
    *,
    td_probe: TDProbe | None = None,
    s3_probe: S3Probe | None = None,
) -> TestResult:
    start = time.perf_counter()

    if td_probe is None and s3_probe is None:
        return TestResult(
            test_id="G",
            status="skip",
            message="sin probes de conectividad configuradas",
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )

    details: dict[str, Any] = {}
    td_results: list[dict[str, Any]] | None = None
    s3_result: dict[str, Any] | None = None

    td_probe_errored = False
    if td_probe is not None:
        try:
            td_results = await td_probe()
            details["twelvedata"] = td_results
        except Exception as e:
            # Probe crasheó antes de reportar por-key. Esto NO implica
            # que todas las keys estén muertas — puede ser un bug del
            # callable. Warning, no fatal.
            td_results = []
            details["twelvedata"] = []
            details["twelvedata_error"] = f"{type(e).__name__}: {e}"
            td_probe_errored = True

    if s3_probe is not None:
        try:
            s3_result = await s3_probe()
            details["s3"] = s3_result
        except Exception as e:
            s3_result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            details["s3"] = s3_result

    # Evaluación
    td_total = len(td_results) if td_results is not None else 0
    td_ok = sum(1 for r in (td_results or []) if r.get("ok"))
    td_all_ok = td_results is None or td_ok == td_total
    td_any_ok = td_results is None or td_ok > 0

    s3_ok = s3_result is None or s3_result.get("ok", False)

    duration_ms = (time.perf_counter() - start) * 1000.0

    # Caso fatal: se probó TD y TODAS las keys fallaron.
    if td_results is not None and td_total > 0 and not td_any_ok:
        return TestResult(
            test_id="G",
            status="fail",
            severity="fatal",
            message=f"todas las {td_total} API keys de Twelve Data fallaron",
            details=details,
            duration_ms=duration_ms,
        )

    if td_all_ok and s3_ok and not td_probe_errored:
        return TestResult(
            test_id="G",
            status="pass",
            details=details,
            duration_ms=duration_ms,
        )

    # Warning: alguna key TD mala, el probe crasheó, o S3 caído.
    failing = []
    if td_probe_errored:
        failing.append("TD probe exception")
    elif td_results is not None and not td_all_ok:
        failing.append(f"{td_total - td_ok}/{td_total} TD keys")
    if not s3_ok:
        failing.append("S3")
    return TestResult(
        test_id="G",
        status="fail",
        severity="warning",
        message="conectividad degradada: " + ", ".join(failing),
        details=details,
        duration_ms=duration_ms,
    )
