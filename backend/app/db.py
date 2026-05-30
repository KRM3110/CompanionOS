import aiosqlite
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, List, Dict, Any, Optional
from uuid import uuid4
from datetime import datetime

DB_PATH = Path("/app/data/companionos.db")


def _utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


@asynccontextmanager
async def get_conn() -> AsyncIterator[aiosqlite.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        yield conn


async def init_db() -> None:
    async with get_conn() as conn:
        # ── sessions: create with mode_id (new schema) ─────────────────────────
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                mode_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        # ── Lightweight migration: rename persona_id → mode_id if old column exists ──
        async with conn.execute("PRAGMA table_info(sessions)") as cur:
            cols = [row[1] for row in await cur.fetchall()]
        if "persona_id" in cols and "mode_id" not in cols:
            # SQLite ALTER TABLE RENAME COLUMN (requires SQLite ≥ 3.25)
            try:
                await conn.execute("ALTER TABLE sessions RENAME COLUMN persona_id TO mode_id")
            except Exception:
                # Fallback for older SQLite: table rebuild
                await conn.execute(
                    """
                    CREATE TABLE sessions_new (
                        id TEXT PRIMARY KEY,
                        mode_id TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                await conn.execute(
                    "INSERT INTO sessions_new SELECT id, persona_id, created_at FROM sessions"
                )
                await conn.execute("DROP TABLE sessions")
                await conn.execute("ALTER TABLE sessions_new RENAME TO sessions")

        await conn.execute(
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
        await conn.execute(
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
        await conn.execute(
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
        await conn.execute(
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
        await conn.execute(
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
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS guard_audit (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                verdict TEXT NOT NULL CHECK(verdict IN ('CLEAN', 'FLAGGED', 'BLOCKED')),
                patterns_hit TEXT,
                llm_reason TEXT,
                scanned_at TEXT NOT NULL
            )
            """
        )
        # ── Feature 1: RAG Document Workspace tables ────────────────────────────
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workspaces (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_type TEXT,
                chunk_count INTEGER DEFAULT 0,
                guard_status TEXT DEFAULT 'clean',
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'ready', 'error')),
                created_at TEXT NOT NULL,
                FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
            )
            """
        )
        # ── Migration: add status column to existing documents tables ──────────
        async with conn.execute("PRAGMA table_info(documents)") as cur:
            doc_cols = [row[1] for row in await cur.fetchall()]
        if doc_cols and "status" not in doc_cols:
            await conn.execute(
                "ALTER TABLE documents ADD COLUMN status TEXT NOT NULL DEFAULT 'ready'"
            )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_jobs (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                mode_id TEXT NOT NULL,
                user_message TEXT NOT NULL,
                assistant_final TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'succeeded', 'failed')),
                attempts INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 2,
                queued_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                last_error TEXT,
                pipeline_result TEXT,
                tool_events TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at DESC)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_session_created ON messages(session_id, created_at ASC)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_memory_scope_session_updated ON memory_items(scope, session_id, updated_at DESC)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_scope_session_status_due ON alerts(scope, session_id, status, due_at)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tool_settings_scope_session_tool ON tool_settings(scope, session_id, tool_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_guard_audit_doc_scanned ON guard_audit(document_id, scanned_at DESC)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_workspace_created ON documents(workspace_id, created_at DESC)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_jobs_status_queued ON chat_jobs(status, queued_at ASC)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_jobs_session ON chat_jobs(session_id, queued_at DESC)"
        )
        # ── Feature 2: Research Mode ─────────────────────────────────────────────
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS research_sessions (
                id TEXT PRIMARY KEY,
                question TEXT NOT NULL,
                workspace_id TEXT,
                status TEXT NOT NULL CHECK(status IN ('planning', 'searching', 'building', 'done', 'error')),
                plan_json TEXT,
                report_md TEXT,
                sources_json TEXT,
                error_msg TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_research_sessions_created ON research_sessions(created_at DESC)"
        )
        async with conn.execute("PRAGMA table_info(documents)") as cur:
            doc_cols = [row[1] for row in await cur.fetchall()]
        if "status" not in doc_cols:
            await conn.execute(
                "ALTER TABLE documents ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'"
            )
            await conn.execute(
                "UPDATE documents SET status = 'ready' WHERE COALESCE(chunk_count, 0) > 0"
            )
        await conn.commit()


# ---------------- Sessions ----------------

async def create_session(mode_id: str) -> str:
    """Creates a new session keyed to the given AssistantMode ID."""
    session_id = str(uuid4())
    async with get_conn() as conn:
        await conn.execute(
            "INSERT INTO sessions (id, mode_id, created_at) VALUES (?, ?, ?)",
            (session_id, mode_id, _utc_now()),
        )
        await conn.commit()
    return session_id


async def list_sessions() -> List[Dict[str, Any]]:
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT id, mode_id, created_at FROM sessions ORDER BY created_at DESC"
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_session(session_id: str) -> Dict[str, Any] | None:
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT id, mode_id, created_at FROM sessions WHERE id = ?",
            (session_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


# ---------------- Messages ----------------

async def add_message(session_id: str, role: str, content: str) -> str:
    msg_id = str(uuid4())
    async with get_conn() as conn:
        await conn.execute(
            "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (msg_id, session_id, role, content, _utc_now()),
        )
        await conn.commit()
    return msg_id


async def get_messages(session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    async with get_conn() as conn:
        async with conn.execute(
            """
            SELECT id, session_id, role, content, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (session_id, limit),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def count_messages(session_id: str) -> int:
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT COUNT(*) as count FROM messages WHERE session_id = ?",
            (session_id,),
        ) as cur:
            row = await cur.fetchone()
            return row["count"] if row else 0


# ---------------- Memory ----------------

async def upsert_memory_item(
    scope: str,
    key: str,
    value: str,
    confidence: float = 0.8,
    session_id: str | None = None,
    source_message_id: str | None = None,
) -> str:
    mem_id = str(uuid4())
    now = _utc_now()
    async with get_conn() as conn:
        async with conn.execute(
            """
            SELECT id FROM memory_items
            WHERE scope = ? AND key = ? AND (session_id IS ? OR session_id = ?)
            """,
            (scope, key, session_id, session_id),
        ) as cur:
            existing = await cur.fetchone()

        if existing:
            mem_id = existing["id"]
            await conn.execute(
                """
                UPDATE memory_items
                SET value = ?, confidence = ?, source_message_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (value, confidence, source_message_id, now, mem_id),
            )
        else:
            await conn.execute(
                """
                INSERT INTO memory_items
                (id, scope, session_id, key, value, confidence, source_message_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (mem_id, scope, session_id, key, value, confidence, source_message_id, now, now),
            )
        await conn.commit()
    return mem_id


async def list_memory_items(scope: str, session_id: str | None = None, limit: int = 50) -> List[Dict[str, Any]]:
    async with get_conn() as conn:
        if scope == "global":
            async with conn.execute(
                """
                SELECT * FROM memory_items
                WHERE scope = 'global'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        else:
            if not session_id:
                return []
            async with conn.execute(
                """
                SELECT * FROM memory_items
                WHERE scope = 'session' AND session_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def delete_memory_item(mem_id: str) -> bool:
    async with get_conn() as conn:
        cur = await conn.execute("DELETE FROM memory_items WHERE id = ?", (mem_id,))
        await conn.commit()
        return cur.rowcount > 0


# ---------------- Session Summary ----------------

async def get_session_summary(session_id: str) -> Dict[str, Any] | None:
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT session_id, summary, open_loops, updated_at FROM session_summaries WHERE session_id = ?",
            (session_id,),
        ) as cur:
            row = await cur.fetchone()
            
    if not row:
        return None

    result = dict(row)
    open_loops_str = result.get("open_loops", "[]")
    try:
        result["open_loops"] = json.loads(open_loops_str) if isinstance(open_loops_str, str) else open_loops_str
    except (json.JSONDecodeError, TypeError):
        result["open_loops"] = []
    return result


async def upsert_session_summary(session_id: str, summary: str, open_loops: list[str]) -> None:
    now = _utc_now()
    open_loops_json = json.dumps(open_loops)
    
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT session_id FROM session_summaries WHERE session_id = ?",
            (session_id,),
        ) as cur:
            existing = await cur.fetchone()

        if existing:
            await conn.execute(
                """
                UPDATE session_summaries
                SET summary = ?, open_loops = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (summary, open_loops_json, now, session_id),
            )
        else:
            await conn.execute(
                """
                INSERT INTO session_summaries (session_id, summary, open_loops, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, summary, open_loops_json, now),
            )
        await conn.commit()


# ---------------- Alerts (TOOLS) ----------------

async def create_alert(
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

    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO alerts
            (id, scope, session_id, title, body, due_at, status, confidence, source_message_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (alert_id, scope, session_id, title, body, due_at, confidence, source_message_id, now, now),
        )
        await conn.commit()
    return alert_id


async def list_alerts(scope: str, session_id: str | None = None, status: str | None = None, limit: int = 50) -> List[Dict[str, Any]]:
    async with get_conn() as conn:
        if scope == "global":
            if status:
                async with conn.execute(
                    """
                    SELECT * FROM alerts
                    WHERE scope = 'global' AND status = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (status, limit),
                ) as cur:
                    rows = await cur.fetchall()
            else:
                async with conn.execute(
                    """
                    SELECT * FROM alerts
                    WHERE scope = 'global'
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ) as cur:
                    rows = await cur.fetchall()
        else:
            if not session_id:
                return []
                
            if status:
                async with conn.execute(
                    """
                    SELECT * FROM alerts
                    WHERE scope = 'session' AND session_id = ? AND status = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (session_id, status, limit),
                ) as cur:
                    rows = await cur.fetchall()
            else:
                async with conn.execute(
                    """
                    SELECT * FROM alerts
                    WHERE scope = 'session' AND session_id = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (session_id, limit),
                ) as cur:
                    rows = await cur.fetchall()

        return [dict(r) for r in rows]


async def update_alert_status(alert_id: str, status: str) -> bool:
    if status not in ("active", "done", "cancelled"):
        raise ValueError("Invalid status")

    now = _utc_now()
    async with get_conn() as conn:
        cur = await conn.execute(
            """
            UPDATE alerts
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, now, alert_id),
        )
        await conn.commit()
        return cur.rowcount > 0


async def get_due_alerts(session_id: str | None = None, limit: int = 10) -> List[Dict[str, Any]]:
    """Get alerts that are due (due_at <= now and status = 'active')."""
    now = _utc_now()
    async with get_conn() as conn:
        if session_id:
            async with conn.execute(
                """
                SELECT * FROM alerts
                WHERE status = 'active' AND due_at <= ? AND session_id = ?
                ORDER BY due_at ASC
                LIMIT ?
                """,
                (now, session_id, limit),
            ) as cur:
                rows = await cur.fetchall()
        else:
            async with conn.execute(
                """
                SELECT * FROM alerts
                WHERE status = 'active' AND due_at <= ?
                ORDER BY due_at ASC
                LIMIT ?
                """,
                (now, limit),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]


# ---------------- Tool Settings ----------------
async def upsert_tool_setting(scope: str, tool_id: str, enabled: bool, session_id: str | None = None) -> str:
    setting_id = str(uuid4())
    now = _utc_now()
    
    async with get_conn() as conn:
        async with conn.execute(
            """
            SELECT id FROM tool_settings
            WHERE scope = ? AND tool_id = ? AND (session_id IS ? OR session_id = ?)
            """,
            (scope, tool_id, session_id, session_id),
        ) as cur:
            existing = await cur.fetchone()

        if existing:
            setting_id = existing["id"]
            await conn.execute(
                """
                UPDATE tool_settings
                SET enabled = ?, updated_at = ?
                WHERE id = ?
                """,
                (1 if enabled else 0, now, setting_id),
            )
        else:
            await conn.execute(
                """
                INSERT INTO tool_settings (id, scope, session_id, tool_id, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (setting_id, scope, session_id, tool_id, 1 if enabled else 0, now, now),
            )
        await conn.commit()
    return setting_id


async def list_tool_settings(scope: str, session_id: str | None = None, limit: int = 100) -> list[dict]:
    async with get_conn() as conn:
        if scope == "global":
            async with conn.execute(
                """
                SELECT * FROM tool_settings
                WHERE scope = 'global'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        else:
            if not session_id:
                return []
            async with conn.execute(
                """
                SELECT * FROM tool_settings
                WHERE scope = 'session' AND session_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (session_id, limit),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_effective_tool_enabled_map(session_id: str, tool_ids: list[str]) -> dict[str, bool]:
    enabled: dict[str, bool] = {tid: True for tid in tool_ids}
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT tool_id, enabled FROM tool_settings WHERE scope='global'"
        ) as cur:
            g = await cur.fetchall()
            for r in g:
                enabled[r["tool_id"]] = bool(r["enabled"])

        async with conn.execute(
            "SELECT tool_id, enabled FROM tool_settings WHERE scope='session' AND session_id=?",
            (session_id,),
        ) as cur:
            s = await cur.fetchall()
            for r in s:
                enabled[r["tool_id"]] = bool(r["enabled"])

    return {tid: enabled.get(tid, True) for tid in tool_ids}


# ---------------- Workspaces (Feature 1) ----------------

async def create_workspace(name: str, description: str | None = None) -> str:
    """Creates a new workspace and returns its UUID."""
    ws_id = str(uuid4())
    async with get_conn() as conn:
        await conn.execute(
            "INSERT INTO workspaces (id, name, description, created_at) VALUES (?, ?, ?, ?)",
            (ws_id, name, description, _utc_now()),
        )
        await conn.commit()
    return ws_id


async def list_workspaces() -> List[Dict[str, Any]]:
    """Returns all workspaces with document and chunk counts, newest first."""
    async with get_conn() as conn:
        async with conn.execute(
            """
            SELECT
                w.id, w.name, w.description, w.created_at,
                COUNT(d.id) AS document_count,
                COALESCE(SUM(d.chunk_count), 0) AS total_chunks
            FROM workspaces w
            LEFT JOIN documents d ON d.workspace_id = w.id
            GROUP BY w.id
            ORDER BY w.created_at DESC
            """
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_workspace(workspace_id: str) -> Dict[str, Any] | None:
    """Fetches a single workspace by ID, or None if not found."""
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT id, name, description, created_at FROM workspaces WHERE id = ?",
            (workspace_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def delete_workspace_db(workspace_id: str) -> bool:
    """Deletes a workspace and all its associated documents from the DB. Returns True if deleted."""
    async with get_conn() as conn:
        await conn.execute("DELETE FROM documents WHERE workspace_id = ?", (workspace_id,))
        cur = await conn.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
        await conn.commit()
        return cur.rowcount > 0


# ---------------- Documents (Feature 1) ----------------

async def create_document(
    workspace_id: str,
    filename: str,
    file_type: str,
    chunk_count: int = 0,
    guard_status: str = "clean",
    status: str = "pending",
) -> str:
    """Creates a document record and returns its UUID."""
    doc_id = str(uuid4())
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO documents (id, workspace_id, filename, file_type, chunk_count, guard_status, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (doc_id, workspace_id, filename, file_type, chunk_count, guard_status, status, _utc_now()),
        )
        await conn.commit()
    return doc_id


async def update_document_chunks(doc_id: str, chunk_count: int, status: str = "ready") -> None:
    """Updates chunk_count and status on a document record after indexing.
    
    Args:
        doc_id:      Document UUID.
        chunk_count: Number of chunks successfully indexed.
        status:      'ready' on success, 'error' on indexing failure.
    """
    if status not in ("ready", "error", "pending"):
        status = "ready"
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE documents SET chunk_count = ?, status = ? WHERE id = ?",
            (chunk_count, status, doc_id),
        )
        await conn.commit()


async def list_documents(workspace_id: str) -> List[Dict[str, Any]]:
    """Returns all documents in a workspace ordered by creation time."""
    async with get_conn() as conn:
        async with conn.execute(
            """
            SELECT id, workspace_id, filename, file_type, chunk_count, guard_status, status, created_at
            FROM documents WHERE workspace_id = ? ORDER BY created_at DESC
            """,
            (workspace_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_document(doc_id: str) -> Dict[str, Any] | None:
    """Fetches a single document record, or None if not found."""
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT id, workspace_id, filename, file_type, chunk_count, guard_status, status, created_at FROM documents WHERE id = ?",
            (doc_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def delete_document_db(doc_id: str) -> bool:
    """Deletes a document record from the DB. Returns True if deleted."""
    async with get_conn() as conn:
        cur = await conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        await conn.commit()
        return cur.rowcount > 0


# ---------------- Chat Jobs (Latency Queue) ----------------

def _deserialize_chat_job(row: aiosqlite.Row | None) -> Dict[str, Any] | None:
    if not row:
        return None
    data = dict(row)
    for field in ("pipeline_result", "tool_events"):
        raw = data.get(field)
        if raw is None:
            data[field] = None
            continue
        try:
            data[field] = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            data[field] = None
    return data


async def create_chat_job(
    session_id: str,
    mode_id: str,
    user_message: str,
    assistant_final: str,
    max_retries: int = 2,
) -> Dict[str, Any]:
    job_id = str(uuid4())
    queued_at = _utc_now()
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO chat_jobs
            (id, session_id, mode_id, user_message, assistant_final, status, attempts, max_retries, queued_at)
            VALUES (?, ?, ?, ?, ?, 'queued', 0, ?, ?)
            """,
            (job_id, session_id, mode_id, user_message, assistant_final, max_retries, queued_at),
        )
        await conn.commit()
    return {
        "id": job_id,
        "session_id": session_id,
        "mode_id": mode_id,
        "status": "queued",
        "attempts": 0,
        "max_retries": max_retries,
        "queued_at": queued_at,
        "started_at": None,
        "finished_at": None,
        "last_error": None,
        "pipeline_result": None,
        "tool_events": None,
    }


async def get_chat_job(job_id: str) -> Dict[str, Any] | None:
    async with get_conn() as conn:
        async with conn.execute(
            """
            SELECT id, session_id, mode_id, user_message, assistant_final, status, attempts, max_retries,
                   queued_at, started_at, finished_at, last_error, pipeline_result, tool_events
            FROM chat_jobs
            WHERE id = ?
            """,
            (job_id,),
        ) as cur:
            row = await cur.fetchone()
    return _deserialize_chat_job(row)


async def recover_chat_jobs(limit: int = 1000) -> List[str]:
    """
    Recover queued/running jobs after restart by setting them back to queued and
    returning IDs ordered by queue time.
    """
    async with get_conn() as conn:
        await conn.execute(
            """
            UPDATE chat_jobs
            SET status = 'queued', started_at = NULL
            WHERE status = 'running'
            """
        )
        await conn.commit()
        async with conn.execute(
            """
            SELECT id
            FROM chat_jobs
            WHERE status = 'queued'
            ORDER BY queued_at ASC
            LIMIT ?
            """,
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    return [r["id"] for r in rows]


async def start_chat_job_attempt(job_id: str) -> Dict[str, Any] | None:
    """
    Mark a queued job as running and increment attempts.
    Returns updated job row; returns None if job was not queued.
    """
    started_at = _utc_now()
    async with get_conn() as conn:
        cur = await conn.execute(
            """
            UPDATE chat_jobs
            SET status = 'running',
                attempts = attempts + 1,
                started_at = ?,
                last_error = NULL
            WHERE id = ? AND status = 'queued'
            """,
            (started_at, job_id),
        )
        if cur.rowcount == 0:
            await conn.commit()
            return None
        await conn.commit()
    return await get_chat_job(job_id)


async def requeue_chat_job(job_id: str, error: str) -> None:
    async with get_conn() as conn:
        await conn.execute(
            """
            UPDATE chat_jobs
            SET status = 'queued',
                started_at = NULL,
                finished_at = NULL,
                last_error = ?
            WHERE id = ?
            """,
            (error[:1000], job_id),
        )
        await conn.commit()


async def fail_chat_job(job_id: str, error: str) -> None:
    finished_at = _utc_now()
    async with get_conn() as conn:
        await conn.execute(
            """
            UPDATE chat_jobs
            SET status = 'failed',
                finished_at = ?,
                last_error = ?
            WHERE id = ?
            """,
            (finished_at, error[:1000], job_id),
        )
        await conn.commit()


async def succeed_chat_job(job_id: str, pipeline_result: Dict[str, Any], tool_events: List[Dict[str, Any]]) -> None:
    finished_at = _utc_now()
    async with get_conn() as conn:
        await conn.execute(
            """
            UPDATE chat_jobs
            SET status = 'succeeded',
                finished_at = ?,
                pipeline_result = ?,
                tool_events = ?,
                last_error = NULL
            WHERE id = ?
            """,
            (
                finished_at,
                json.dumps(pipeline_result, ensure_ascii=False),
                json.dumps(tool_events, ensure_ascii=False),
                job_id,
            ),
        )
        await conn.commit()
