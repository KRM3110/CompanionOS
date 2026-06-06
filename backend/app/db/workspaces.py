from typing import Any, Dict, List
from uuid import uuid4

from .connection import _utc_now, get_conn


async def create_workspace(name: str, description: str | None = None) -> str:
    ws_id = str(uuid4())
    async with get_conn() as conn:
        await conn.execute(
            "INSERT INTO workspaces (id, name, description, created_at) VALUES (?, ?, ?, ?)",
            (ws_id, name, description, _utc_now()),
        )
        await conn.commit()
    return ws_id


async def list_workspaces() -> List[Dict[str, Any]]:
    async with get_conn() as conn:
        async with conn.execute(
            """
            SELECT
                w.id, w.name, w.description, w.created_at,
                COUNT(d.id) AS document_count,
                COALESCE(SUM(d.chunk_count), 0) AS total_chunks
            FROM workspaces w
            LEFT JOIN documents d ON d.workspace_id = w.id
            GROUP BY w.id
            ORDER BY w.created_at DESC
            """
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_workspace(workspace_id: str) -> Dict[str, Any] | None:
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT id, name, description, created_at FROM workspaces WHERE id = ?",
            (workspace_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def delete_workspace_db(workspace_id: str) -> bool:
    async with get_conn() as conn:
        await conn.execute("DELETE FROM documents WHERE workspace_id = ?", (workspace_id,))
        cur = await conn.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
        await conn.commit()
        return cur.rowcount > 0
