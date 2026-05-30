from fastapi import APIRouter, HTTPException

from ..db import (
    count_messages,
    create_session,
    get_messages,
    get_session,
    get_session_summary,
    list_sessions,
)
from ..state import MODES, settings
from .schemas import CreateSessionReq

router = APIRouter()


@router.post("/sessions")
async def create_session_api(req: CreateSessionReq):
    if req.mode_id not in MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode_id '{req.mode_id}'. Available: {list(MODES.keys())}",
        )
    session_id = await create_session(req.mode_id)
    return {"session_id": session_id}


@router.get("/sessions")
async def list_sessions_api():
    return await list_sessions()


@router.get("/sessions/{session_id}/messages")
async def get_session_messages_api(session_id: str, limit: int = 50):
    s = await get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await get_messages(session_id, limit=limit)
    return {"session": s, "messages": messages}


@router.get("/sessions/{session_id}/summary")
async def session_summary_api(session_id: str):
    s = await get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    summary = await get_session_summary(session_id)
    msg_count = await count_messages(session_id)
    return {
        "session": s,
        "summary": summary,
        "debug": {
            "message_count": msg_count,
            "should_update_at_next": (msg_count % settings.summary_cadence == 0),
            "next_update_at": (
                (msg_count // settings.summary_cadence) + 1
            )
            * settings.summary_cadence,
        },
    }
