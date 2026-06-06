"""baseline schema

Captures the schema produced by app.db.connection.init_db at the time
alembic was introduced. Idempotent: every CREATE uses IF NOT EXISTS so a
DB that was already bootstrapped by init_db can run ``alembic stamp head``
and continue forward.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-30
"""
from __future__ import annotations

from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


_TABLES_SQL = [
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        mode_id TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
        content TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(session_id) REFERENCES sessions(id)
    )
    """,
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
    """,
    """
    CREATE TABLE IF NOT EXISTS session_summaries (
        session_id TEXT PRIMARY KEY,
        summary TEXT NOT NULL,
        open_loops TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(session_id) REFERENCES sessions(id)
    )
    """,
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
    """,
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
    """,
    """
    CREATE TABLE IF NOT EXISTS guard_audit (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        verdict TEXT NOT NULL CHECK(verdict IN ('CLEAN', 'FLAGGED', 'BLOCKED')),
        patterns_hit TEXT,
        llm_reason TEXT,
        scanned_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS workspaces (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        created_at TEXT NOT NULL
    )
    """,
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
    """,
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
    """,
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
    """,
]

_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_messages_session_created ON messages(session_id, created_at ASC)",
    "CREATE INDEX IF NOT EXISTS idx_memory_scope_session_updated ON memory_items(scope, session_id, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_alerts_scope_session_status_due ON alerts(scope, session_id, status, due_at)",
    "CREATE INDEX IF NOT EXISTS idx_tool_settings_scope_session_tool ON tool_settings(scope, session_id, tool_id)",
    "CREATE INDEX IF NOT EXISTS idx_guard_audit_doc_scanned ON guard_audit(document_id, scanned_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_documents_workspace_created ON documents(workspace_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status)",
    "CREATE INDEX IF NOT EXISTS idx_chat_jobs_status_queued ON chat_jobs(status, queued_at ASC)",
    "CREATE INDEX IF NOT EXISTS idx_chat_jobs_session ON chat_jobs(session_id, queued_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_research_sessions_created ON research_sessions(created_at DESC)",
]


def upgrade() -> None:
    for stmt in _TABLES_SQL:
        op.execute(stmt)
    for stmt in _INDEXES_SQL:
        op.execute(stmt)


def downgrade() -> None:
    # Baseline downgrade drops every table created above. Order matters
    # because of FK references.
    for table in (
        "research_sessions",
        "chat_jobs",
        "documents",
        "workspaces",
        "guard_audit",
        "tool_settings",
        "alerts",
        "session_summaries",
        "memory_items",
        "messages",
        "sessions",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")
