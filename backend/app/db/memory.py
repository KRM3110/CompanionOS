from typing import Any, Dict, List
from uuid import uuid4

from .connection import _utc_now, get_conn


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
