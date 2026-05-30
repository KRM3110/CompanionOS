from typing import Any, Dict, List
from uuid import uuid4

from .connection import _utc_now, get_conn


async def create_document(
    workspace_id: str,
    filename: str,
    file_type: str,
    chunk_count: int = 0,
    guard_status: str = "clean",
    status: str = "pending",
) -> str:
    doc_id = str(uuid4())
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO documents (id, workspace_id, filename, file_type, chunk_count, guard_status, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (doc_id, workspace_id, filename, file_type, chunk_count, guard_status, status, _utc_now()),
        )
        await conn.commit()
    return doc_id


async def update_document_chunks(doc_id: str, chunk_count: int, status: str = "ready") -> None:
    if status not in ("ready", "error", "pending"):
        status = "ready"
    async with get_conn() as conn:
        await conn.execute(
            "UPDATE documents SET chunk_count = ?, status = ? WHERE id = ?",
            (chunk_count, status, doc_id),
        )
        await conn.commit()


async def list_documents(workspace_id: str) -> List[Dict[str, Any]]:
    async with get_conn() as conn:
        async with conn.execute(
            """
            SELECT id, workspace_id, filename, file_type, chunk_count, guard_status, status, created_at
            FROM documents WHERE workspace_id = ? ORDER BY created_at DESC
            """,
            (workspace_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_document(doc_id: str) -> Dict[str, Any] | None:
    async with get_conn() as conn:
        async with conn.execute(
            "SELECT id, workspace_id, filename, file_type, chunk_count, guard_status, status, created_at FROM documents WHERE id = ?",
            (doc_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def delete_document_db(doc_id: str) -> bool:
    async with get_conn() as conn:
        cur = await conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        await conn.commit()
        return cur.rowcount > 0
