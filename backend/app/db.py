import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from uuid import uuid4
from datetime import datetime

DB_PATH = Path("/app/data/companionos.db")


def _utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()

    # ---------------- Sessions ----------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            persona_id TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )

    # ---------------- Messages ----------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
        """
    )

    # ---------------- Memory ----------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_items (
            id TEXT PRIMARY KEY,
            scope TEXT NOT NULL CHECK(scope IN ('global', 'session')),
            session_id TEXT,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            confidence REAL NOT NULL,
            source_message_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )

    # ---------------- Session Summaries ----------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS session_summaries (
            session_id TEXT PRIMARY KEY,
            summary TEXT NOT NULL,
            open_loops TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
        """
    )

    # ---------------- Alerts (TOOLS) ----------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS alerts (
            id TEXT PRIMARY KEY,
            scope TEXT NOT NULL CHECK(scope IN ('global', 'session')),
            session_id TEXT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            due_at TEXT,
            status TEXT NOT NULL CHECK(status IN ('active', 'done', 'cancelled')),
            confidence REAL NOT NULL,
            source_message_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
        """
    )
    
    cur.execute(
    """
    CREATE TABLE IF NOT EXISTS tool_settings (
        id TEXT PRIMARY KEY,
        scope TEXT NOT NULL CHECK(scope IN ('global', 'session')),
        session_id TEXT,
        tool_id TEXT NOT NULL,
        enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """
    )

    conn.commit()
    conn.close()


# ---------------- Sessions ----------------

def create_session(persona_id: str) -> str:
    session_id = str(uuid4())
    conn = get_conn()
    conn.execute(
        "INSERT INTO sessions (id, persona_id, created_at) VALUES (?, ?, ?)",
        (session_id, persona_id, _utc_now()),
    )
    conn.commit()
    conn.close()
    return session_id


def list_sessions() -> List[Dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, persona_id, created_at FROM sessions ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session(session_id: str) -> Dict[str, Any] | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT id, persona_id, created_at FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ---------------- Messages ----------------

def add_message(session_id: str, role: str, content: str) -> str:
    msg_id = str(uuid4())
    conn = get_conn()
    conn.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (msg_id, session_id, role, content, _utc_now()),
    )
    conn.commit()
    conn.close()
    return msg_id


def get_messages(session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT id, session_id, role, content, created_at
        FROM messages
        WHERE session_id = ?
        ORDER BY created_at ASC
        LIMIT ?
        """,
        (session_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_messages(session_id: str) -> int:
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as count FROM messages WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    conn.close()
    return row["count"] if row else 0


# ---------------- Memory ----------------

def upsert_memory_item(
    scope: str,
    key: str,
    value: str,
    confidence: float = 0.8,
    session_id: str | None = None,
    source_message_id: str | None = None,
) -> str:
    mem_id = str(uuid4())
    now = _utc_now()
    conn = get_conn()

    existing = conn.execute(
        """
        SELECT id FROM memory_items
        WHERE scope = ? AND key = ? AND (session_id IS ? OR session_id = ?)
        """,
        (scope, key, session_id, session_id),
    ).fetchone()

    if existing:
        mem_id = existing["id"]
        conn.execute(
            """
            UPDATE memory_items
            SET value = ?, confidence = ?, source_message_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (value, confidence, source_message_id, now, mem_id),
        )
    else:
        conn.execute(
            """
            INSERT INTO memory_items
            (id, scope, session_id, key, value, confidence, source_message_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (mem_id, scope, session_id, key, value, confidence, source_message_id, now, now),
        )

    conn.commit()
    conn.close()
    return mem_id


def list_memory_items(scope: str, session_id: str | None = None, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_conn()

    if scope == "global":
        rows = conn.execute(
            """
            SELECT * FROM memory_items
            WHERE scope = 'global'
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    else:
        if not session_id:
            conn.close()
            return []
        rows = conn.execute(
            """
            SELECT * FROM memory_items
            WHERE scope = 'session' AND session_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()

    conn.close()
    return [dict(r) for r in rows]


def delete_memory_item(mem_id: str) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM memory_items WHERE id = ?", (mem_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0


# ---------------- Session Summary ----------------

def get_session_summary(session_id: str) -> Dict[str, Any] | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT session_id, summary, open_loops, updated_at FROM session_summaries WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None

    result = dict(row)
    open_loops_str = result.get("open_loops", "[]")
    try:
        result["open_loops"] = json.loads(open_loops_str) if isinstance(open_loops_str, str) else open_loops_str
    except (json.JSONDecodeError, TypeError):
        result["open_loops"] = []
    return result


def upsert_session_summary(session_id: str, summary: str, open_loops: list[str]) -> None:
    conn = get_conn()
    now = _utc_now()
    open_loops_json = json.dumps(open_loops)

    existing = conn.execute(
        "SELECT session_id FROM session_summaries WHERE session_id = ?",
        (session_id,),
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE session_summaries
            SET summary = ?, open_loops = ?, updated_at = ?
            WHERE session_id = ?
            """,
            (summary, open_loops_json, now, session_id),
        )
    else:
        conn.execute(
            """
            INSERT INTO session_summaries (session_id, summary, open_loops, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, summary, open_loops_json, now),
        )

    conn.commit()
    conn.close()


# ---------------- Alerts (TOOLS) ----------------

def create_alert(
    scope: str,
    title: str,
    body: str,
    due_at: str | None,
    confidence: float,
    session_id: str | None = None,
    source_message_id: str | None = None,
) -> str:
    alert_id = str(uuid4())
    now = _utc_now()

    conn = get_conn()
    conn.execute(
        """
        INSERT INTO alerts
        (id, scope, session_id, title, body, due_at, status, confidence, source_message_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
        """,
        (alert_id, scope, session_id, title, body, due_at, confidence, source_message_id, now, now),
    )
    conn.commit()
    conn.close()
    return alert_id


def list_alerts(scope: str, session_id: str | None = None, status: str | None = None, limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_conn()

    if scope == "global":
        if status:
            rows = conn.execute(
                """
                SELECT * FROM alerts
                WHERE scope = 'global' AND status = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM alerts
                WHERE scope = 'global'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    else:
        if not session_id:
            conn.close()
            return []
            
        if status:
            rows = conn.execute(
                """
                SELECT * FROM alerts
                WHERE scope = 'session' AND session_id = ? AND status = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (session_id, status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM alerts
                WHERE scope = 'session' AND session_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()

    conn.close()
    return [dict(r) for r in rows]


def update_alert_status(alert_id: str, status: str) -> bool:
    if status not in ("active", "done", "cancelled"):
        raise ValueError("Invalid status")

    conn = get_conn()
    now = _utc_now()
    cur = conn.execute(
        """
        UPDATE alerts
        SET status = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, now, alert_id),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def get_due_alerts(session_id: str | None = None, limit: int = 10) -> List[Dict[str, Any]]:
    """Get alerts that are due (due_at <= now and status = 'active')."""
    conn = get_conn()
    now = _utc_now()
    
    if session_id:
        rows = conn.execute(
            """
            SELECT * FROM alerts
            WHERE status = 'active' AND due_at <= ? AND session_id = ?
            ORDER BY due_at ASC
            LIMIT ?
            """,
            (now, session_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM alerts
            WHERE status = 'active' AND due_at <= ?
            ORDER BY due_at ASC
            LIMIT ?
            """,
            (now, limit),
        ).fetchall()
    
    conn.close()
    return [dict(r) for r in rows]


# ---------------- Tool Settings ----------------
def upsert_tool_setting(scope: str, tool_id: str, enabled: bool, session_id: str | None = None) -> str:
    setting_id = str(uuid4())
    now = _utc_now()
    conn = get_conn()

    existing = conn.execute(
        """
        SELECT id FROM tool_settings
        WHERE scope = ? AND tool_id = ? AND (session_id IS ? OR session_id = ?)
        """,
        (scope, tool_id, session_id, session_id),
    ).fetchone()

    if existing:
        setting_id = existing["id"]
        conn.execute(
            """
            UPDATE tool_settings
            SET enabled = ?, updated_at = ?
            WHERE id = ?
            """,
            (1 if enabled else 0, now, setting_id),
        )
    else:
        conn.execute(
            """
            INSERT INTO tool_settings (id, scope, session_id, tool_id, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (setting_id, scope, session_id, tool_id, 1 if enabled else 0, now, now),
        )

    conn.commit()
    conn.close()
    return setting_id


def list_tool_settings(scope: str, session_id: str | None = None, limit: int = 100) -> list[dict]:
    conn = get_conn()
    if scope == "global":
        rows = conn.execute(
            """
            SELECT * FROM tool_settings
            WHERE scope = 'global'
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    else:
        if not session_id:
            conn.close()
            return []
        rows = conn.execute(
            """
            SELECT * FROM tool_settings
            WHERE scope = 'session' AND session_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()

    conn.close()
    return [dict(r) for r in rows]


def get_effective_tool_enabled_map(session_id: str, tool_ids: list[str]) -> dict[str, bool]:
    """
    session override > global default > True
    """
    conn = get_conn()
    enabled: dict[str, bool] = {tid: True for tid in tool_ids}

    # global
    g = conn.execute(
        "SELECT tool_id, enabled FROM tool_settings WHERE scope='global'"
    ).fetchall()
    for r in g:
        enabled[r["tool_id"]] = bool(r["enabled"])

    # session overrides
    s = conn.execute(
        "SELECT tool_id, enabled FROM tool_settings WHERE scope='session' AND session_id=?",
        (session_id,),
    ).fetchall()
    for r in s:
        enabled[r["tool_id"]] = bool(r["enabled"])

    conn.close()

    # only return requested tool_ids
    return {tid: enabled.get(tid, True) for tid in tool_ids}
