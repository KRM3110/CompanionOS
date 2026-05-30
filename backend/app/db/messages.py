from typing import Any, Dict, List
from uuid import uuid4

from .connection import _utc_now, get_conn


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
