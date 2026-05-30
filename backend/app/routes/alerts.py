from fastapi import APIRouter, HTTPException

from ..db import get_due_alerts, list_alerts, update_alert_status

router = APIRouter()


@router.get("/alerts")
async def list_alerts_api(
    scope: str = "global",
    session_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
):
    if scope not in ("global", "session"):
        raise HTTPException(status_code=400, detail="scope must be 'global' or 'session'")
    if scope == "global":
        return await list_alerts(scope="global", status=status, limit=limit)
    return await list_alerts(scope="session", session_id=session_id, status=status, limit=limit)


@router.post("/alerts/{alert_id}/done")
async def mark_alert_done_api(alert_id: str):
    ok = await update_alert_status(alert_id, "done")
    if not ok:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"ok": True}


@router.post("/alerts/{alert_id}/cancel")
async def mark_alert_cancel_api(alert_id: str):
    ok = await update_alert_status(alert_id, "cancelled")
    if not ok:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"ok": True}


@router.get("/alerts/due")
async def get_due_alerts_api(session_id: str | None = None, limit: int = 10):
    return await get_due_alerts(session_id=session_id, limit=limit)
