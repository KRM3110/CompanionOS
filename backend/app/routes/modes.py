from fastapi import APIRouter, HTTPException

from ..state import MODES

router = APIRouter()


@router.get("/modes")
def list_modes_api():
    return [m.model_dump() for m in MODES.values()]


@router.get("/modes/{mode_id}")
def get_mode_api(mode_id: str):
    mode = MODES.get(mode_id)
    if not mode:
        raise HTTPException(status_code=404, detail="Mode not found")
    return mode.model_dump()
