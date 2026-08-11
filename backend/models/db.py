"""SQLite persistence for call history: sessions, turns, latency metrics.

Uses the stdlib `sqlite3` module - no extra dependency, keeps the app fully
offline. Every write goes through `asyncio.to_thread`, so the event loop is
never blocked by disk I/O: the voice pipeline must not wait on the database.

Schema migration: additive only, and automatic. `_SCHEMA` creates missing
tables, `_ADDED_COLUMNS` adds missing columns. Both are idempotent, so an old
`app.db` upgrades in place on startup and nobody loses a contact list.

Why not numbered migrations: every change so far is "add a table" or "add a
column with a constant default", which converges to the same state no matter
what order it runs in. A version counter would only add a way to get it wrong.
Anything that needs to *transform* existing rows does need a real migration -
add it to `_DATA_MIGRATIONS` with its own guard.
"""

import asyncio
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.pipeline.session_manager import CallSession

logger = logging.getLogger(__name__)

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()  # sqlite3 connections are not safe for concurrent writes

_SCHEMA = """
CREATE TABLE IF NOT EXISTS call_sessions (
    session_id    TEXT PRIMARY KEY,
    customer_name TEXT NOT NULL DEFAULT '',
    product       TEXT NOT NULL DEFAULT '',
    voice_name    TEXT NOT NULL DEFAULT 'default',
    status        TEXT NOT NULL DEFAULT 'active',   -- active | ended
    turn_count    INTEGER NOT NULL DEFAULT 0,
    created_at    REAL NOT NULL,                    -- epoch seconds, time.time()
    ended_at      REAL
);

CREATE INDEX IF NOT EXISTS ix_sessions_created_at ON call_sessions(created_at DESC);

-- What the bot says and how: swappable per campaign so the same system can sell
-- insurance tomorrow without a code change. See services/llm_service.py for
-- which parts of the prompt a scenario may override and which are fixed.
CREATE TABLE IF NOT EXISTS scenarios (
    scenario_id      TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    industry         TEXT NOT NULL DEFAULT '',
    org_name         TEXT NOT NULL DEFAULT '',   -- replaces {bank_name}
    agent_name       TEXT NOT NULL DEFAULT '',   -- replaces {agent_name}
    opening_line     TEXT NOT NULL DEFAULT '',   -- spoken the moment the callee answers
    rules            TEXT NOT NULL DEFAULT '',   -- one extra rule per line
    examples         TEXT NOT NULL DEFAULT '',   -- JSON list of {khach, tu_van}
    knowledge_tag    TEXT NOT NULL DEFAULT '',   -- restrict RAG chunks to this tag
    max_turns        INTEGER NOT NULL DEFAULT 20,
    transfer_number  TEXT NOT NULL DEFAULT '',
    transfer_on      TEXT NOT NULL DEFAULT '',   -- JSON list of trigger names
    transfer_message TEXT NOT NULL DEFAULT '',
    direction        TEXT NOT NULL DEFAULT 'outbound',  -- outbound | inbound | both
    is_default       INTEGER NOT NULL DEFAULT 0,
    note             TEXT NOT NULL DEFAULT '',
    created_at       REAL NOT NULL
);

-- Kho cau dem theo tinh huong. La CAU HINH dung chung cho moi cuoc goi, nen
-- nam o app.db chu khong tach theo khach: tach ra la moi khach mot ban sao cua
-- cung mot thu, va nhan len dung tai nguyen dat nhat (GPU dung tieng moi giong).
CREATE TABLE IF NOT EXISTS tinh_huong (
    id         TEXT PRIMARY KEY,
    ten        TEXT NOT NULL,
    vi_du      TEXT NOT NULL,      -- JSON array: cau khach noi mau, de nhung
    tu_khoa    TEXT,               -- JSON array: loc tho / du phong
    mo_dau     TEXT,               -- JSON array: mau mo dau rieng
    speed      REAL,               -- NULL = lay toc cua giong
    bat        INTEGER NOT NULL DEFAULT 1,
    created_at REAL,
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS cau_duoi (
    id          TEXT PRIMARY KEY,
    text        TEXT NOT NULL,
    hop_cau_hoi INTEGER NOT NULL DEFAULT 1,
    bat         INTEGER NOT NULL DEFAULT 1,
    created_at  REAL,
    updated_at  REAL
);

-- Call outcome labels the operator sticks on a session by hand.
CREATE TABLE IF NOT EXISTS labels (
    label_id   TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    color      TEXT NOT NULL DEFAULT '#888888',
    sort_order INTEGER NOT NULL DEFAULT 0
);

-- Where end-of-call and end-of-day reports get pushed.
CREATE TABLE IF NOT EXISTS notify_channels (
    channel_id TEXT PRIMARY KEY,
    kind       TEXT NOT NULL DEFAULT 'telegram',
    name       TEXT NOT NULL,
    config     TEXT NOT NULL DEFAULT '',   -- JSON: {"token": ..., "chat_id": ...}
    events     TEXT NOT NULL DEFAULT '',   -- JSON list of event names
    enabled    INTEGER NOT NULL DEFAULT 1,
    last_error TEXT NOT NULL DEFAULT '',
    last_sent  REAL,
    created_at REAL NOT NULL
);

-- Excel/CSV/SQL the bot may consult during a call. Two very different modes -
-- see services/data_source_service.py.
CREATE TABLE IF NOT EXISTS data_sources (
    source_id   TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'excel',  -- excel | csv | sqlite | mysql | postgres
    config      TEXT NOT NULL DEFAULT '',       -- JSON: path / dsn / table / columns
    mode        TEXT NOT NULL DEFAULT 'rag',    -- rag | lookup
    lookup_key  TEXT NOT NULL DEFAULT '',
    knowledge_tag TEXT NOT NULL DEFAULT '',
    sync_at     REAL,
    row_count   INTEGER NOT NULL DEFAULT 0,
    last_error  TEXT NOT NULL DEFAULT '',
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_turns (
    session_id  TEXT NOT NULL REFERENCES call_sessions(session_id) ON DELETE CASCADE,
    turn_index  INTEGER NOT NULL,   -- position in CallSession.history
    role        TEXT NOT NULL,      -- user | assistant
    content     TEXT NOT NULL,
    recorded_at REAL NOT NULL,
    PRIMARY KEY (session_id, turn_index)
);

CREATE TABLE IF NOT EXISTS latency_metrics (
    session_id  TEXT NOT NULL REFERENCES call_sessions(session_id) ON DELETE CASCADE,
    turn_number INTEGER NOT NULL,
    timestamp   REAL NOT NULL,
    stt_ms      INTEGER,
    rag_ms      INTEGER,
    ttfa_ms     INTEGER,            -- NULL when TTS is unavailable
    total_ms    INTEGER,
    PRIMARY KEY (session_id, turn_number)
);

-- Calling hardware: the phone/gateway/modem the system dials through.
CREATE TABLE IF NOT EXISTS devices (
    device_id    TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    kind         TEXT NOT NULL DEFAULT 'phone_link',  -- phone_link | usb_modem | sip | audio
    address      TEXT NOT NULL DEFAULT '',   -- host:port, http url, COM port, MAC or SIP uri
    dial_url     TEXT NOT NULL DEFAULT '',   -- HTTP hook used to place a call, {number} placeholder
    phone_number TEXT NOT NULL DEFAULT '',   -- subscriber number attached to the device
    status       TEXT NOT NULL DEFAULT 'unknown',  -- online | offline | error | unknown
    is_default   INTEGER NOT NULL DEFAULT 0,
    note         TEXT NOT NULL DEFAULT '',
    last_error   TEXT NOT NULL DEFAULT '',
    last_seen    REAL,
    created_at   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    product     TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'draft',  -- draft | running | paused | done
    note        TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL
);

-- One row per phone number to call. `phone` is unique so a re-import updates
-- the existing row instead of creating a duplicate lead.
CREATE TABLE IF NOT EXISTS contacts (
    contact_id      TEXT PRIMARY KEY,
    phone           TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL DEFAULT '',
    product         TEXT NOT NULL DEFAULT '',
    campaign_id     TEXT REFERENCES campaigns(campaign_id) ON DELETE SET NULL,
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending | calling | done | no_answer | busy | refused | invalid | dnc
    attempts        INTEGER NOT NULL DEFAULT 0,
    note            TEXT NOT NULL DEFAULT '',
    last_called_at  REAL,
    last_session_id TEXT,
    created_at      REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_contacts_campaign ON contacts(campaign_id);
CREATE INDEX IF NOT EXISTS ix_contacts_status ON contacts(status);

CREATE TABLE IF NOT EXISTS call_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id TEXT NOT NULL REFERENCES contacts(contact_id) ON DELETE CASCADE,
    phone      TEXT NOT NULL,
    device_id  TEXT,
    session_id TEXT,
    status     TEXT NOT NULL,             -- dialed | failed | done | no_answer | busy | refused
    detail     TEXT NOT NULL DEFAULT '',
    started_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_attempts_contact ON call_attempts(contact_id, started_at DESC);
"""

# Indexes over columns that `_ADDED_COLUMNS` may have just created. Kept apart
# from `_SCHEMA` because CREATE INDEX fails on a column that does not exist yet,
# and on an old app.db the column only appears after the ALTER TABLE pass.
_INDEXES_AFTER_COLUMNS = """
CREATE INDEX IF NOT EXISTS ix_sessions_campaign ON call_sessions(campaign_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_sessions_label ON call_sessions(label);
CREATE INDEX IF NOT EXISTS ix_sessions_quality ON call_sessions(quality);
CREATE INDEX IF NOT EXISTS ix_sessions_outcome ON call_sessions(outcome);
CREATE INDEX IF NOT EXISTS ix_sessions_phone ON call_sessions(phone);
CREATE INDEX IF NOT EXISTS ix_contacts_retry ON contacts(next_retry_at)
    WHERE next_retry_at IS NOT NULL;
"""

# Columns added after the first release. Every entry must carry a CONSTANT
# default (SQLite rejects `ALTER TABLE ADD COLUMN` with a computed one) and must
# not be UNIQUE or a PRIMARY KEY.
#
# Deliberately no REFERENCES clauses here: with foreign_keys=ON, SQLite refuses
# to ADD COLUMN a foreign key unless its default is NULL, and the ids below are
# cleaned up in code anyway (deleting a scenario nulls it out of campaigns).
_ADDED_COLUMNS: dict[str, dict[str, str]] = {
    "call_sessions": {
        # where the call came from
        "campaign_id":     "TEXT NOT NULL DEFAULT ''",
        "contact_id":      "TEXT NOT NULL DEFAULT ''",
        "scenario_id":     "TEXT NOT NULL DEFAULT ''",
        "phone":           "TEXT NOT NULL DEFAULT ''",
        "direction":       "TEXT NOT NULL DEFAULT 'outbound'",   # outbound | inbound
        "caller_number":   "TEXT NOT NULL DEFAULT ''",           # inbound: who rang us
        # how it went
        "outcome":         "TEXT NOT NULL DEFAULT ''",   # answered|no_answer|busy|voicemail|failed
        "quality":         "TEXT NOT NULL DEFAULT ''",   # derived, see reports_db.derive_quality
        "label":           "TEXT NOT NULL DEFAULT ''",   # set by hand
        "gender":          "TEXT NOT NULL DEFAULT ''",   # male | female | unknown
        # artefacts
        "recording_path":  "TEXT NOT NULL DEFAULT ''",
        "recording_size":  "INTEGER NOT NULL DEFAULT 0",
        "summary":         "TEXT NOT NULL DEFAULT ''",
        "summary_json":    "TEXT NOT NULL DEFAULT ''",
        "suggested_label": "TEXT NOT NULL DEFAULT ''",
        "summarized_at":   "REAL",
        # handover to a human
        "transferred_to":  "TEXT NOT NULL DEFAULT ''",
        "transfer_reason": "TEXT NOT NULL DEFAULT ''",
    },
    "campaigns": {
        "scenario_id":     "TEXT NOT NULL DEFAULT ''",
        "voice_name":      "TEXT NOT NULL DEFAULT 'default'",
        "device_ids":      "TEXT NOT NULL DEFAULT ''",   # JSON list; empty = default device
        "concurrency":     "INTEGER NOT NULL DEFAULT 1",
        "started_at":      "REAL",
        "paused_at":       "REAL",
        # operator-defined column headings for contacts.field1..3
        "field1_label":    "TEXT NOT NULL DEFAULT ''",
        "field2_label":    "TEXT NOT NULL DEFAULT ''",
        "field3_label":    "TEXT NOT NULL DEFAULT ''",
        # retry policy
        "retry_no_answer": "INTEGER NOT NULL DEFAULT 1",
        "retry_busy":      "INTEGER NOT NULL DEFAULT 1",
        "retry_voicemail": "INTEGER NOT NULL DEFAULT 0",
        "retry_max":       "INTEGER NOT NULL DEFAULT 3",
        "retry_delay_min": "INTEGER NOT NULL DEFAULT 30",
        # schedule
        "start_date":      "TEXT NOT NULL DEFAULT ''",   # 'YYYY-MM-DD', empty = start now
        "end_date":        "TEXT NOT NULL DEFAULT ''",
        "call_windows":    "TEXT NOT NULL DEFAULT ''",   # JSON, see campaign_runner
        "timezone":        "TEXT NOT NULL DEFAULT 'Asia/Ho_Chi_Minh'",
        # behaviour
        "on_voicemail":    "TEXT NOT NULL DEFAULT 'hangup'",  # hangup | continue
        "detect_gender":   "INTEGER NOT NULL DEFAULT 1",
        "record_calls":    "INTEGER NOT NULL DEFAULT 1",
    },
    "contacts": {
        "field1":        "TEXT NOT NULL DEFAULT ''",
        "field2":        "TEXT NOT NULL DEFAULT ''",
        "field3":        "TEXT NOT NULL DEFAULT ''",
        "next_retry_at": "REAL",
        "retry_reason":  "TEXT NOT NULL DEFAULT ''",
    },
    "devices": {
        "inbound_enabled":     "INTEGER NOT NULL DEFAULT 0",
        "inbound_scenario_id": "TEXT NOT NULL DEFAULT ''",
        "inbound_delay_s":     "REAL NOT NULL DEFAULT 2.0",
    },
}

# Rows that need rewriting, not just new columns. Each entry is
# (guard SQL returning a count, statement to run when the count is non-zero).
# Empty for now - kept so the first real data migration has an obvious home.
_DATA_MIGRATIONS: list[tuple[str, str]] = []

# Once a session is marked ended it stays ended: a stray background write that
# lands after the disconnect flush must not resurrect it as active.
#
# Only columns the live CallSession owns are written here. Everything decided
# after the call - outcome, quality, label, recording path, summary - belongs to
# reports_db and must NOT be listed, or a late flush from the pipeline would
# blank out what the operator just set.
_SESSION_COLUMNS = (
    "session_id", "customer_name", "product", "voice_name", "status",
    "turn_count", "created_at", "ended_at",
    "campaign_id", "contact_id", "scenario_id", "phone", "direction",
    "caller_number", "gender",
)

_UPSERT_SESSION = f"""
INSERT INTO call_sessions ({", ".join(_SESSION_COLUMNS)})
VALUES ({", ".join("?" * len(_SESSION_COLUMNS))})
ON CONFLICT(session_id) DO UPDATE SET
    customer_name = excluded.customer_name,
    product       = excluded.product,
    voice_name    = excluded.voice_name,
    turn_count    = excluded.turn_count,
    status        = CASE WHEN call_sessions.status = 'ended'
                         THEN 'ended' ELSE excluded.status END,
    ended_at      = COALESCE(excluded.ended_at, call_sessions.ended_at),
    campaign_id   = excluded.campaign_id,
    contact_id    = excluded.contact_id,
    scenario_id   = excluded.scenario_id,
    phone         = excluded.phone,
    direction     = excluded.direction,
    caller_number = excluded.caller_number,
    -- gender is detected mid-call and then stays put: a later flush that has
    -- not run detection yet would otherwise wipe it back to ''.
    gender        = CASE WHEN excluded.gender != '' THEN excluded.gender
                         ELSE call_sessions.gender END
"""


# --- lifecycle ---------------------------------------------------------------

def _add_missing_columns(conn: sqlite3.Connection) -> list[str]:
    """Bring an existing database up to `_ADDED_COLUMNS`. Returns what it added."""
    added = []
    for table, columns in _ADDED_COLUMNS.items():
        existing = {
            r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if not existing:
            continue  # table itself is missing - _SCHEMA already declined to create it
        for name, decl in columns.items():
            if name in existing:
                continue
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
            added.append(f"{table}.{name}")
    return added


def _seed_default_labels(conn: sqlite3.Connection):
    """The three labels Điều 6 of the contract names, inserted once."""
    if conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0]:
        return
    conn.executemany(
        "INSERT INTO labels (label_id, name, color, sort_order) VALUES (?, ?, ?, ?)",
        [
            ("quan_tam", "Quan tâm", "#22c55e", 1),
            ("khong_quan_tam", "Không quan tâm", "#ef4444", 2),
            ("follow", "Follow chăm sóc thêm", "#f59e0b", 3),
        ],
    )


def _init_sync(db_path: Path):
    global _conn

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL")     # readers don't block the writer
    conn.execute("PRAGMA synchronous=NORMAL")   # survives process death; only a
                                                # sudden power loss can drop the
                                                # last commit
    conn.execute("PRAGMA foreign_keys=ON")

    with conn:
        conn.executescript(_SCHEMA)
        # Order matters: columns first, then the indexes that sit on them, then
        # anything that rewrites rows.
        added = _add_missing_columns(conn)
        conn.executescript(_INDEXES_AFTER_COLUMNS)
        for guard, statement in _DATA_MIGRATIONS:
            if conn.execute(guard).fetchone()[0]:
                conn.execute(statement)
        _seed_default_labels(conn)

        # Nothing can be live at startup, so any session still flagged active is
        # a leftover from a kill -9 during a previous run.
        cur = conn.execute(
            "UPDATE call_sessions SET status='ended', ended_at=created_at "
            "WHERE status='active'"
        )
        recovered = cur.rowcount

        # Same reasoning for the dialer: a contact can only be 'calling' while
        # the process that dialled it is alive.
        conn.execute("UPDATE contacts SET status='pending' WHERE status='calling'")
        conn.execute("UPDATE devices SET status='unknown' WHERE status='online'")
        # A campaign cannot be running either - the runner task died with the
        # process. Leave it paused so the operator decides whether to resume.
        conn.execute("UPDATE campaigns SET status='paused' WHERE status='running'")

    _conn = conn
    return recovered, added


async def init_db(db_path: str | Path):
    """Open the database, apply the schema, clean up sessions left by a crash."""
    path = Path(db_path)
    recovered, added = await asyncio.to_thread(_init_sync, path)
    logger.info(f"  Database: {path}")
    if added:
        logger.info(f"  Schema updated: added {len(added)} column(s) - {', '.join(added)}")
    if recovered:
        logger.info(f"  Recovered {recovered} session(s) left active by a previous crash")


def _close_sync():
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


async def close_db():
    await asyncio.to_thread(_close_sync)


# --- shared access for the sibling repositories -------------------------------
# devices_db.py and contacts_db.py store their rows in this same file, so they
# reuse the connection and the write lock opened here instead of opening a
# second handle to the same SQLite file.

write_lock = _lock


def connection() -> sqlite3.Connection | None:
    """The open connection, or None before init_db() / after close_db()."""
    return _conn


# --- writes ------------------------------------------------------------------

def _save_session_sync(
    session_id: str,
    customer_name: str,
    product: str,
    voice_name: str,
    turn_count: int,
    created_at: float,
    history: list[dict],
    latency_log: list[dict],
    ended: bool,
    provenance: dict,
):
    if _conn is None:
        return

    now = time.time()
    with _lock, _conn:
        _conn.execute(_UPSERT_SESSION, (
            session_id, customer_name, product, voice_name,
            "ended" if ended else "active",
            turn_count, created_at,
            now if ended else None,
            provenance.get("campaign_id", ""),
            provenance.get("contact_id", ""),
            provenance.get("scenario_id", ""),
            provenance.get("phone", ""),
            provenance.get("direction", "outbound"),
            provenance.get("caller_number", ""),
            provenance.get("gender", ""),
        ))

        # INSERT OR IGNORE over the whole history rather than only the newest
        # turn: it costs a handful of no-op statements but self-heals if an
        # earlier background write failed, and needs no index bookkeeping.
        _conn.executemany(
            "INSERT OR IGNORE INTO conversation_turns "
            "(session_id, turn_index, role, content, recorded_at) VALUES (?, ?, ?, ?, ?)",
            [
                (session_id, i, turn.get("role", ""), turn.get("content", ""), now)
                for i, turn in enumerate(history)
            ],
        )

        _conn.executemany(
            "INSERT OR IGNORE INTO latency_metrics "
            "(session_id, turn_number, timestamp, stt_ms, rag_ms, ttfa_ms, total_ms) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    session_id,
                    m.get("turn", i),
                    m.get("timestamp", now),
                    m.get("stt_ms"),
                    m.get("rag_ms"),
                    m.get("ttfa_ms"),
                    m.get("total_ms"),
                )
                for i, m in enumerate(latency_log)
            ],
        )


async def save_session(session: "CallSession", ended: bool = False):
    """Persist a session and everything said in it.

    Idempotent - safe to call after every turn and again on disconnect. Pass
    ended=True to close the session out (sets status + ended_at).

    A session with no turns is normally skipped: clients (the desktop app in
    particular) open and drop WebSockets without saying anything, and those empty
    rows are noise in the call history.

    The exception is any session belonging to a campaign or a contact. "Rang,
    nobody picked up" is exactly the outcome Điều 6 asks the report to filter on
    ("lọc trạng thái: thành công, thất bại"), so dropping those rows would empty
    out half of every campaign report.
    """
    if not session.history and not (
        getattr(session, "contact_id", "") or getattr(session, "campaign_id", "")
    ):
        return

    await asyncio.to_thread(
        _save_session_sync,
        session.session_id,
        session.customer_name,
        session.product,
        session.voice_name,
        session.turn_count,
        session.created_at,
        list(session.history),
        list(session.latency_log),
        ended,
        {
            "campaign_id": getattr(session, "campaign_id", ""),
            "contact_id": getattr(session, "contact_id", ""),
            "scenario_id": getattr(session, "scenario_id", ""),
            "phone": getattr(session, "phone", ""),
            "direction": getattr(session, "direction", "outbound"),
            "caller_number": getattr(session, "caller_number", ""),
            "gender": getattr(session, "gender", ""),
        },
    )


# --- reads -------------------------------------------------------------------

_METRIC_COLUMNS = ("stt_ms", "rag_ms", "ttfa_ms", "total_ms")


# Columns added after the first release. Read through `_opt` so a row coming
# from a query that did not select them (or from a database mid-upgrade) degrades
# to a default instead of raising IndexError.
def _opt(row: sqlite3.Row, key: str, default=""):
    try:
        value = row[key]
    except (IndexError, KeyError):
        return default
    return default if value is None else value


def _session_summary(row: sqlite3.Row) -> dict:
    ended_at = row["ended_at"]
    return {
        "session_id": row["session_id"],
        "customer_name": row["customer_name"],
        "product": row["product"],
        "voice_name": row["voice_name"],
        "status": row["status"],
        "turn_count": row["turn_count"],
        "created_at": row["created_at"],
        "ended_at": ended_at,
        "duration_seconds": round((ended_at or time.time()) - row["created_at"], 1),
        "campaign_id": _opt(row, "campaign_id"),
        "contact_id": _opt(row, "contact_id"),
        "scenario_id": _opt(row, "scenario_id"),
        "phone": _opt(row, "phone"),
        "direction": _opt(row, "direction", "outbound"),
        "caller_number": _opt(row, "caller_number"),
        "outcome": _opt(row, "outcome"),
        "quality": _opt(row, "quality"),
        "label": _opt(row, "label"),
        "gender": _opt(row, "gender"),
        "recording_path": _opt(row, "recording_path"),
        "recording_size": _opt(row, "recording_size", 0),
        "summary": _opt(row, "summary"),
        "suggested_label": _opt(row, "suggested_label"),
        "transferred_to": _opt(row, "transferred_to"),
        "transfer_reason": _opt(row, "transfer_reason"),
    }


def _get_session_sync(session_id: str) -> dict | None:
    if _conn is None:
        return None

    with _lock:
        row = _conn.execute(
            "SELECT * FROM call_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            return None

        turns = _conn.execute(
            "SELECT role, content FROM conversation_turns "
            "WHERE session_id = ? ORDER BY turn_index",
            (session_id,),
        ).fetchall()
        metrics = _conn.execute(
            "SELECT * FROM latency_metrics WHERE session_id = ? ORDER BY turn_number",
            (session_id,),
        ).fetchall()

    data = _session_summary(row)
    data["history"] = [{"role": t["role"], "content": t["content"]} for t in turns]
    # Rebuild the same dict shape log_latency() produces, dropping keys that
    # were never recorded so the payload matches CallSession.to_dict().
    data["latency_log"] = [
        {
            "turn": m["turn_number"],
            "timestamp": m["timestamp"],
            **{c: m[c] for c in _METRIC_COLUMNS if m[c] is not None},
        }
        for m in metrics
    ]
    return data


async def get_session(session_id: str) -> dict | None:
    """Read one session with its full history. Same shape as CallSession.to_dict()."""
    return await asyncio.to_thread(_get_session_sync, session_id)


def _list_sessions_sync(
    page: int, limit: int, q: str = "", status: str = ""
) -> tuple[list[dict], int]:
    if _conn is None:
        return [], 0

    where, params = [], []
    if q:
        where.append("(customer_name LIKE ? OR product LIKE ? OR session_id LIKE ?)")
        like = f"%{q}%"
        params += [like, like, like]
    if status in ("active", "ended"):
        where.append("status = ?")
        params.append(status)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    offset = max(0, (page - 1) * limit)
    with _lock:
        total = _conn.execute(
            f"SELECT COUNT(*) FROM call_sessions {where_sql}", params
        ).fetchone()[0]
        rows = _conn.execute(
            f"SELECT * FROM call_sessions {where_sql} "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return [_session_summary(r) for r in rows], total


async def list_sessions(
    page: int = 1, limit: int = 20, q: str = "", status: str = ""
) -> tuple[list[dict], int]:
    """Past sessions, newest first, with optional search/filter.

    Returns (items, total_matching). Headers only - no turns.
    """
    return await asyncio.to_thread(_list_sessions_sync, page, limit, q, status)


def _delete_session_sync(session_id: str) -> bool:
    if _conn is None:
        return False
    with _lock, _conn:
        cur = _conn.execute(
            "DELETE FROM call_sessions WHERE session_id = ?", (session_id,)
        )
    # turns + metrics go with it via ON DELETE CASCADE
    return cur.rowcount > 0


async def delete_session_record(session_id: str) -> bool:
    """Hard-delete a session and its transcript/metrics from the database."""
    return await asyncio.to_thread(_delete_session_sync, session_id)


def _session_stats_sync() -> dict:
    if _conn is None:
        return {}

    day_start = time.time() - 86400
    with _lock:
        totals = _conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(turn_count), 0) AS turns "
            "FROM call_sessions"
        ).fetchone()
        today = _conn.execute(
            "SELECT COUNT(*) FROM call_sessions WHERE created_at >= ?", (day_start,)
        ).fetchone()[0]
        avg_dur = _conn.execute(
            "SELECT AVG(ended_at - created_at) FROM call_sessions "
            "WHERE status = 'ended' AND ended_at IS NOT NULL"
        ).fetchone()[0]
        lat = _conn.execute(
            "SELECT AVG(ttfa_ms) AS ttfa, AVG(total_ms) AS total FROM latency_metrics"
        ).fetchone()

    return {
        "total_sessions": totals["n"],
        "total_turns": totals["turns"],
        "sessions_24h": today,
        "avg_duration_seconds": round(avg_dur, 1) if avg_dur else 0,
        "avg_ttfa_ms": round(lat["ttfa"]) if lat["ttfa"] else None,
        "avg_total_ms": round(lat["total"]) if lat["total"] else None,
    }


async def session_stats() -> dict:
    """Aggregate numbers for the session-management dashboard."""
    return await asyncio.to_thread(_session_stats_sync)
