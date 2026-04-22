"""Runner del Validator — orquesta la batería de 7 tests D/A/B/C/E/F/G.

**Responsabilidades:**

- Correr los tests en el orden canónico `D → A → B → C → E → F → G`
  (spec §3.2). Los no implementados se emiten como `skip`.
- Emitir el evento WebSocket `validator.progress` con el estado de
  cada test (`running` → `pass`/`fail`/`skip`) para que el Dashboard
  anime el progress bar.
- Devolver un `ValidatorReport` con todos los resultados.

**Fallos Fatal NO abortan la batería** — se sigue corriendo los demás
tests para recolectar todo el diagnóstico en una sola corrida. La
decisión de qué hacer con un `fatal` la toma el caller (el arranque
del backend en V.7 mostrará banner rojo y seguirá en DEGRADED,
confiando en que el trader decida — nunca crashear por Validator).

**Checks no implementados:** se listan acá y se emiten como `skip`
con mensaje `"not implemented yet"`. Cuando se añadan las sub-fases
V.2-V.6, este mapa crece.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.broadcaster import Broadcaster
from api.events import EVENT_VALIDATOR_PROGRESS
from modules.db import now_et
from modules.validator.checks import d_infra
from modules.validator.models import (
    TEST_ORDER,
    TestId,
    TestResult,
    ValidatorReport,
)


class Validator:
    """Orquestador de la batería del Validator.

    No guarda estado entre corridas — cada `run_full_battery()` emite
    un `run_id` nuevo.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker,
        broadcaster: Broadcaster,
        log_dir: Path | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._broadcaster = broadcaster
        self._log_dir = log_dir

    async def run_full_battery(self) -> ValidatorReport:
        """Corre los 7 tests en orden y devuelve el reporte."""
        run_id = str(uuid.uuid4())
        started_at = now_et()
        logger.info(f"Validator run {run_id} — starting full battery")

        results: list[TestResult] = []
        for test_id in TEST_ORDER:
            await self._emit_progress(run_id, test_id, status="running")
            result = await self._run_test(test_id)
            results.append(result)
            await self._emit_progress(
                run_id,
                test_id,
                status=result.status,
                message=result.message,
                error_code=result.error_code,
            )

        finished_at = now_et()
        report = ValidatorReport(
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            tests=results,
        )
        logger.info(
            f"Validator run {run_id} — finished "
            f"overall={report.overall_status} "
            f"duration={(finished_at - started_at).total_seconds():.2f}s",
        )
        return report

    async def _run_test(self, test_id: TestId) -> TestResult:
        """Despacha a la implementación del test.

        Cada check nunca lanza — devuelve un `TestResult` con el estado.
        Si el check no está implementado todavía, devolvemos `skip`.
        """
        if test_id == "D":
            return await d_infra.run(
                session_factory=self._session_factory,
                log_dir=self._log_dir,
            )
        return TestResult(
            test_id=test_id,
            status="skip",
            message="not implemented yet",
        )

    async def _emit_progress(
        self,
        run_id: str,
        test_id: TestId,
        *,
        status: str,
        message: str | None = None,
        error_code: str | None = None,
    ) -> None:
        """Emite `validator.progress` al Broadcaster. Fail-safe."""
        payload: dict[str, Any] = {
            "run_id": run_id,
            "test_id": test_id,
            "status": status,
        }
        if message is not None:
            payload["message"] = message
        if error_code is not None:
            payload["error_code"] = error_code
        try:
            await self._broadcaster.broadcast(EVENT_VALIDATOR_PROGRESS, payload)
        except Exception:
            logger.exception(
                f"validator.progress emit failed for test {test_id} "
                f"(run_id={run_id})",
            )


def utcnow() -> datetime:
    """Helper para tests que mockean el timestamp."""
    return now_et()
