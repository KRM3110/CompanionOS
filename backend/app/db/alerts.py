from typing import Any, Dict, List
from uuid import uuid4

from .connection import _utc_now, get_conn


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


async def list_alerts(
    scope: str,
    session_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
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
    """Active alerts whose due_at is in the past."""
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
