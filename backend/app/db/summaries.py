import json
from typing import Any, Dict

from .connection import _utc_now, get_conn


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
