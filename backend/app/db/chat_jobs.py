import json
from typing import Any, Dict, List
from uuid import uuid4

import aiosqlite

from .connection import _utc_now, get_conn


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
    """Reset running jobs back to queued after restart; return queued IDs in queue order."""
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
    """Atomically claim a queued job for execution."""
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
