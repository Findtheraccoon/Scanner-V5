"""Modelos del Validator Module.

Tipos públicos del reporte de validación. Diseñado para serializarse
directamente a JSON (payload del evento `validator.progress` y REST
`GET /api/v1/validator/report`).

**Glosario:**

- `TestId`: id canónico del test (`"D"` a `"G"`). Orden de ejecución:
  `D → A → B → C → E → F → G`.
- `TestStatus`: estado actual del test.
    - `pending` — aún no arrancó.
    - `running` — en ejecución.
    - `pass` — terminó OK.
    - `fail` — terminó con un problema; severidad en `severity`.
    - `skip` — no se ejecutó (no implementado, dataset ausente, etc.).
- `Severity`: solo aplica cuando `status="fail"`.
    - `fatal` — sistema no puede operar.
    - `degraded` — un slot específico no puede operar.
    - `warning` — operable pero con advertencia.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TestId = Literal["D", "A", "B", "C", "E", "F", "G"]
TestStatus = Literal["pending", "running", "pass", "fail", "skip"]
Severity = Literal["fatal", "degraded", "warning"]

# Orden canónico de ejecución (spec §3.2 batería del Validator).
TEST_ORDER: tuple[TestId, ...] = ("D", "A", "B", "C", "E", "F", "G")

# Descripciones humanas de cada test (para UI y logs).
TEST_DESCRIPTIONS: dict[TestId, str] = {
    "D": "Diagnóstico de infraestructura",
    "A": "Validación de fixtures",
    "B": "Validación de canonicals (hashes)",
    "C": "Validación del Slot Registry",
    "E": "Test end-to-end (is_validator_test)",
    "F": "Parity exhaustivo vs canonical QQQ",
    "G": "Healthcheck de conectividad externa",
}


class TestResult(BaseModel):
    """Resultado de un test individual de la batería."""

    # Evita que pytest colecte esta clase como tests (empieza con "Test").
    __test__ = False

    model_config = ConfigDict(frozen=True, extra="forbid")

    test_id: TestId
    status: TestStatus
    severity: Severity | None = None
    message: str | None = None
    error_code: str | None = Field(
        default=None,
        description="FIX-XXX / REG-XXX / ENG-XXX / VAL-XXX cuando aplique.",
    )
    details: dict = Field(default_factory=dict)
    duration_ms: float = 0.0


class ValidatorReport(BaseModel):
    """Reporte completo de una corrida del Validator."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    tests: list[TestResult]

    @property
    def overall_status(self) -> Literal["pass", "fail", "partial"]:
        """Resumen del reporte.

        - `pass` — todos los tests corridos pasaron (skip no cuenta como fail).
        - `fail` — al menos un test `fail` con severidad `fatal`.
        - `partial` — algún `fail` no-fatal O todos skipped O mix.
        """
        statuses = [t.status for t in self.tests]
        if "fail" in statuses:
            fatal = any(
                t.status == "fail" and t.severity == "fatal"
                for t in self.tests
            )
            return "fail" if fatal else "partial"
        if all(s == "skip" for s in statuses):
            return "partial"
        if all(s in ("pass", "skip") for s in statuses):
            return "pass"
        return "partial"
