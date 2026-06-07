from fastapi import APIRouter, HTTPException

from ..db import delete_memory_item, list_memory_items, upsert_memory_item
from .schemas import MemoryUpsertReq

router = APIRouter()


@router.get("/memory")
async def list_memory_api(
    scope: str | None = None,
    session_id: str | None = None,
    limit: int = 50,
):
    if scope is None:
        scope = "session" if session_id else "global"
    if scope not in ("global", "session"):
        raise HTTPException(status_code=400, detail="scope must be 'global' or 'session'")
    return await list_memory_items(scope=scope, session_id=session_id, limit=limit)


@router.post("/memory")
async def upsert_memory_api(req: MemoryUpsertReq):
    if req.scope == "session" and not req.session_id:
        raise HTTPException(status_code=400, detail="session_id is required for session scope")
    mem_id = await upsert_memory_item(
        scope=req.scope,
        key=req.key,
        value=req.value,
        confidence=req.confidence,
        session_id=req.session_id,
        source_message_id=None,
    )
    return {"id": mem_id}


@router.delete("/memory/{mem_id}")
async def delete_memory_api(mem_id: str):
    ok = await delete_memory_item(mem_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory item not found")
    return {"deleted": True}
