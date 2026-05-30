from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..db import upsert_memory_item
from ..research import research_agent
from ..research.research_db import (
    create_research_session,
    get_research_session,
    list_research_sessions,
)
from .schemas import SaveResearchReq, StartResearchReq

router = APIRouter()


@router.post("/research")
async def start_research_api(req: StartResearchReq):
    research_id = await create_research_session(
        question=req.question, workspace_id=req.workspace_id
    )
    return {"research_id": research_id, "question": req.question}


@router.get("/research")
async def list_research_api(limit: int = 50):
    return await list_research_sessions(limit=limit)


@router.get("/research/{research_id}")
async def get_research_api(research_id: str):
    session = await get_research_session(research_id)
    if not session:
        raise HTTPException(status_code=404, detail="Research session not found")
    return session


@router.get("/research/{research_id}/stream")
async def research_stream_api(research_id: str):
    """SSE endpoint that runs the research pipeline and streams progress events."""
    session = await get_research_session(research_id)
    if not session:
        raise HTTPException(status_code=404, detail="Research session not found")

    async def event_generator():
        async for payload in research_agent.run_research(
            research_id=research_id,
            question=session["question"],
            workspace_id=session.get("workspace_id"),
        ):
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/research/{research_id}/save")
async def save_research_api(research_id: str, req: SaveResearchReq):
    session = await get_research_session(research_id)
    if not session:
        raise HTTPException(status_code=404, detail="Research session not found")
    if session.get("status") != "done" or not session.get("report_md"):
        raise HTTPException(status_code=400, detail="Research session is not completed yet")

    mem_id = await upsert_memory_item(
        scope=req.scope,
        key=f"research:{session['question'][:60]}",
        value=session["report_md"][:400],
        confidence=0.9,
        session_id=req.session_id if req.scope == "session" else None,
    )
    return {"saved": True, "memory_id": mem_id, "research_id": research_id}
