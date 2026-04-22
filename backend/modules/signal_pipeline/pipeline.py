"""Pipeline de señales: analyze → persist → broadcast.

La función `scan_and_emit()` es el punto de entrada que los motores y
schedulers invocan. Encapsula la orquestación de side effects (DB +
WS) alrededor del motor puro `engines.scoring.analyze()`.

**Contratos:**

- **SIEMPRE persiste** el output en la tabla `signals` (incluyendo
  NEUTRAL/blocked/error) — el histórico completo es necesario para
  auditoría y debugging.
- **Solo broadcast `signal.new`** cuando `out["signal"] != "NEUTRAL"`
  y `not out["error"]`. Los estados neutros/errores se exponen vía
  otros eventos (`slot.status`, `engine.status`, `system.log`) en
  C5.7.
- **Nunca lanza excepciones** al caller — la invariante I3 del motor
  se mantiene acá también. Si el persist o el broadcast fallan, se
  loguea y se sigue.

**`chat_format`:** v0 mínimo — template compacto con bloque por
sección. El template rico (v1.1.0 del spec) queda para una fase
posterior junto con el frontend.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from api.broadcaster import Broadcaster
from api.events import EVENT_SIGNAL_NEW
from engines.scoring import analyze
from modules.db import write_signal

SIGNAL_NEUTRAL = "NEUTRAL"


async def scan_and_emit(
    *,
    session: AsyncSession,
    broadcaster: Broadcaster,
    candle_timestamp: _dt.datetime,
    slot_id: int | None,
    ticker: str,
    candles_daily: list[dict],
    candles_1h: list[dict],
    candles_15m: list[dict],
    fixture: dict,
    spy_daily: list[dict] | None = None,
    bench_daily: list[dict] | None = None,
    sim_datetime: str | None = None,
    sim_date: str | None = None,
    candles_snapshot_gzip: bytes | None = None,
) -> dict[str, Any]:
    """Corre el pipeline completo y devuelve el output de `analyze()`
    aumentado con el `id` de la señal persistida.

    Args:
        session: sesión async para escribir.
        broadcaster: broadcaster para emitir `signal.new`.
        candle_timestamp: tz-aware ET del candle 15M que disparó el scan.
        slot_id: id del slot (puede ser `None` para scans ad-hoc).
        ticker, candles_*, fixture, spy_daily, bench_daily,
        sim_datetime, sim_date: args de `analyze()`.
        candles_snapshot_gzip: opcional — snapshot comprimido de los
            inputs para reproducibilidad post-hoc.

    Returns:
        Output de `analyze()` con la clave extra `id` (int del registro
        en `signals`).
    """
    out = analyze(
        ticker=ticker,
        candles_daily=candles_daily,
        candles_1h=candles_1h,
        candles_15m=candles_15m,
        fixture=fixture,
        spy_daily=spy_daily,
        sim_datetime=sim_datetime,
        sim_date=sim_date,
        bench_daily=bench_daily,
    )

    # Persistir siempre — histórico completo para auditoría.
    sig_id = await write_signal(
        session,
        analyze_output=out,
        candle_timestamp=candle_timestamp,
        slot_id=slot_id,
        candles_snapshot_gzip=candles_snapshot_gzip,
    )

    # Broadcast solo si hay señal real (no NEUTRAL ni error).
    should_broadcast = (
        not out.get("error", False)
        and out.get("signal") != SIGNAL_NEUTRAL
    )
    if should_broadcast:
        payload = build_ws_payload(
            out, sig_id=sig_id, candle_timestamp=candle_timestamp,
        )
        await broadcaster.broadcast(EVENT_SIGNAL_NEW, payload)

    return {**out, "id": sig_id}


def build_ws_payload(
    out: dict,
    *,
    sig_id: int,
    candle_timestamp: _dt.datetime,
) -> dict[str, Any]:
    """Arma el payload del evento `signal.new` sin snapshot gzip.

    Incluye: columnas planas + layers + ind + patterns + chat_format.
    """
    return {
        "id": sig_id,
        "ticker": out["ticker"],
        "candle_timestamp": candle_timestamp.isoformat(),
        "engine_version": out.get("engine_version"),
        "fixture_id": out.get("fixture_id"),
        "fixture_version": out.get("fixture_version"),
        "score": out.get("score"),
        "conf": out.get("conf"),
        "signal": out.get("signal"),
        "dir": out.get("dir"),
        "blocked": out.get("blocked"),
        "layers": out.get("layers", {}),
        "ind": out.get("ind", {}),
        "patterns": out.get("patterns", []),
        "chat_format": build_chat_format(out, candle_timestamp=candle_timestamp),
    }


def build_chat_format(
    out: dict,
    *,
    candle_timestamp: _dt.datetime,
) -> str:
    """Template v0 del `chat_format` — texto multilinea listo para pegar
    al chat con Claude.

    El template rico (v1.1.0) lo define el frontend y se implementa en
    una fase posterior. Esta versión mínima cubre los bloques básicos.
    """
    lines: list[str] = []
    ticker = out.get("ticker", "?")
    score = out.get("score")
    conf = out.get("conf", "—")
    dir_ = out.get("dir") or "—"
    signal = out.get("signal", "NEUTRAL")

    header = f"[{ticker}] {dir_} · score {score} ({conf}) · {signal}"
    lines.append(header)
    lines.append(f"Candle: {candle_timestamp.isoformat()}")

    if out.get("error"):
        lines.append(f"ERROR: {out.get('error_code')}")
        return "\n".join(lines)

    if out.get("blocked"):
        lines.append(f"Blocked: {out['blocked']}")

    layers = out.get("layers", {})
    aln = layers.get("alignment") or {}
    if aln:
        lines.append(f"Alignment: {aln.get('dir', '?')} {aln.get('n', 0)}/3")

    trends = layers.get("trends") or {}
    if trends:
        lines.append(
            f"Trends: 15M={trends.get('t15m', '?')} "
            f"1H={trends.get('t1h', '?')} "
            f"D={trends.get('tdaily', '?')}"
        )

    triggers = [p for p in out.get("patterns") or [] if p.get("cat") == "TRIGGER"]
    if triggers:
        lines.append("Triggers:")
        for t in triggers[:5]:
            lines.append(f"  {t.get('d', '?')} (+{t.get('w', 0)})")

    confirm_items = (layers.get("confirm") or {}).get("items") or []
    if confirm_items:
        lines.append("Confirms:")
        for c in confirm_items[:5]:
            lines.append(f"  {c.get('desc', '?')} (+{c.get('weight', 0)})")

    return "\n".join(lines)
