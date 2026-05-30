"""Database layer.

Split from a single db.py into per-domain modules. Existing call sites that
do ``from .db import init_db, create_session, ...`` continue to work via the
re-exports below.
"""

from .connection import DB_PATH, get_conn, init_db
from .sessions import create_session, get_session, list_sessions
from .messages import add_message, count_messages, get_messages
from .memory import delete_memory_item, list_memory_items, upsert_memory_item
from .summaries import get_session_summary, upsert_session_summary
from .alerts import (
    create_alert,
    get_due_alerts,
    list_alerts,
    update_alert_status,
)
from .tool_settings import (
    get_effective_tool_enabled_map,
    list_tool_settings,
    upsert_tool_setting,
)
from .workspaces import (
    create_workspace,
    delete_workspace_db,
    get_workspace,
    list_workspaces,
)
from .documents import (
    create_document,
    delete_document_db,
    get_document,
    list_documents,
    update_document_chunks,
)
from .chat_jobs import (
    create_chat_job,
    fail_chat_job,
    get_chat_job,
    recover_chat_jobs,
    requeue_chat_job,
    start_chat_job_attempt,
    succeed_chat_job,
)

__all__ = [
    "DB_PATH",
    "get_conn",
    "init_db",
    "create_session",
    "get_session",
    "list_sessions",
    "add_message",
    "count_messages",
    "get_messages",
    "delete_memory_item",
    "list_memory_items",
    "upsert_memory_item",
    "get_session_summary",
    "upsert_session_summary",
    "create_alert",
    "get_due_alerts",
    "list_alerts",
    "update_alert_status",
    "get_effective_tool_enabled_map",
    "list_tool_settings",
    "upsert_tool_setting",
    "create_workspace",
    "delete_workspace_db",
    "get_workspace",
    "list_workspaces",
    "create_document",
    "delete_document_db",
    "get_document",
    "list_documents",
    "update_document_chunks",
    "create_chat_job",
    "fail_chat_job",
    "get_chat_job",
    "recover_chat_jobs",
    "requeue_chat_job",
    "start_chat_job_attempt",
    "succeed_chat_job",
]
