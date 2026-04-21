"""Tests del `KeyPool` del Data Engine.

Cubren las invariantes críticas del round-robin proporcional:

1. Validación al construir (vacío, duplicados, más que MAX_API_KEYS).
2. Skip de keys con `enabled=False`.
3. Pick determinístico con proporcionalidad correcta (8/min vs 4/min → 2:1).
4. Respeto del cupo/minuto (nunca excede `credits_per_minute`).
5. Reset automático al cambio de minuto (vía `freezegun`).
6. Bloqueo async cuando todas las elegibles llenaron su cupo/minuto, y
   desbloqueo al próximo rollover.
7. `mark_exhausted` excluye del pool y `reset_daily` lo restaura.
8. `acquire` lanza `KeyPoolExhaustedError` cuando todas están exhausted.
9. `snapshot` no expone `secret`.
10. `shutdown` wipea secretos internos y deja el pool inutilizable.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import timedelta

import pytest
from freezegun import freeze_time

from engines.data.api_keys import KeyPool, KeyPoolExhaustedError
from engines.data.models import ApiKeyConfig, ApiKeyState

# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def make_config(
    key_id: str,
    *,
    credits_per_minute: int = 8,
    credits_per_day: int = 800,
    enabled: bool = True,
    secret: str | None = None,
) -> ApiKeyConfig:
    return ApiKeyConfig(
        key_id=key_id,
        secret=secret if secret is not None else f"secret-{key_id}",
        credits_per_minute=credits_per_minute,
        credits_per_day=credits_per_day,
        enabled=enabled,
    )


async def drain_acquires(pool: KeyPool, n: int) -> list[str]:
    """Llama `pool.acquire()` n veces y devuelve los `key_id` obtenidos."""
    picked: list[str] = []
    for _ in range(n):
        k = await pool.acquire()
        picked.append(k.key_id)
        pool.release(k.key_id, credits_used=1, success=True)
    return picked


# ═══════════════════════════════════════════════════════════════════════════
# Construcción
# ═══════════════════════════════════════════════════════════════════════════


class TestConstruction:
    def test_raises_when_keys_list_is_empty(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            KeyPool([])

    def test_raises_on_duplicate_key_ids(self) -> None:
        keys = [make_config("k1"), make_config("k1")]
        with pytest.raises(ValueError, match="Duplicate"):
            KeyPool(keys)

    def test_raises_when_exceeding_max_api_keys(self) -> None:
        keys = [make_config(f"k{i}") for i in range(6)]
        with pytest.raises(ValueError, match="at most"):
            KeyPool(keys)

    def test_accepts_up_to_max_keys(self) -> None:
        keys = [make_config(f"k{i}") for i in range(5)]
        pool = KeyPool(keys)
        assert len(pool.snapshot()) == 5


# ═══════════════════════════════════════════════════════════════════════════
# Acquire / release
# ═══════════════════════════════════════════════════════════════════════════


class TestAcquireBasics:
    async def test_acquire_returns_enabled_key(self) -> None:
        pool = KeyPool([make_config("only")])
        key = await pool.acquire()
        assert key.key_id == "only"
        assert key.secret == "secret-only"

    async def test_acquire_skips_disabled_keys(self) -> None:
        pool = KeyPool(
            [
                make_config("off", enabled=False),
                make_config("on"),
            ]
        )
        key = await pool.acquire()
        assert key.key_id == "on"

    async def test_release_updates_daily_counter(self) -> None:
        pool = KeyPool([make_config("k1", credits_per_minute=8, credits_per_day=100)])
        k = await pool.acquire()
        pool.release(k.key_id, credits_used=3, success=True)
        [state] = pool.snapshot()
        # reservado 1 en acquire + ajuste (3 - 1) = 3 en minute
        assert state.used_minute == 3
        assert state.used_daily == 3
        assert state.last_call_ts is not None

    async def test_release_with_credits_zero_undoes_reservation(self) -> None:
        pool = KeyPool([make_config("k1")])
        k = await pool.acquire()
        pool.release(k.key_id, credits_used=0, success=False)
        [state] = pool.snapshot()
        assert state.used_minute == 0
        assert state.used_daily == 0
        assert state.last_call_ts is None

    async def test_release_with_failure_does_not_set_last_call_ts(self) -> None:
        pool = KeyPool([make_config("k1")])
        k = await pool.acquire()
        pool.release(k.key_id, credits_used=1, success=False)
        [state] = pool.snapshot()
        assert state.last_call_ts is None
        assert state.used_daily == 1  # provider cobró, contabiliza

    async def test_release_rejects_negative_credits(self) -> None:
        pool = KeyPool([make_config("k1")])
        k = await pool.acquire()
        with pytest.raises(ValueError):
            pool.release(k.key_id, credits_used=-1)

    async def test_release_is_no_op_for_unknown_key_id(self) -> None:
        pool = KeyPool([make_config("k1")])
        # No crash, no exception
        pool.release("does-not-exist", credits_used=1)


# ═══════════════════════════════════════════════════════════════════════════
# Pick proporcional
# ═══════════════════════════════════════════════════════════════════════════


class TestProportionalPick:
    @freeze_time("2025-03-10 14:30:00", tz_offset=0)
    async def test_two_keys_same_cpm_split_evenly(self) -> None:
        pool = KeyPool(
            [
                make_config("a", credits_per_minute=8),
                make_config("b", credits_per_minute=8),
            ]
        )
        picks = await drain_acquires(pool, 8)
        counts = Counter(picks)
        # Con cupos iguales el split debe ser 4-4.
        assert counts["a"] == 4
        assert counts["b"] == 4

    @freeze_time("2025-03-10 14:30:00", tz_offset=0)
    async def test_proportional_to_credits_per_minute(self) -> None:
        pool = KeyPool(
            [
                make_config("fast", credits_per_minute=8),
                make_config("slow", credits_per_minute=4),
            ]
        )
        # 12 picks en el mismo minuto: 8 a fast, 4 a slow.
        picks = await drain_acquires(pool, 12)
        counts = Counter(picks)
        assert counts["fast"] == 8
        assert counts["slow"] == 4

    @freeze_time("2025-03-10 14:30:00", tz_offset=0)
    async def test_exhausted_key_is_skipped(self) -> None:
        pool = KeyPool(
            [
                make_config("fast", credits_per_minute=8),
                make_config("slow", credits_per_minute=4),
            ]
        )
        pool.mark_exhausted("fast")
        picks = await drain_acquires(pool, 4)
        # "slow" recibe todo el tráfico hasta agotar su cupo.
        assert set(picks) == {"slow"}

    @freeze_time("2025-03-10 14:30:00", tz_offset=0)
    async def test_tie_broken_by_key_id_deterministic(self) -> None:
        pool = KeyPool(
            [
                make_config("b", credits_per_minute=8),
                make_config("a", credits_per_minute=8),
            ]
        )
        # Primer pick: ambas en 0/8, misma fracción → gana la de key_id menor.
        k = await pool.acquire()
        assert k.key_id == "a"


# ═══════════════════════════════════════════════════════════════════════════
# Minute rollover
# ═══════════════════════════════════════════════════════════════════════════


class TestMinuteRollover:
    async def test_used_minute_resets_on_minute_change(self) -> None:
        with freeze_time("2025-03-10 14:30:00") as frozen:
            pool = KeyPool([make_config("k1", credits_per_minute=2)])
            await pool.acquire()
            pool.release("k1", credits_used=1, success=True)
            await pool.acquire()
            pool.release("k1", credits_used=1, success=True)
            [state] = pool.snapshot()
            assert state.used_minute == 2

            # Cambio de minuto: used_minute debe resetearse en el próximo uso.
            frozen.move_to("2025-03-10 14:31:00")
            k = await pool.acquire()
            pool.release(k.key_id, credits_used=1, success=True)
            [state] = pool.snapshot()
            assert state.used_minute == 1


# ═══════════════════════════════════════════════════════════════════════════
# Bloqueo y exhaustion
# ═══════════════════════════════════════════════════════════════════════════


class TestBlockingAndExhaustion:
    async def test_acquire_blocks_when_all_at_minute_cap_and_resumes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Al saturar el cupo/minuto, acquire duerme hasta el rollover.

        Interceptamos `asyncio.sleep` para avanzar el reloj frozen en vez
        de esperar wall-clock real.
        """
        with freeze_time("2025-03-10 14:30:00") as frozen:
            real_sleep = asyncio.sleep

            async def fast_sleep(seconds: float, *args: object, **kwargs: object) -> None:
                frozen.tick(timedelta(seconds=seconds))
                await real_sleep(0)

            monkeypatch.setattr(asyncio, "sleep", fast_sleep)

            pool = KeyPool([make_config("k1", credits_per_minute=1)])
            first = await pool.acquire()
            pool.release(first.key_id, credits_used=1, success=True)

            # Segunda acquire debe bloquear hasta rollover y luego volver.
            k = await pool.acquire()
            assert k.key_id == "k1"

    async def test_acquire_raises_when_all_enabled_exhausted(self) -> None:
        pool = KeyPool(
            [
                make_config("a"),
                make_config("b"),
            ]
        )
        pool.mark_exhausted("a")
        pool.mark_exhausted("b")
        with pytest.raises(KeyPoolExhaustedError):
            await pool.acquire()

    async def test_acquire_raises_when_only_enabled_is_exhausted(self) -> None:
        pool = KeyPool(
            [
                make_config("off", enabled=False),
                make_config("on"),
            ]
        )
        pool.mark_exhausted("on")
        with pytest.raises(KeyPoolExhaustedError):
            await pool.acquire()

    async def test_reset_daily_restores_exhausted_keys(self) -> None:
        pool = KeyPool([make_config("k1"), make_config("k2")])
        pool.mark_exhausted("k1")
        pool.mark_exhausted("k2")
        pool.reset_daily()
        k = await pool.acquire()
        assert k.key_id in {"k1", "k2"}
        states = {s.key_id: s for s in pool.snapshot()}
        assert not states["k1"].exhausted
        assert not states["k2"].exhausted
        assert states["k1"].used_daily == 0
        assert states["k2"].used_daily == 0


# ═══════════════════════════════════════════════════════════════════════════
# Snapshot
# ═══════════════════════════════════════════════════════════════════════════


class TestSnapshot:
    def test_snapshot_returns_apikeystate_without_secret(self) -> None:
        pool = KeyPool([make_config("k1", secret="supersecret")])
        [state] = pool.snapshot()
        assert isinstance(state, ApiKeyState)
        # ApiKeyState no tiene campo `secret` por diseño
        assert "secret" not in type(state).model_fields
        # Pydantic v2 disallows extra por default, así que esto también
        # confirma que el dict tampoco lo incluye
        assert "secret" not in state.model_dump()

    def test_snapshot_preserves_insertion_order(self) -> None:
        pool = KeyPool(
            [
                make_config("zeta"),
                make_config("alpha"),
                make_config("mu"),
            ]
        )
        ids = [s.key_id for s in pool.snapshot()]
        assert ids == ["zeta", "alpha", "mu"]

    def test_snapshot_reflects_max_caps_from_config(self) -> None:
        pool = KeyPool([make_config("k1", credits_per_minute=8, credits_per_day=800)])
        [state] = pool.snapshot()
        assert state.max_minute == 8
        assert state.max_daily == 800


# ═══════════════════════════════════════════════════════════════════════════
# Shutdown
# ═══════════════════════════════════════════════════════════════════════════


class TestShutdown:
    async def test_shutdown_wipes_internal_secrets(self) -> None:
        pool = KeyPool([make_config("k1", secret="topsecret")])
        k = await pool.acquire()
        assert k.secret == "topsecret"
        pool.shutdown()
        # Tras shutdown, acquire debe fallar (pool inutilizable).
        with pytest.raises(RuntimeError, match="shut down"):
            await pool.acquire()
        # Y los entries internos tienen secret vaciado.
        assert all(e.secret == "" for e in pool._entries.values())

    def test_shutdown_is_idempotent(self) -> None:
        pool = KeyPool([make_config("k1")])
        pool.shutdown()
        pool.shutdown()  # no debe lanzar
