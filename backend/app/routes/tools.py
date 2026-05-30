from fastapi import APIRouter, HTTPException

from ..db import list_tool_settings, upsert_tool_setting
from ..state import TOOLS_REGISTRY
from .schemas import ToolSettingUpsertReq

router = APIRouter()


@router.get("/tools")
def list_tools_api():
    return [
        {"tool_id": t.id, "name": t.name, "description": t.description}
        for t in TOOLS_REGISTRY.list_tools()
    ]


@router.get("/tools/settings")
async def list_tool_settings_api(scope: str = "global", session_id: str | None = None):
    if scope not in ("global", "session"):
        raise HTTPException(status_code=400, detail="scope must be global|session")
    if scope == "session" and not session_id:
        raise HTTPException(status_code=400, detail="session_id is required for session scope")
    return await list_tool_settings(scope=scope, session_id=session_id)


@router.put("/tools/settings")
async def upsert_tool_setting_api(req: ToolSettingUpsertReq):
    if req.scope == "session" and not req.session_id:
        raise HTTPException(status_code=400, detail="session_id is required for session scope")
    _id = await upsert_tool_setting(
        scope=req.scope,
        tool_id=req.tool_id,
        enabled=req.enabled,
        session_id=req.session_id,
    )
    return {"id": _id}
