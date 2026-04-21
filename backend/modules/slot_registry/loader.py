"""Loader del `slot_registry.json`.

Carga y valida el archivo de topología operativa siguiendo la jerarquía
de severidad de `docs/specs/SLOT_REGISTRY_SPEC.md §8`:

    1. Errores estructurales del archivo y compatibilidad del motor →
       `RegistryError` (fatal, abortan arranque).
    2. Errores por-slot → el `SlotRecord` correspondiente queda con
       `status=DEGRADED` y los demás siguen funcionando.
    3. Hash mismatch de canonical (REG-020) → fatal (integridad crítica).

Secuencia (§8 del spec):

    1. Leer archivo / parsear JSON.
    2. Validar estructura top-level y metadata.
    3. Validar compatibilidad de motor (REG-030).
    4. Para cada slot enabled:
        a. Cargar la fixture (errores de I/O y FIX-XXX → DEGRADED).
        b. Validar consistencia ticker/benchmark (REG-012/013).
        c. Validar engine_compat_range de la fixture (REG-011).
        d. Verificar hash del canonical (si aplica) — REG-020 fatal.
    5. Validar unicidad de ticker entre operativos (REG-005).
    6. Retornar `SlotRegistry` con los 6 slots y sus estados.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version
from pydantic import ValidationError

from modules.fixtures import FixtureError, load_fixture
from modules.slot_registry.errors import (
    REG_001,
    REG_002,
    REG_003,
    REG_004,
    REG_005,
    REG_010,
    REG_011,
    REG_012,
    REG_013,
    REG_020,
    REG_030,
    REG_101,
    RegistryError,
)
from modules.slot_registry.models import RegistryMetadata, SlotRecord, SlotRegistry

_TOP_LEVEL_BLOCKS: frozenset[str] = frozenset({"registry_metadata", "slots"})


def load_registry(
    registry_path: str | Path,
    *,
    engine_version: str,
    fixtures_root: str | Path | None = None,
) -> SlotRegistry:
    """Carga y valida el `slot_registry.json`.

    Args:
        registry_path: path al archivo del registry.
        engine_version: versión actual del Scoring Engine (ej. "5.2.0").
            Se chequea contra `engine_version_required` del registry
            (REG-030 fatal) y `engine_compat_range` de cada fixture
            (REG-011 per-slot).
        fixtures_root: directorio base para resolver paths relativos de
            fixtures. Si es `None`, se usa el directorio del registry.

    Returns:
        `SlotRegistry` con los 6 slots evaluados.

    Raises:
        RegistryError: con `code` en {REG-001, REG-002, REG-003, REG-004,
            REG-020, REG-030} si hubo un error fatal que impide arrancar
            el sistema.
    """
    path = Path(registry_path)
    root = Path(fixtures_root) if fixtures_root is not None else path.parent

    # ── 1. I/O + JSON parse (FATAL REG-001 / REG-002)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as e:
        raise RegistryError(REG_001, f"slot_registry file not found: {path}") from e
    except OSError as e:
        raise RegistryError(REG_001, f"cannot read slot_registry: {e}") from e
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RegistryError(REG_002, f"slot_registry is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise RegistryError(REG_002, "slot_registry top-level must be a JSON object")

    # ── 2. Top-level shape (FATAL REG-002)
    missing = _TOP_LEVEL_BLOCKS - set(data.keys())
    if missing:
        raise RegistryError(REG_002, f"missing top-level block(s): {sorted(missing)}")
    extra = set(data.keys()) - _TOP_LEVEL_BLOCKS
    if extra:
        raise RegistryError(
            REG_002,
            f"unknown top-level block(s): {sorted(extra)}. Valid: {sorted(_TOP_LEVEL_BLOCKS)}",
        )

    # ── 3. Parsear metadata (FATAL REG-002 en error de shape/tipos)
    try:
        metadata = RegistryMetadata.model_validate(data["registry_metadata"])
    except ValidationError as e:
        raise RegistryError(
            REG_002, f"registry_metadata schema error: {_summarize_errors(e)}"
        ) from e

    # ── 4. Compatibilidad del motor (FATAL REG-030)
    if not _version_in_range(engine_version, metadata.engine_version_required):
        raise RegistryError(
            REG_030,
            f"registry requires engine in range {metadata.engine_version_required!r} "
            f"but engine is {engine_version!r}",
        )

    # ── 5. Cardinalidad y unicidad de IDs (FATAL REG-003 / REG-004)
    raw_slots = data["slots"]
    if not isinstance(raw_slots, list):
        raise RegistryError(REG_002, "slots must be a JSON array")
    if len(raw_slots) != 6:
        raise RegistryError(
            REG_003,
            f"slot_registry must have exactly 6 slots. Found {len(raw_slots)}",
        )

    ids = [s.get("slot") for s in raw_slots if isinstance(s, dict)]
    if len(ids) != 6:
        raise RegistryError(REG_002, "each slot must be an object with a `slot` field")
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise RegistryError(REG_004, f"duplicate slot id(s): {duplicates}")
    if set(ids) != {1, 2, 3, 4, 5, 6}:
        raise RegistryError(
            REG_003, f"slot ids must cover the range 1..6 exactly, got {sorted(ids)}"
        )

    # ── 6. Evaluar cada slot. REG-020 (hash mismatch) se propaga como fatal.
    #       Los demás errores quedan en el SlotRecord como DEGRADED.
    warnings: list[str] = []
    records_by_slot: dict[int, SlotRecord] = {}
    for raw_slot in sorted(raw_slots, key=lambda s: s["slot"]):
        record = _evaluate_slot(
            raw_slot,
            fixtures_root=root,
            engine_version=engine_version,
            warnings=warnings,
        )
        records_by_slot[record.slot] = record

    # ── 7. Unicidad de ticker entre OPERATIVE (REG-005 per-slot DEGRADED)
    seen_tickers: dict[str, int] = {}
    for slot_id in sorted(records_by_slot.keys()):
        rec = records_by_slot[slot_id]
        if rec.status != "OPERATIVE" or rec.ticker is None:
            continue
        if rec.ticker in seen_tickers:
            first = seen_tickers[rec.ticker]
            records_by_slot[slot_id] = rec.model_copy(
                update={
                    "status": "DEGRADED",
                    "fixture": None,
                    "error_code": REG_005,
                    "error_detail": (
                        f"ticker {rec.ticker!r} ya está asignado al slot {first} (OPERATIVE). "
                        f"Se degrada el slot {slot_id} para mantener unicidad."
                    ),
                }
            )
        else:
            seen_tickers[rec.ticker] = rec.slot

    ordered = [records_by_slot[i] for i in range(1, 7)]
    return SlotRegistry(metadata=metadata, slots=ordered, warnings=warnings)


# ═══════════════════════════════════════════════════════════════════════════
# Evaluación por-slot
# ═══════════════════════════════════════════════════════════════════════════


def _evaluate_slot(
    raw: dict[str, Any],
    *,
    fixtures_root: Path,
    engine_version: str,
    warnings: list[str],
) -> SlotRecord:
    slot_id = raw["slot"]
    enabled = bool(raw.get("enabled", False))
    ticker = raw.get("ticker")
    fixture_rel = raw.get("fixture")
    benchmark = raw.get("benchmark")
    priority = raw.get("priority")
    notes = raw.get("notes")

    if not enabled:
        # §5.3: disabled slot con campos populados → REG-101 warning.
        populated = [k for k in ("ticker", "fixture", "benchmark") if raw.get(k) is not None]
        if populated:
            warnings.append(
                f"{REG_101}: slot {slot_id} disabled pero tiene campos populados: {populated}"
            )
        return SlotRecord(
            slot=slot_id,
            status="DISABLED",
            ticker=ticker,
            fixture_path=fixture_rel,
            fixture=None,
            benchmark=benchmark,
            priority=priority,
            notes=notes,
            error_code=None,
            error_detail=None,
        )

    # Slot enabled — validar campos obligatorios y cargar fixture.
    if not ticker or not fixture_rel:
        return _degraded(
            raw,
            REG_010,
            "enabled slot requires ticker and fixture path",
        )

    fixture_path = fixtures_root / fixture_rel
    if not fixture_path.is_file():
        return _degraded(raw, REG_010, f"fixture file not found: {fixture_path}")

    try:
        fixture = load_fixture(fixture_path)
    except FixtureError as e:
        # Propagamos el código FIX-XXX original para trazabilidad.
        return _degraded(raw, e.code, e.detail)

    # §5.4 regla 13: ticker matchea.
    if fixture.ticker_info.ticker != ticker:
        return _degraded(
            raw,
            REG_012,
            f"slot {slot_id} declares ticker {ticker!r} but fixture has "
            f"{fixture.ticker_info.ticker!r}",
        )

    # §5.4 regla 14: benchmark matchea.
    if benchmark != fixture.ticker_info.benchmark:
        return _degraded(
            raw,
            REG_013,
            f"slot {slot_id} declares benchmark {benchmark!r} but fixture has "
            f"{fixture.ticker_info.benchmark!r}",
        )

    # §5.6 regla 17: engine_compat_range de la fixture.
    if not _version_in_range(engine_version, fixture.metadata.engine_compat_range):
        return _degraded(
            raw,
            REG_011,
            f"fixture engine_compat_range {fixture.metadata.engine_compat_range!r} "
            f"does not include engine {engine_version!r}",
        )

    # §5.7: hash del canonical.
    #   Si los archivos no existen → DEGRADED (REG-010).
    #   Si existen y el hash no matchea → FATAL (REG-020). Se propaga
    #   desde `_check_canonical_hash` como RegistryError y aborta el
    #   arranque (spec §8: REG-020 es fatal).
    canonical_ref = fixture.metadata.canonical_ref
    if canonical_ref:
        canonical_dir = fixture_path.parent
        canonical_json = canonical_dir / f"{canonical_ref}.json"
        canonical_hash = canonical_dir / f"{canonical_ref}.sha256"
        if not canonical_json.is_file() or not canonical_hash.is_file():
            return _degraded(
                raw,
                REG_010,
                f"canonical files missing for {canonical_ref!r} "
                f"(expected {canonical_json} + {canonical_hash})",
            )
        _check_canonical_hash(canonical_json, canonical_hash, canonical_ref, slot_id)

    return SlotRecord(
        slot=slot_id,
        status="OPERATIVE",
        ticker=ticker,
        fixture_path=fixture_rel,
        fixture=fixture,
        benchmark=benchmark,
        priority=priority,
        notes=notes,
        error_code=None,
        error_detail=None,
    )


def _check_canonical_hash(
    canonical_json: Path,
    canonical_hash: Path,
    canonical_ref: str,
    slot_id: int,
) -> None:
    """Verifica el hash SHA-256 del canonical. Lanza FATAL si mismatch.

    Asume que ambos archivos existen (checkeado por el caller).
    """
    actual = hashlib.sha256(canonical_json.read_bytes()).hexdigest()
    expected = canonical_hash.read_text().split()[0].strip().lower()
    if actual.lower() != expected:
        raise RegistryError(
            REG_020,
            f"canonical hash mismatch for {canonical_ref!r} referenced by slot "
            f"{slot_id}. Expected {expected!r}, got {actual!r}. Either a "
            f"canonical was modified or its .sha256 is stale — integrity failure.",
        )


def _degraded(raw: dict[str, Any], code: str, detail: str) -> SlotRecord:
    return SlotRecord(
        slot=raw["slot"],
        status="DEGRADED",
        ticker=raw.get("ticker"),
        fixture_path=raw.get("fixture"),
        fixture=None,
        benchmark=raw.get("benchmark"),
        priority=raw.get("priority"),
        notes=raw.get("notes"),
        error_code=code,
        error_detail=detail,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Semver helpers
# ═══════════════════════════════════════════════════════════════════════════


def _version_in_range(version: str, range_spec: str) -> bool:
    """Check if `version` (PEP 440) is within npm-style `range_spec`.

    Ejemplos del spec: `">=5.2.0,<6.0.0"`. `packaging` acepta la sintaxis
    de comma-separated specifiers directamente.
    """
    try:
        v = Version(version)
        s = SpecifierSet(range_spec)
    except (InvalidVersion, InvalidSpecifier):
        return False
    return v in s


def _summarize_errors(err: ValidationError) -> str:
    lines: list[str] = []
    for e in err.errors():
        loc = ".".join(str(x) for x in e.get("loc", ()))
        msg = e.get("msg", "")
        lines.append(f"{loc}: {msg}")
    return "; ".join(lines) if lines else "schema validation failed"
