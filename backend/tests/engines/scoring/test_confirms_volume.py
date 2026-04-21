"""Tests de confirms de volumen (Fase 5.1) — VolHigh + VolSeq.

Observatory condiciones portadas literalmente:
    - VolHigh → `volM > 1.5` (estricto, no mayor-o-igual)
    - VolSeq  → `volSeqM.growing is True`
"""

from __future__ import annotations

from engines.scoring.confirms import (
    detect_volume_high_confirm,
    detect_volume_sequence_confirm,
)

# ═══════════════════════════════════════════════════════════════════════════
# VolHigh
# ═══════════════════════════════════════════════════════════════════════════


class TestVolumeHighNone:
    def test_none_returns_empty(self) -> None:
        assert detect_volume_high_confirm(None) == []


class TestVolumeHighBoundary:
    def test_strictly_greater_than_1_5_fires(self) -> None:
        result = detect_volume_high_confirm(1.51)
        assert len(result) == 1
        c = result[0]
        assert c["d"] == "Vol 1.51x avg"
        assert c["sg"] == "CONFIRM"
        assert c["tf"] == "15M"
        assert c["cat"] == "CONFIRM"
        assert c["w"] == 2.0
        assert c["age"] == 0

    def test_exactly_1_5_does_not_fire(self) -> None:
        # Observatory usa `> 1.5`, estricto.
        assert detect_volume_high_confirm(1.5) == []

    def test_below_1_5_does_not_fire(self) -> None:
        assert detect_volume_high_confirm(1.49) == []

    def test_zero_does_not_fire(self) -> None:
        assert detect_volume_high_confirm(0.0) == []


class TestVolumeHighFormatting:
    def test_integer_ratio_shows_dot_zero(self) -> None:
        result = detect_volume_high_confirm(2.0)
        assert result[0]["d"] == "Vol 2.0x avg"

    def test_two_decimal_ratio(self) -> None:
        result = detect_volume_high_confirm(2.47)
        assert result[0]["d"] == "Vol 2.47x avg"

    def test_one_decimal_ratio_no_trailing_zero(self) -> None:
        # Observatory no usa .2f, así que 1.6 → "1.6x" (sin trailing 0)
        result = detect_volume_high_confirm(1.6)
        assert result[0]["d"] == "Vol 1.6x avg"


# ═══════════════════════════════════════════════════════════════════════════
# VolSeq
# ═══════════════════════════════════════════════════════════════════════════


class TestVolumeSequenceNone:
    def test_none_returns_empty(self) -> None:
        assert detect_volume_sequence_confirm(None) == []


class TestVolumeSequenceGrowing:
    def test_growing_fires(self) -> None:
        vol_seq = {"growing": True, "declining": False, "count": 3}
        result = detect_volume_sequence_confirm(vol_seq)
        assert len(result) == 1
        c = result[0]
        # Observatory: f"Vol creciente {count+1} velas" — 3+1=4
        assert c["d"] == "Vol creciente 4 velas"
        assert c["sg"] == "CONFIRM"
        assert c["tf"] == "15M"
        assert c["cat"] == "CONFIRM"
        assert c["w"] == 0.0

    def test_not_growing_does_not_fire(self) -> None:
        vol_seq = {"growing": False, "declining": False, "count": 0}
        assert detect_volume_sequence_confirm(vol_seq) == []

    def test_declining_does_not_fire(self) -> None:
        # Observatory: VolSeq confirm sólo mira `growing`; `declining`
        # es materia del risk detector.
        vol_seq = {"growing": False, "declining": True, "count": -3}
        assert detect_volume_sequence_confirm(vol_seq) == []

    def test_growing_with_count_zero(self) -> None:
        # Borderline: growing=True con count=0 (no debería pasar en la
        # práctica pero el detector solo lee `growing`).
        vol_seq = {"growing": True, "declining": False, "count": 0}
        result = detect_volume_sequence_confirm(vol_seq)
        assert len(result) == 1
        assert result[0]["d"] == "Vol creciente 1 velas"


class TestVolumeSequenceMissingKeys:
    def test_missing_count_defaults_zero(self) -> None:
        vol_seq = {"growing": True}
        result = detect_volume_sequence_confirm(vol_seq)
        assert result[0]["d"] == "Vol creciente 1 velas"

    def test_missing_growing_does_not_fire(self) -> None:
        # Sin key `growing`, get() devuelve None → no dispara.
        assert detect_volume_sequence_confirm({"count": 3}) == []
