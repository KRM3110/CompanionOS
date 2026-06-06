import aiosqlite
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

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
    """Idempotent schema bootstrap.

    Kept as a runtime safety net so the app boots on a fresh volume even when
    alembic hasn't been run. The authoritative schema source going forward is
    backend/alembic/versions/.
    """
    async with get_conn() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                mode_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

        async with conn.execute("PRAGMA table_info(sessions)") as cur:
            cols = [row[1] for row in await cur.fetchall()]
        if "persona_id" in cols and "mode_id" not in cols:
            try:
                await conn.execute("ALTER TABLE sessions RENAME COLUMN persona_id TO mode_id")
            except Exception:
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

        # Pre-alembic databases shipped with CHECK(status IN ('pending', 'ready')).
        # The current schema also permits 'error', and the upload route writes
        # 'error' when indexing fails. Rebuild the table if 'error' isn't allowed.
        async with conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='documents'"
        ) as cur:
            row = await cur.fetchone()
        documents_sql = row[0] if row else ""
        if documents_sql and "'error'" not in documents_sql:
            await conn.execute("PRAGMA foreign_keys = OFF")
            await conn.execute(
                """
                CREATE TABLE documents_new (
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
            await conn.execute(
                """
                INSERT INTO documents_new
                    (id, workspace_id, filename, file_type, chunk_count, guard_status, status, created_at)
                SELECT id, workspace_id, filename, file_type, chunk_count, guard_status, status, created_at
                FROM documents
                """
            )
            await conn.execute("DROP TABLE documents")
            await conn.execute("ALTER TABLE documents_new RENAME TO documents")
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_workspace_created ON documents(workspace_id, created_at DESC)"
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)"
            )
            await conn.execute("PRAGMA foreign_keys = ON")

        await conn.commit()
