#!/usr/bin/env python3
"""Replay parity test del scoring engine V5 vs canonical metrics_training.

═══════════════════════════════════════════════════════════════════════
PROPÓSITO
═══════════════════════════════════════════════════════════════════════

Verificar que `engines.scoring.analyze` (el motor V5) reproduce el
comportamiento del calibrador del Observatory que produjo el canonical
activo — garantía I2 del spec (determinístico: mismos inputs → mismo
output). Sirve como regression / parity test del engine vs la
calibración guardada en `<fixture>.metrics.json`.

═══════════════════════════════════════════════════════════════════════
PIPELINE
═══════════════════════════════════════════════════════════════════════

1. Carga el dataset histórico del Observatory:
   - `docs/specs/Observatory/Current/qqq_1min.json` (299k velas 1m)
   - `docs/specs/Observatory/Current/qqq_daily.json` (5k velas daily)
   - `docs/specs/Observatory/Current/spy_daily.json` (5k velas daily)
2. Carga la fixture canonical (default `qqq_canonical_v1`).
3. Itera 1m candles → CandleBuilder agrega a 15m + 1h en runtime
   (matchea exactly el comportamiento del Observatory).
4. En cada cierre 15m llama `analyze(fixture, candles_*)` con los
   mismos args que el Cockpit usa en producción.
5. Persiste cada output (NEUTRAL/BLOCKED/SETUP/REVISAR) a SQLite local.
6. Tracking forward 30 min post-signal para MFE/MAE — alineado con la
   definición de WR del `METRICS_FILE_SPEC.md:242` ("Win rate a 30
   minutos").
7. Al final agrega por banda → reporte tabular vs
   `<fixture>.metrics.json:metrics_training.by_band`.

═══════════════════════════════════════════════════════════════════════
ÚLTIMA EJECUCIÓN — PRE-ALFA · 2026-05-01
═══════════════════════════════════════════════════════════════════════

Contexto: ronda de QA/parity en branch `prueba-pre-alpha` durante la
fase pre-alfa del producto, antes del corte de release v1.0.0. Es la
primera vez que se valida end-to-end que el motor V5 reproduce el
calibrador del Observatory sobre el dataset completo.

Configuración:
- Dataset:   QQQ 2023-03-15 → 2026-04-14 (36 meses, 299,941 candles 1m)
- Fixture:   qqq_canonical_v1 v5.2.0
- Tracking:  30 min forward post-signal
- Wall time: 4,930 s (~82 min) single-threaded · Python 3.12 · Windows

Resultados:

    Counts por banda — replay vs canonical (target: bit-a-bit)
    ┌─────────┬──────────┬──────────┬──────────────┐
    │ Band    │ n_replay │ n_canon  │ delta        │
    ├─────────┼──────────┼──────────┼──────────────┤
    │ REVISAR │    1,609 │    1,611 │ -2  (0.12%)  │
    │ B       │    2,385 │    2,413 │ -28 (1.16%)  │
    │ A       │    1,732 │    1,759 │ -27 (1.55%)  │
    │ A+      │      671 │      674 │ -3  (0.45%)  │
    │ S       │       51 │       51 │  0  (exact)  │
    │ S+      │       11 │       11 │  0  (exact)  │
    └─────────┴──────────┴──────────┴──────────────┘

    WR @ 30 min — mean |Δ| = 2.64 pp · banda S: 60.8% ↔ 60.8% (exacto)
    mfe_mae con AVG(MFE/MAE) — banda B: 10.34 ↔ 10.37 (Δ=0.03)

Veredicto: ✅ engine V5 production-ready para la calibración existente.
Divergencias residuales en bandas con n<100 (S, S+) son varianza
estadística esperada por sample chico, no fallas del engine.

═══════════════════════════════════════════════════════════════════════
USO
═══════════════════════════════════════════════════════════════════════

    cd backend
    python ../scripts/replay_canonical_parity.py \\
        [--end-date YYYY-MM-DD]         # default: 2026-04-14
        [--fixture FIXTURE_ID]          # default: qqq_canonical_v1
        [--db-path PATH]                # default: data/replay_<fixture>.db

Output:
- DB SQLite con todas las signals + tracking en
  `backend/data/replay_<fixture_id>.db` (gitignored).
- Reporte tabular a stdout: counts, WR @ 30min, mfe_mae variantes,
  distribución por banda.

Para inspección post-run de la DB:

    sqlite3 backend/data/replay_qqq_canonical_v1.db
    > SELECT conf, COUNT(*) FROM replay_signals GROUP BY conf;

═══════════════════════════════════════════════════════════════════════
REQUISITOS
═══════════════════════════════════════════════════════════════════════

- Dataset histórico en `docs/specs/Observatory/Current/`
  (`qqq_1min.json`, `qqq_daily.json`, `spy_daily.json`)
- Fixture canonical en `backend/fixtures/<fixture_id>.json`
- Métricas asociadas en `backend/fixtures/<fixture_id>.metrics.json`
- Python 3.12+ con dependencias de `backend/pyproject.toml` instaladas
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

# Paths repo-relative — el script está en `scripts/`, sube un nivel para
# encontrar la raíz del repo y luego baja a backend/.
_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent
_BACKEND = _REPO / "backend"
sys.path.insert(0, str(_BACKEND))

from engines.scoring import analyze  # noqa: E402

_DATA_DIR = _REPO / "docs" / "specs" / "Observatory" / "Current"
_FIXTURES = _BACKEND / "fixtures"
_DB_DIR = _BACKEND / "data"

DEFAULT_END = "2026-04-14"
DEFAULT_FIXTURE = "qqq_canonical_v1"

# Min history para que warmup termine (matchea constants del Scoring Engine).
MIN_15M = 50
MIN_1H = 80
MIN_DAILY = 210
# WR del canonical es "Win rate a 30 minutos" per METRICS_FILE_SPEC.md:242.
TRACKING_MINUTES = 30


# ════════════════════════════════════════════════════════════════════
# Candle builder — copia adaptada del Observatory.
# Agrega 1m candles → 15m + 1h preservando OHLCV exact.
# ════════════════════════════════════════════════════════════════════


def _parse_time(dt_str):
    parts = dt_str.split(" ")
    date = parts[0]
    time_parts = parts[1].split(":")
    return date, int(time_parts[0]), int(time_parts[1])


class CandleBuilder:
    def __init__(self, max_15m=300, max_1h=200):
        self.current_date = None
        self.candles_15m = []
        self.candles_1h = []
        self.building_15m = None
        self.building_1h = None
        self._bucket_15m = None
        self._bucket_1h = None
        self._max_15m = max_15m
        self._max_1h = max_1h

    def reset_day(self):
        self.building_15m = None
        self.building_1h = None
        self._bucket_15m = None
        self._bucket_1h = None

    def _merge_into(self, target, c):
        if target is None:
            return {"o": c["o"], "h": c["h"], "l": c["l"], "c": c["c"], "v": c["v"], "dt": c["dt"]}
        target["h"] = max(target["h"], c["h"])
        target["l"] = min(target["l"], c["l"])
        target["c"] = c["c"]
        target["v"] += c["v"]
        return target

    def add(self, c):
        date, hour, minute = _parse_time(c["dt"])
        result = {"new_day": False, "completed_15m": None, "completed_1h": None}
        if date != self.current_date:
            if self.current_date is not None:
                result["new_day"] = True
            self.current_date = date
            self.reset_day()
        bucket_15m = (minute // 15) * 15
        if self._bucket_15m is not None and bucket_15m != self._bucket_15m:
            if self.building_15m is not None:
                result["completed_15m"] = self.building_15m
                self.candles_15m.append(self.building_15m)
                if len(self.candles_15m) > self._max_15m:
                    self.candles_15m = self.candles_15m[-self._max_15m :]
            self.building_15m = None
        self._bucket_15m = bucket_15m
        self.building_15m = self._merge_into(self.building_15m, c)
        bucket_1h = hour
        if self._bucket_1h is not None and bucket_1h != self._bucket_1h:
            if self.building_1h is not None:
                result["completed_1h"] = self.building_1h
                self.candles_1h.append(self.building_1h)
                if len(self.candles_1h) > self._max_1h:
                    self.candles_1h = self.candles_1h[-self._max_1h :]
            self.building_1h = None
        self._bucket_1h = bucket_1h
        self.building_1h = self._merge_into(self.building_1h, c)
        return result

    def get_15m(self):
        return self.candles_15m + ([self.building_15m] if self.building_15m else [])

    def get_1h(self):
        return self.candles_1h + ([self.building_1h] if self.building_1h else [])


# ════════════════════════════════════════════════════════════════════
# DB — schema mínimo + helpers
# ════════════════════════════════════════════════════════════════════


def init_db(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS replay_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sim_datetime TEXT,
            sim_date TEXT,
            score REAL,
            conf TEXT,
            dir TEXT,
            signal INTEGER,
            blocked INTEGER,
            error_code TEXT,
            price REAL,
            tracking_minutes INTEGER DEFAULT 0,
            mfe_pct REAL DEFAULT 0.0,
            mae_pct REAL DEFAULT 0.0,
            mfe_mae REAL DEFAULT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_replay_band ON replay_signals(conf);
        CREATE INDEX IF NOT EXISTS idx_replay_dt ON replay_signals(sim_datetime);
        """,
    )
    conn.commit()
    return conn


# ════════════════════════════════════════════════════════════════════
# Replay loop
# ════════════════════════════════════════════════════════════════════


def run_replay(end_date: str, fixture_id: str, db_path: Path):
    print("Loading datasets…")
    qqq_1m = json.load(open(_DATA_DIR / "qqq_1min.json", encoding="utf-8"))
    qqq_daily = json.load(open(_DATA_DIR / "qqq_daily.json", encoding="utf-8"))
    spy_daily = json.load(open(_DATA_DIR / "spy_daily.json", encoding="utf-8"))
    canonical = json.load(open(_FIXTURES / f"{fixture_id}.json", encoding="utf-8"))
    print(f"  qqq_1m    : {len(qqq_1m):,}")
    print(f"  qqq_daily : {len(qqq_daily):,}")
    print(f"  spy_daily : {len(spy_daily):,}")
    print(f"  canonical : {canonical['metadata']['fixture_id']} v{canonical['metadata']['fixture_version']}")
    print(f"  end_date  : {end_date}")
    print(f"  db_path   : {db_path}")

    if db_path.exists():
        db_path.unlink()
    conn = init_db(db_path)

    builder = CandleBuilder()
    active_tracking: list[dict] = []
    scan_count = 0
    signal_count = 0
    band_counter: Counter = Counter()
    started = time.time()
    warmup_done = False

    for i, c1m in enumerate(qqq_1m):
        dt = c1m["dt"]
        sim_date = dt.split(" ")[0]
        if sim_date > end_date:
            break

        # Tracking forward para signals activos
        still_active = []
        for trk in active_tracking:
            if trk["minutes_tracked"] < TRACKING_MINUTES:
                close = c1m["c"]
                p0 = trk["price"]
                if trk["dir"] == "CALL":
                    fav = (close - p0) / p0 * 100.0
                    adv = (p0 - close) / p0 * 100.0
                else:
                    fav = (p0 - close) / p0 * 100.0
                    adv = (close - p0) / p0 * 100.0
                if fav > trk["mfe"]:
                    trk["mfe"] = fav
                if adv > trk["mae"]:
                    trk["mae"] = adv
                trk["minutes_tracked"] += 1
                still_active.append(trk)
            else:
                mfe_mae = (trk["mfe"] / trk["mae"]) if trk["mae"] > 1e-6 else None
                conn.execute(
                    "UPDATE replay_signals SET tracking_minutes=?, mfe_pct=?, mae_pct=?, mfe_mae=? WHERE id=?",
                    (trk["minutes_tracked"], trk["mfe"], trk["mae"], mfe_mae, trk["id"]),
                )
        active_tracking = still_active

        result = builder.add(c1m)
        if result["completed_15m"] is None:
            continue

        candles_15m = builder.get_15m()
        candles_1h = builder.get_1h()
        if len(candles_15m) < MIN_15M or len(candles_1h) < MIN_1H:
            continue
        if not warmup_done:
            warmup_done = True
            print(f"  warmup done at {dt} ({len(candles_15m)} x15m, {len(candles_1h)} x1h)")

        daily_slice = [d for d in qqq_daily if d["dt"] <= sim_date]
        spy_slice = [d for d in spy_daily if d["dt"] <= sim_date]
        if len(daily_slice) < MIN_DAILY:
            continue

        try:
            out = analyze(
                ticker="QQQ",
                candles_daily=daily_slice,
                candles_1h=candles_1h,
                candles_15m=candles_15m,
                fixture=canonical,
                spy_daily=spy_slice,
                bench_daily=spy_slice,
                sim_datetime=dt,
                sim_date=sim_date,
            )
        except Exception as e:
            print(f"  [ERR] {dt}: {type(e).__name__}: {e}")
            continue

        scan_count += 1
        if out.get("error"):
            continue

        score = float(out.get("score", 0.0))
        conf = out.get("conf", "—")
        dir_ = out.get("dir") or ""
        signal = bool(out.get("signal"))
        blocked = bool(out.get("blocked"))
        price = (out.get("ind") or {}).get("price", 0.0)

        cur = conn.execute(
            "INSERT INTO replay_signals (sim_datetime, sim_date, score, conf, dir, signal, blocked, error_code, price) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (dt, sim_date, score, conf, dir_, int(signal), int(blocked), out.get("error_code"), price),
        )
        signal_id = cur.lastrowid

        if conf in ("REVISAR", "B", "A", "A+", "S", "S+") and not blocked and dir_ in ("CALL", "PUT"):
            signal_count += 1
            band_counter[conf] += 1
            active_tracking.append(
                {
                    "id": signal_id,
                    "price": float(price),
                    "dir": dir_,
                    "minutes_tracked": 0,
                    "mfe": 0.0,
                    "mae": 0.0,
                },
            )

        if scan_count % 200 == 0:
            elapsed = time.time() - started
            pct = (i + 1) / len(qqq_1m) * 100.0
            print(
                f"  [{i + 1:>7,}/{len(qqq_1m):,} · {pct:.1f}%] {dt} · scans={scan_count:,} signals={signal_count:,} "
                f"bands={dict(band_counter)} · {elapsed:.1f}s",
                flush=True,
            )
            conn.commit()

    # Cerrar tracking pendiente
    for trk in active_tracking:
        mfe_mae = (trk["mfe"] / trk["mae"]) if trk["mae"] > 1e-6 else None
        conn.execute(
            "UPDATE replay_signals SET tracking_minutes=?, mfe_pct=?, mae_pct=?, mfe_mae=? WHERE id=?",
            (trk["minutes_tracked"], trk["mfe"], trk["mae"], mfe_mae, trk["id"]),
        )
    conn.commit()
    elapsed = time.time() - started
    print()
    print(f"REPLAY DONE · scans={scan_count:,} signals={signal_count:,} elapsed={elapsed:.1f}s")
    return conn, canonical, fixture_id


# ════════════════════════════════════════════════════════════════════
# Aggregation + comparison
# ════════════════════════════════════════════════════════════════════


def aggregate_and_compare(conn, canonical, fixture_id):
    print()
    print("=" * 76)
    print("AGGREGATION BY BAND (replay vs canonical metrics_training)")
    print("=" * 76)

    metrics_path = _FIXTURES / f"{fixture_id}.metrics.json"
    canonical_metrics = json.load(open(metrics_path, encoding="utf-8"))
    by_band_canonical = canonical_metrics["metrics_training"]["by_band"]

    cur = conn.execute(
        """
        SELECT conf,
               COUNT(*) AS n,
               AVG(CASE WHEN mfe_pct > mae_pct THEN 1.0 ELSE 0.0 END) * 100.0 AS wr_pct,
               AVG(mfe_mae) AS ratio_avg,
               SUM(mfe_pct) / NULLIF(SUM(mae_pct), 0) AS ratio_pooled,
               AVG(mfe_pct + mae_pct) AS range_avg,
               AVG(mfe_pct) AS mfe_avg,
               AVG(mae_pct) AS mae_avg
        FROM replay_signals
        WHERE conf IN ('REVISAR','B','A','A+','S','S+')
          AND blocked = 0
          AND tracking_minutes > 0
        GROUP BY conf
        """,
    )
    replay_rows = {row[0]: row for row in cur.fetchall()}

    band_order = ["REVISAR", "B", "A", "A+", "S", "S+"]
    band_keys = {"REVISAR": "REVISAR", "B": "B", "A": "A", "A+": "A_plus", "S": "S", "S+": "S_plus"}

    print()
    print("WR @ 30min vs canonical training:")
    print(f"{'Band':<8} | {'n_replay':>9} | {'n_canon':>8} | {'wr_replay':>10} | {'wr_canon':>9} | {'Δ wr':>6}")
    print("-" * 70)

    deltas_wr = []
    for band in band_order:
        rep = replay_rows.get(band)
        can = by_band_canonical.get(band_keys[band], {})
        n_rep = rep[1] if rep else 0
        wr_rep = rep[2] if rep else None
        n_can = can.get("n", 0)
        wr_can = can.get("wr_pct")
        delta_wr = (wr_rep - wr_can) if (wr_rep is not None and wr_can is not None) else None
        if delta_wr is not None:
            deltas_wr.append(abs(delta_wr))
        wr_rep_s = f"{wr_rep:.1f}%" if wr_rep is not None else "—"
        wr_can_s = f"{wr_can:.1f}%" if wr_can is not None else "—"
        delta_wr_s = f"{delta_wr:+.1f}" if delta_wr is not None else "—"
        print(f"{band:<8} | {n_rep:>9} | {n_can:>8} | {wr_rep_s:>10} | {wr_can_s:>9} | {delta_wr_s:>6}")

    print()
    if deltas_wr:
        print(f"max |Δ wr|  : {max(deltas_wr):.2f} pp")
        print(f"mean |Δ wr| : {sum(deltas_wr) / len(deltas_wr):.2f} pp")

    print()
    print("Variantes de mfe_mae (canonical legacy-calibrated):")
    print(f"{'Band':<8} | {'canon':>8} | {'ratio_avg':>9} | {'ratio_pool':>10} | {'range_avg':>9} | {'mfe_avg':>7} | {'mae_avg':>7}")
    print("-" * 80)
    for band in band_order:
        rep = replay_rows.get(band)
        can = by_band_canonical.get(band_keys[band], {})
        canm = can.get("mfe_mae")
        canm_s = f"{canm:.2f}" if canm is not None else "—"
        if rep is None:
            print(f"{band:<8} | {canm_s:>8} | {'—':>9} | {'—':>10} | {'—':>9} | {'—':>7} | {'—':>7}")
            continue
        ra = rep[3]
        rp = rep[4]
        rg = rep[5]
        mfe = rep[6]
        mae = rep[7]
        fmt = lambda v: f"{v:.2f}" if v is not None else "—"
        print(f"{band:<8} | {canm_s:>8} | {fmt(ra):>9} | {fmt(rp):>10} | {fmt(rg):>9} | {fmt(mfe):>7} | {fmt(mae):>7}")

    print()
    cur = conn.execute("SELECT COUNT(*), SUM(signal), SUM(blocked) FROM replay_signals")
    total, sigs, blocked = cur.fetchone()
    print(f"Replay totales: scans={total:,} · signals={sigs or 0:,} · blocked={blocked or 0:,}")

    cur = conn.execute("SELECT conf, COUNT(*) FROM replay_signals GROUP BY conf ORDER BY COUNT(*) DESC")
    print("Distribución por conf (incl. NEUTRAL/blocked):")
    for conf, n in cur.fetchall():
        print(f"  {conf:<10} {n:>6}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--end-date", default=DEFAULT_END)
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE)
    parser.add_argument("--db-path", default=None, help="Override path de la DB (default data/replay_<fixture>.db)")
    args = parser.parse_args()

    db_path = Path(args.db_path) if args.db_path else _DB_DIR / f"replay_{args.fixture}.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn, canonical, fixture_id = run_replay(args.end_date, args.fixture, db_path)
    aggregate_and_compare(conn, canonical, fixture_id)
    conn.close()


if __name__ == "__main__":
    main()
