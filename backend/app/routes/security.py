from fastapi import APIRouter, HTTPException

from ..security import content_guard
from ..security.guard_db import (
    get_audit_by_doc,
    insert_audit_record,
    list_audit_records,
)
from .schemas import ScanTextReq

router = APIRouter()


@router.post("/security/scan")
async def security_scan_api(req: ScanTextReq):
    result = await content_guard.scan(req.text)
    audit_id = None
    if req.document_id:
        audit_id = await insert_audit_record(
            document_id=req.document_id,
            verdict=result.verdict,
            patterns_hit=result.patterns_hit,
            llm_reason=result.llm_reason or None,
        )
    return {
        "verdict": result.verdict,
        "patterns_hit": result.patterns_hit,
        "llm_reason": result.llm_reason,
        "audit_id": audit_id,
        "sanitized_preview": result.sanitized_text[:500] if result.sanitized_text else "",
    }


@router.get("/security/audit")
async def list_audit_api(verdict: str | None = None, limit: int = 100):
    if verdict and verdict not in ("CLEAN", "FLAGGED", "BLOCKED"):
        raise HTTPException(
            status_code=400, detail="verdict must be CLEAN, FLAGGED, or BLOCKED"
        )
    return await list_audit_records(verdict_filter=verdict, limit=limit)


@router.get("/security/audit/{document_id}")
async def get_audit_by_doc_api(document_id: str):
    record = await get_audit_by_doc(document_id)
    if not record:
        raise HTTPException(status_code=404, detail="No audit record found for this document")
    return record
