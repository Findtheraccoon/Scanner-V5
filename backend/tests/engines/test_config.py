"""Tests de `DataEngineConfig`.

Cubren validación, defaults desde constants.py, inmutabilidad, y
roundtrip de serialización JSON.
"""

from __future__ import annotations

import pytest

from engines.data.config import DataEngineConfig
from engines.data.constants import (
    AUTO_CYCLE_DELAY_AFTER_CLOSE_S,
    ENG_060_CYCLES_THRESHOLD,
    RETRY_SHORT_DELAY_S,
    WARMUP_1H_N,
    WARMUP_15M_N,
    WARMUP_DAILY_N,
)
from engines.data.models import ApiKeyConfig

# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _key(
    key_id: str,
    *,
    enabled: bool = True,
    cpm: int = 8,
    cpd: int = 800,
) -> ApiKeyConfig:
    return ApiKeyConfig(
        key_id=key_id,
        secret=f"secret-{key_id}",
        credits_per_minute=cpm,
        credits_per_day=cpd,
        enabled=enabled,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Construcción válida + defaults
# ═══════════════════════════════════════════════════════════════════════════


class TestConstruction:
    def test_minimal_config_with_one_enabled_key(self) -> None:
        cfg = DataEngineConfig(api_keys=[_key("k1")])
        assert len(cfg.api_keys) == 1
        assert cfg.api_keys[0].key_id == "k1"

    def test_applies_defaults_from_constants(self) -> None:
        cfg = DataEngineConfig(api_keys=[_key("k1")])
        assert cfg.warmup_daily_n == WARMUP_DAILY_N
        assert cfg.warmup_1h_n == WARMUP_1H_N
        assert cfg.warmup_15m_n == WARMUP_15M_N
        assert cfg.retry_short_delay_s == RETRY_SHORT_DELAY_S
        assert cfg.eng_060_cycles_threshold == ENG_060_CYCLES_THRESHOLD
        assert cfg.auto_cycle_delay_after_close_s == AUTO_CYCLE_DELAY_AFTER_CLOSE_S
        assert cfg.http_timeout_s == 10.0

    def test_accepts_mixed_enabled_disabled_keys(self) -> None:
        cfg = DataEngineConfig(
            api_keys=[
                _key("k1", enabled=True),
                _key("k2", enabled=False),
            ]
        )
        assert len(cfg.api_keys) == 2

    def test_accepts_max_keys(self) -> None:
        cfg = DataEngineConfig(api_keys=[_key(f"k{i}") for i in range(5)])
        assert len(cfg.api_keys) == 5


# ═══════════════════════════════════════════════════════════════════════════
# Validación
# ═══════════════════════════════════════════════════════════════════════════


class TestValidation:
    def test_rejects_empty_api_keys_list(self) -> None:
        with pytest.raises(ValueError, match="at least one api_key"):
            DataEngineConfig(api_keys=[])

    def test_rejects_more_than_max_keys(self) -> None:
        keys = [_key(f"k{i}") for i in range(6)]
        with pytest.raises(ValueError, match="at most 5"):
            DataEngineConfig(api_keys=keys)

    def test_rejects_duplicate_key_ids(self) -> None:
        with pytest.raises(ValueError, match="duplicate key_id"):
            DataEngineConfig(api_keys=[_key("k1"), _key("k1")])

    def test_rejects_all_disabled_keys(self) -> None:
        with pytest.raises(ValueError, match="at least one enabled"):
            DataEngineConfig(api_keys=[_key("k1", enabled=False)])

    def test_rejects_extra_unknown_field(self) -> None:
        with pytest.raises(ValueError, match=r"[Ee]xtra"):
            # `extra="forbid"` atrapa typos de campo al deserializar.
            DataEngineConfig.model_validate(
                {
                    "api_keys": [_key("k1").model_dump()],
                    "warmup_daily_count": 300,  # typo: debería ser warmup_daily_n
                }
            )

    def test_rejects_zero_warmup(self) -> None:
        with pytest.raises(ValueError):
            DataEngineConfig(api_keys=[_key("k1")], warmup_daily_n=0)

    def test_rejects_negative_timeout(self) -> None:
        with pytest.raises(ValueError):
            DataEngineConfig(api_keys=[_key("k1")], http_timeout_s=-1.0)

    def test_rejects_zero_retry_delay(self) -> None:
        with pytest.raises(ValueError):
            DataEngineConfig(api_keys=[_key("k1")], retry_short_delay_s=0.0)


# ═══════════════════════════════════════════════════════════════════════════
# Overrides
# ═══════════════════════════════════════════════════════════════════════════


class TestOverrides:
    def test_override_warmup_sizes(self) -> None:
        cfg = DataEngineConfig(
            api_keys=[_key("k1")],
            warmup_daily_n=300,
            warmup_1h_n=120,
            warmup_15m_n=80,
        )
        assert cfg.warmup_daily_n == 300
        assert cfg.warmup_1h_n == 120
        assert cfg.warmup_15m_n == 80

    def test_override_retry_policy(self) -> None:
        cfg = DataEngineConfig(
            api_keys=[_key("k1")],
            retry_short_delay_s=0.5,
            eng_060_cycles_threshold=5,
        )
        assert cfg.retry_short_delay_s == 0.5
        assert cfg.eng_060_cycles_threshold == 5

    def test_override_http_timeout(self) -> None:
        cfg = DataEngineConfig(api_keys=[_key("k1")], http_timeout_s=30.0)
        assert cfg.http_timeout_s == 30.0


# ═══════════════════════════════════════════════════════════════════════════
# Invariantes estructurales
# ═══════════════════════════════════════════════════════════════════════════


class TestStructuralInvariants:
    def test_config_is_frozen(self) -> None:
        cfg = DataEngineConfig(api_keys=[_key("k1")])
        with pytest.raises((TypeError, ValueError)):
            cfg.http_timeout_s = 99.0  # type: ignore[misc]

    def test_roundtrip_via_json(self) -> None:
        original = DataEngineConfig(
            api_keys=[_key("k1"), _key("k2", enabled=False)],
            warmup_daily_n=250,
            http_timeout_s=15.5,
        )
        payload = original.model_dump_json()
        restored = DataEngineConfig.model_validate_json(payload)
        assert restored == original

    def test_api_keys_equality_preserves_secrets(self) -> None:
        # El roundtrip debe preservar campos sensibles (el caller es
        # responsable de no serializar esto a disco sin encriptar).
        cfg = DataEngineConfig(api_keys=[_key("k1")])
        restored = DataEngineConfig.model_validate_json(cfg.model_dump_json())
        assert restored.api_keys[0].secret == "secret-k1"
