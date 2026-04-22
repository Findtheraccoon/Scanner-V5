"""Log TXT del Validator — spec §3.2 (`/LOG/` + retención 5 días).

Escribe un archivo human-readable por cada corrida completa del
Validator (`run_full_battery`). Rota archivos más viejos que
`retention_days` al escribir el nuevo — simple y suficiente para el
volumen esperado (una corrida por arranque + on-demand, típicamente
< 1 archivo/día).

**Formato del archivo:**

    Validator run <run_id>
    started_at: <iso>
    finished_at: <iso>
    overall_status: pass|fail|partial
    ============================================================
    [D] <Diagnóstico de infraestructura> → <status> (<duration_ms>ms)
        severity: <...>       # solo si aplica
        error_code: <...>     # solo si aplica
        message: <...>        # solo si aplica
        details: <json_pretty> # solo si tiene entradas
    ...

**Naming:** `validator-<YYYYMMDD-HHMMSS>-<run_id_short>.txt` en
`log_dir`. Ordenables alfabéticamente = cronológicamente.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from loguru import logger

from modules.validator.models import (
    TEST_DESCRIPTIONS,
    TEST_ORDER,
    TestResult,
    ValidatorReport,
)

DEFAULT_RETENTION_DAYS = 5


def write_report_log(
    report: ValidatorReport,
    log_dir: Path,
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> Path:
    """Persiste `report` como TXT en `log_dir` + rota archivos viejos.

    Args:
        report: reporte a escribir.
        log_dir: directorio destino (se crea si no existe).
        retention_days: archivos `validator-*.txt` más viejos que esto
            se borran. Por default 5 (spec §3.2 y §4 logs).

    Returns:
        Path absoluto al archivo escrito.
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    stamp = report.started_at.strftime("%Y%m%d-%H%M%S")
    short_id = report.run_id.split("-")[0]
    target = log_dir / f"validator-{stamp}-{short_id}.txt"
    target.write_text(_format_report(report), encoding="utf-8")

    _rotate_old_logs(log_dir, retention_days=retention_days)
    return target


def _format_report(report: ValidatorReport) -> str:
    lines: list[str] = []
    lines.append(f"Validator run {report.run_id}")
    lines.append(f"started_at: {report.started_at.isoformat()}")
    lines.append(
        f"finished_at: "
        f"{report.finished_at.isoformat() if report.finished_at else '-'}",
    )
    lines.append(f"overall_status: {report.overall_status}")
    lines.append("=" * 60)

    by_id = {t.test_id: t for t in report.tests}
    for test_id in TEST_ORDER:
        t = by_id.get(test_id)
        if t is None:
            continue
        lines.append(_format_test_result(t))
    lines.append("")
    return "\n".join(lines)


def _format_test_result(t: TestResult) -> str:
    parts: list[str] = []
    desc = TEST_DESCRIPTIONS.get(t.test_id, "")
    header = (
        f"[{t.test_id}] {desc} → {t.status} ({t.duration_ms:.1f}ms)"
    )
    parts.append(header)
    if t.severity is not None:
        parts.append(f"    severity: {t.severity}")
    if t.error_code is not None:
        parts.append(f"    error_code: {t.error_code}")
    if t.message is not None:
        parts.append(f"    message: {t.message}")
    if t.details:
        details_json = json.dumps(t.details, indent=2, ensure_ascii=False)
        indented = "\n".join("    " + ln for ln in details_json.splitlines())
        parts.append(f"    details:\n{indented}")
    return "\n".join(parts)


def _rotate_old_logs(log_dir: Path, *, retention_days: int) -> None:
    """Borra `validator-*.txt` con mtime anterior a `retention_days`."""
    cutoff = datetime.now().timestamp() - (retention_days * 86400)
    for f in log_dir.glob("validator-*.txt"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            # Fallo al borrar un archivo viejo no es crítico — seguimos.
            logger.warning(f"could not rotate validator log {f}")
