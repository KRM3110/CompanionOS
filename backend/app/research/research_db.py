import json
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ..db import get_conn
from ..db.connection import _utc_now


async def create_research_session(question: str, workspace_id: Optional[str] = None) -> str:
    """Creates a new research session row and returns its UUID."""
    research_id = str(uuid4())
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO research_sessions
            (id, question, workspace_id, status, created_at)
            VALUES (?, ?, ?, 'planning', ?)
            """,
            (research_id, question, workspace_id, _utc_now()),
        )
        await conn.commit()
    return research_id


async def update_research_plan(research_id: str, plan: List[str]) -> None:
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE research_sessions SET plan_json = ?, status = 'searching' WHERE id = ?",
            (json.dumps(plan), research_id),
        )
        await conn.commit()


async def save_research_report(
    research_id: str,
    report_md: str,
    sources: List[Dict[str, Any]],
) -> None:
    async with get_conn() as conn:
        await conn.execute(
            """
            UPDATE research_sessions
            SET report_md = ?, sources_json = ?, status = 'done'
            WHERE id = ?
            """,
            (report_md, json.dumps(sources), research_id),
        )
        await conn.commit()


async def fail_research_session(research_id: str, error: str) -> None:
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE research_sessions SET status = 'error', error_msg = ? WHERE id = ?",
            (error[:500], research_id),
        )
        await conn.commit()


async def get_research_session(research_id: str) -> Optional[Dict[str, Any]]:
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT * FROM research_sessions WHERE id = ?",
            (research_id,),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    data = dict(row)
    for field in ("plan_json", "sources_json"):
        raw = data.get(field)
        if raw:
            try:
                data[field] = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                data[field] = []
        else:
            data[field] = []
    return data


async def list_research_sessions(limit: int = 50) -> List[Dict[str, Any]]:
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT * FROM research_sessions ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    results = []
    for row in rows:
        data = dict(row)
        for field in ("plan_json", "sources_json"):
            raw = data.get(field)
            if raw:
                try:
                    data[field] = json.loads(raw)
                except (TypeError, json.JSONDecodeError):
                    data[field] = []
            else:
                data[field] = []
        results.append(data)
    return results
