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

**Modo `is_validator_test` (V.3):** el Validator Check E usa este
pipeline con `persist=False`. En ese modo:

- NO se escribe en `signals` (no contamina la DB de producción).
- NO se emite `signal.new` al WebSocket.
- La señal se corre completa contra `analyze()` y el output se
  retorna para que el caller valide shape/estado.
- `session` y `broadcaster` pasan a ser opcionales (`None` permitido).

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
    session: AsyncSession | None,
    broadcaster: Broadcaster | None,
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
    persist: bool = True,
) -> dict[str, Any]:
    """Corre el pipeline completo y devuelve el output de `analyze()`
    aumentado con el `id` de la señal persistida (o `None` si
    `persist=False`).

    Args:
        session: sesión async para escribir. Requerido si
            `persist=True`.
        broadcaster: broadcaster para emitir `signal.new`. Requerido
            si `persist=True`.
        candle_timestamp: tz-aware ET del candle 15M que disparó el scan.
        slot_id: id del slot (puede ser `None` para scans ad-hoc).
        ticker, candles_*, fixture, spy_daily, bench_daily,
        sim_datetime, sim_date: args de `analyze()`.
        candles_snapshot_gzip: opcional — snapshot comprimido de los
            inputs para reproducibilidad post-hoc.
        persist: si `True` (default), escribe en `signals` y emite
            `signal.new`. Si `False` (is_validator_test), solo corre
            `analyze()` y retorna el output — no toca DB ni WS.

    Returns:
        Output de `analyze()` con las claves extra `id` (int del
        registro en `signals`, o `None` si `persist=False`) y
        `persisted` (bool).
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

    if not persist:
        return {**out, "id": None, "persisted": False}

    if session is None or broadcaster is None:
        raise ValueError(
            "scan_and_emit: session y broadcaster son requeridos cuando persist=True",
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

    return {**out, "id": sig_id, "persisted": True}


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


def _fmt_signal_label(signal: Any, blocked: Any, conf: Any) -> str:
    """Convierte el flag boolean `signal` del backend a label humano.

    BUG-024 cierre real: antes la f-string serializaba `True`/`False`
    crudo (ej. "score 0.0 (—) · False"), confuso para el usuario.
    """
    if blocked:
        return "BLOQUEADO"
    if signal is True or (isinstance(signal, str) and signal.upper() == "SETUP"):
        # Heuristic: REVISAR vs SETUP por la banda
        if conf in ("REVISAR", "B"):
            return "REVISAR"
        return "SETUP"
    return "NEUTRAL"


def build_chat_format(
    out: dict,
    *,
    candle_timestamp: _dt.datetime,
) -> str:
    """Template del `chat_format` — texto multilinea listo para pegar
    al chat con Claude.

    Bloques (en orden):
        1. HEADER  — ticker · dir · score (band) · LABEL
        2. PRECIO  — último cierre + ATR si disponibles (BUG-024)
        3. ESTADO  — bloqueo con motivo + conflict info (BUG-024)
        4. CONTEXTO — alignment + trends
        5. TRIGGERS / CONFIRMS / RISKS — listas con weight
        6. META — engine, fixture, candle ts
    """
    lines: list[str] = []
    ticker = out.get("ticker", "?")
    score = out.get("score")
    conf = out.get("conf", "—")
    dir_ = out.get("dir") or "—"
    blocked = out.get("blocked")
    label = _fmt_signal_label(out.get("signal"), blocked, conf)

    score_str = f"{score:.1f}" if isinstance(score, (int, float)) else "—"
    lines.append(f"[{ticker}] {dir_} · score {score_str} ({conf}) · {label}")
    lines.append(f"Candle: {candle_timestamp.isoformat()}")
    lines.append("")

    if out.get("error"):
        lines.append(f"ERROR: {out.get('error_code')}")
        return "\n".join(lines)

    # PRECIO — del bloque `ind` (BUG-024 cierre real: el usuario quiere
    # comparar con su gráfico, así que el precio es lo primero útil).
    ind = out.get("ind") or {}
    price = ind.get("price")
    if isinstance(price, (int, float)):
        lines.append(f"PRECIO  ${price:.2f}")
        atr15 = ind.get("atr_15m")
        if isinstance(atr15, (int, float)):
            atr_pct = (atr15 / price * 100.0) if price else 0.0
            lines.append(f"  ATR15M  {atr_pct:.2f}% (${atr15:.2f})")
        bb1h = ind.get("bb_1h")
        if isinstance(bb1h, list) and len(bb1h) == 3:
            lines.append(f"  BB1H    sup ${bb1h[0]:.2f} · mid ${bb1h[1]:.2f} · inf ${bb1h[2]:.2f}")
        bbd = ind.get("bb_daily")
        if isinstance(bbd, list) and len(bbd) == 3:
            lines.append(f"  BBD     sup ${bbd[0]:.2f} · mid ${bbd[1]:.2f} · inf ${bbd[2]:.2f}")
        lines.append("")

    # ESTADO — bloqueo + conflict info (BUG-024 cierre real).
    layers = out.get("layers") or {}
    risk = layers.get("risk") or {}
    if blocked:
        items = risk.get("items") or []
        if items:
            lines.append("BLOQUEO")
            for it in items[:5]:
                if isinstance(it, dict):
                    desc = it.get("desc") or it.get("reason") or it.get("name") or "?"
                    code = it.get("code") or it.get("error_code")
                    lines.append(f"  {desc}{' [' + code + ']' if code else ''}")
                else:
                    lines.append(f"  {it}")
        else:
            lines.append("BLOQUEO  (motivo no detallado en risk.items)")
        conflict = risk.get("conflictInfo") or {}
        if conflict:
            put = conflict.get("put")
            call = conflict.get("call")
            diff = conflict.get("diff")
            if put is not None and call is not None:
                lines.append(
                    f"  conflicto put/call: PUT {put} vs CALL {call}"
                    f"{f' · diff {diff}' if diff is not None else ''}",
                )
        lines.append("")

    # CONTEXTO
    aln = layers.get("alignment") or {}
    if aln:
        lines.append(
            f"CONTEXTO  {aln.get('dir', '?')} {aln.get('n', 0)}/3 alineados",
        )
    trends = layers.get("trends") or {}
    if trends:
        lines.append(
            f"  Trends   15M={trends.get('t15m', '?')} · "
            f"1H={trends.get('t1h', '?')} · D={trends.get('tdaily', '?')}",
        )
    if aln or trends:
        lines.append("")

    # TRIGGERS / CONFIRMS / RISKS
    triggers = [p for p in out.get("patterns") or [] if p.get("cat") == "TRIGGER"]
    if triggers:
        lines.append("TRIGGERS")
        for t in triggers[:8]:
            lines.append(f"  {t.get('d', '?')}  (+{t.get('w', 0)})")
        lines.append("")

    confirm_items = (layers.get("confirm") or {}).get("items") or []
    if confirm_items:
        lines.append("CONFIRMS")
        for c in confirm_items[:8]:
            lines.append(f"  {c.get('desc', '?')}  (+{c.get('weight', 0)})")
        lines.append("")

    risk_items = risk.get("items") or []
    if risk_items and not blocked:
        # Solo mostramos riesgos no-bloqueantes acá (los bloqueantes
        # ya salieron en el bloque ESTADO arriba).
        lines.append("RIESGOS")
        for r in risk_items[:5]:
            if isinstance(r, dict):
                desc = r.get("desc") or r.get("reason") or "?"
                lines.append(f"  {desc}")
        lines.append("")

    # META
    fid = out.get("fixture_id", "—")
    fver = out.get("fixture_version") or ""
    eng = out.get("engine_version", "—")
    lines.append("─" * 40)
    lines.append(
        f"Fixture: {fid}{' v' + fver if fver else ''} · Engine: {eng}",
    )
    return "\n".join(lines).rstrip()
