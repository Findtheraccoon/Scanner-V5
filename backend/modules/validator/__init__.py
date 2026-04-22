"""Validator Module — orquestador de la batería de 7 tests del scanner.

Ver `README.md` y `docs/operational/FEATURE_DECISIONS.md §3.2` para el
scope completo. Batería ejecutada en orden canónico:

    D → A → B → C → E → F → G

**API pública:**

    - `Validator(session_factory, broadcaster, log_dir?)` — orquestador.
    - `Validator.run_full_battery()` → `ValidatorReport`.
    - `ValidatorReport`, `TestResult`, `TestId`, `TestStatus`, `Severity`
      (tipos del reporte).
    - `TEST_ORDER`, `TEST_DESCRIPTIONS`.

**Estado actual (V.1):** solo Check D implementado. A/B/C/E/F/G se
emiten como `skip` con `"not implemented yet"`.
"""

from modules.validator.models import (
    TEST_DESCRIPTIONS,
    TEST_ORDER,
    Severity,
    TestId,
    TestResult,
    TestStatus,
    ValidatorReport,
)
from modules.validator.runner import Validator

__all__ = [
    "TEST_DESCRIPTIONS",
    "TEST_ORDER",
    "Severity",
    "TestId",
    "TestResult",
    "TestStatus",
    "Validator",
    "ValidatorReport",
]
