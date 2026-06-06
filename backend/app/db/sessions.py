from typing import Any, Dict, List
from uuid import uuid4

from .connection import _utc_now, get_conn


async def create_session(mode_id: str) -> str:
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
