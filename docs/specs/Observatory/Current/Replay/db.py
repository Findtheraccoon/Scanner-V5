"""
Signal Observatory — Database Module
SQLite schema + insert/query helpers for all 7 tables.
"""
import sqlite3
import json
import os

DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "observatory.db")


def get_connection(db_path=None):
    conn = sqlite3.connect(db_path or DEFAULT_DB)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(conn):
    """Create all tables and indices."""
    conn.executescript("""

    CREATE TABLE IF NOT EXISTS sessions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        date            TEXT NOT NULL UNIQUE,
        open_price      REAL,
        prev_close      REAL,
        notes           TEXT
    );

    CREATE TABLE IF NOT EXISTS signals (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id          INTEGER NOT NULL REFERENCES sessions(id),
        timestamp           TEXT NOT NULL,
        ticker              TEXT NOT NULL,
        price_at_signal     REAL NOT NULL,
        direction           TEXT NOT NULL,
        score               REAL NOT NULL,
        confidence          TEXT NOT NULL,
        alignment_n         INTEGER,
        alignment_dir       TEXT,
        trend_15m           TEXT,
        trend_1h            TEXT,
        trend_daily         TEXT,
        structure_pass      INTEGER,
        structure_override  INTEGER,
        vol_mult            REAL,
        time_mult           REAL,
        time_zone           TEXT,
        trigger_count       INTEGER,
        trigger_sum         REAL,
        confirm_sum         REAL,
        bonus               INTEGER,
        risk_sum            REAL,
        conflict_blocked    INTEGER,
        needs_catalyst      INTEGER,
        catalyst_threshold  REAL
    );
    CREATE INDEX IF NOT EXISTS idx_signals_session ON signals(session_id);
    CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker);
    CREATE INDEX IF NOT EXISTS idx_signals_score ON signals(score);
    CREATE INDEX IF NOT EXISTS idx_signals_conf ON signals(confidence);

    CREATE TABLE IF NOT EXISTS signal_components (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        signal_id   INTEGER NOT NULL REFERENCES signals(id),
        category    TEXT NOT NULL,
        timeframe   TEXT,
        description TEXT,
        direction   TEXT,
        weight      REAL,
        age         INTEGER,
        decay_applied INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_components_signal ON signal_components(signal_id);
    CREATE INDEX IF NOT EXISTS idx_components_cat ON signal_components(category);

    CREATE TABLE IF NOT EXISTS signal_indicators (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        signal_id       INTEGER NOT NULL UNIQUE REFERENCES signals(id),
        ma20_d          REAL, ma40_d      REAL, ma200_d     REAL,
        ma20_h          REAL, ma40_h      REAL,
        ma20_m          REAL,
        bb_1h_upper     REAL, bb_1h_mid   REAL, bb_1h_lower REAL,
        bb_d_upper      REAL, bb_d_lower  REAL,
        bb_squeeze_1h   INTEGER,
        bb_expanding    INTEGER,
        atr             REAL, atr_pct     REAL,
        dma200          REAL,
        vol_15m         REAL, vol_1h      REAL,
        vol_projected   REAL,
        vol_seq_growing INTEGER,
        vol_seq_declining INTEGER,
        gap_pct         REAL, gap_significant INTEGER,
        orb_high        REAL, orb_low     REAL,
        orb_break_up    INTEGER, orb_break_down INTEGER,
        div_spy         INTEGER,
        fza_rel         REAL
    );

    CREATE TABLE IF NOT EXISTS signal_levels (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        signal_id       INTEGER NOT NULL REFERENCES signals(id),
        level_type      TEXT NOT NULL,
        price           REAL NOT NULL,
        label           TEXT,
        distance_pct    REAL
    );
    CREATE INDEX IF NOT EXISTS idx_levels_signal ON signal_levels(signal_id);

    CREATE TABLE IF NOT EXISTS price_tracking (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        signal_id       INTEGER NOT NULL REFERENCES signals(id),
        offset_min      INTEGER NOT NULL,
        price           REAL NOT NULL,
        volume          INTEGER,
        change_pct      REAL,
        max_favorable   REAL,
        max_adverse     REAL
    );
    CREATE INDEX IF NOT EXISTS idx_tracking_signal ON price_tracking(signal_id);
    CREATE INDEX IF NOT EXISTS idx_tracking_offset ON price_tracking(signal_id, offset_min);

    CREATE TABLE IF NOT EXISTS scan_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id      INTEGER NOT NULL REFERENCES sessions(id),
        timestamp       TEXT NOT NULL,
        ticker          TEXT NOT NULL,
        price           REAL,
        score           REAL,
        confidence      TEXT,
        direction       TEXT,
        signal_generated INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_scanlog_session ON scan_log(session_id);
    """)
    conn.commit()


# ═══════════════════════════════════════
# INSERT HELPERS
# ═══════════════════════════════════════

def insert_session(conn, date, open_price=None, prev_close=None):
    """Insert or get existing session. Returns session_id."""
    row = conn.execute("SELECT id FROM sessions WHERE date=?", (date,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO sessions (date, open_price, prev_close) VALUES (?,?,?)",
        (date, open_price, prev_close)
    )
    conn.commit()
    return cur.lastrowid


def insert_scan_log(conn, session_id, timestamp, ticker, price, score, confidence, direction, signal_generated):
    """Log every scanner run."""
    conn.execute(
        "INSERT INTO scan_log (session_id, timestamp, ticker, price, score, confidence, direction, signal_generated) VALUES (?,?,?,?,?,?,?,?)",
        (session_id, timestamp, ticker, price, score, confidence, direction, int(signal_generated))
    )


def insert_signal(conn, session_id, result, timestamp, ticker):
    """
    Insert a full signal snapshot from scanner result.
    Returns signal_id.
    """
    s = result["scoring"]
    ind = result["ind"]
    layers = s["layers"]

    cur = conn.execute("""
        INSERT INTO signals (
            session_id, timestamp, ticker, price_at_signal, direction,
            score, confidence, alignment_n, alignment_dir,
            trend_15m, trend_1h, trend_daily,
            structure_pass, structure_override,
            vol_mult, time_mult, time_zone,
            trigger_count, trigger_sum, confirm_sum, bonus, risk_sum,
            conflict_blocked, needs_catalyst, catalyst_threshold
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        session_id, timestamp, ticker, ind["price"], s.get("dir"),
        s["score"], s["conf"], result["aln"]["n"], result["aln"]["dir"],
        result["tM"], result["tH"], result["tD"],
        int(layers["structure"]["pass"]), int(layers["structure"]["override"]),
        layers["confirm"]["volMult"], s["timeW"]["w"], s["timeW"]["zone"],
        layers["trigger"]["count"], layers["trigger"]["sum"],
        layers["confirm"]["sum"], layers["confirm"].get("bonus", 0),
        layers["risk"]["sum"],
        int(layers["risk"]["blocked"]),
        int(result["needsCat"]), result["catThreshold"],
    ))
    signal_id = cur.lastrowid

    # ─── Components ───
    for p in result["patterns"]:
        conn.execute("""
            INSERT INTO signal_components (signal_id, category, timeframe, description, direction, weight, age, decay_applied)
            VALUES (?,?,?,?,?,?,?,?)
        """, (signal_id, p["cat"], p["tf"], p["d"], p["sg"], p["w"], p["age"], int(p["age"] > 1)))

    # ─── Indicators ───
    conn.execute("""
        INSERT INTO signal_indicators (
            signal_id, ma20_d, ma40_d, ma200_d, ma20_h, ma40_h, ma20_m,
            bb_1h_upper, bb_1h_mid, bb_1h_lower, bb_d_upper, bb_d_lower,
            bb_squeeze_1h, bb_expanding, atr, atr_pct, dma200,
            vol_15m, vol_1h, vol_projected,
            vol_seq_growing, vol_seq_declining,
            gap_pct, gap_significant,
            orb_high, orb_low, orb_break_up, orb_break_down,
            div_spy, fza_rel
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        signal_id,
        ind["ma20D"], ind["ma40D"], ind["ma200D"],
        ind["ma20H"], ind["ma40H"], ind["ma20M"],
        ind["bbH"]["u"] if ind["bbH"] else None,
        ind["bbH"]["m"] if ind["bbH"] else None,
        ind["bbH"]["l"] if ind["bbH"] else None,
        ind["bbD"]["u"] if ind["bbD"] else None,
        ind["bbD"]["l"] if ind["bbD"] else None,
        int(ind["bbSqH"]["isSqueeze"]) if ind["bbSqH"] else None,
        int(ind["bbSqH"]["isExpanding"]) if ind["bbSqH"] else None,
        ind["atr"], ind["atrPct"], ind["dMA200"],
        ind["volM"], ind["volH"],
        ind["volProjM"]["projected"] if ind["volProjM"] else None,
        int(ind["volSeqM"]["growing"]),
        int(ind["volSeqM"]["declining"]),
        ind["gap"]["pct"] if ind["gap"] else None,
        int(ind["gap"]["significant"]) if ind["gap"] else None,
        ind["orb"]["high"] if ind["orb"] else None,
        ind["orb"]["low"] if ind["orb"] else None,
        int(ind["orb"]["breakUp"]) if ind["orb"] else None,
        int(ind["orb"]["breakDown"]) if ind["orb"] else None,
        int(result["divSPY"] is not None),
        result["secRel"]["diff"] if result["secRel"] else None,
    ))

    # ─── Key Levels ───
    for lv in result["kLvls"]["r"]:
        dist = round(abs(ind["price"] - lv["p"]) / lv["p"] * 100, 3) if lv["p"] > 0 else 0
        conn.execute(
            "INSERT INTO signal_levels (signal_id, level_type, price, label, distance_pct) VALUES (?,?,?,?,?)",
            (signal_id, "R", lv["p"], lv["l"], dist)
        )
    for lv in result["kLvls"]["s"]:
        dist = round(abs(ind["price"] - lv["p"]) / lv["p"] * 100, 3) if lv["p"] > 0 else 0
        conn.execute(
            "INSERT INTO signal_levels (signal_id, level_type, price, label, distance_pct) VALUES (?,?,?,?,?)",
            (signal_id, "S", lv["p"], lv["l"], dist)
        )

    conn.commit()
    return signal_id


def insert_price_tracking(conn, signal_id, offset_min, price, volume,
                          price_at_signal, direction, prev_max_fav, prev_max_adv):
    """
    Insert one minute of price tracking.
    Returns (max_favorable, max_adverse) updated.
    """
    change_pct = round((price - price_at_signal) / price_at_signal * 100, 4)

    # Favorable = move in signal direction, adverse = against
    if direction == "CALL":
        favorable = max(0, change_pct)
        adverse = min(0, change_pct)
    else:  # PUT
        favorable = max(0, -change_pct)
        adverse = min(0, -change_pct)

    max_fav = max(prev_max_fav, favorable)
    max_adv = min(prev_max_adv, adverse)

    conn.execute("""
        INSERT INTO price_tracking (signal_id, offset_min, price, volume, change_pct, max_favorable, max_adverse)
        VALUES (?,?,?,?,?,?,?)
    """, (signal_id, offset_min, price, volume, change_pct, max_fav, max_adv))

    return max_fav, max_adv
