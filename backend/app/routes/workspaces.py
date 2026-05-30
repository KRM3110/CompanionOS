import logging
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..db import (
    create_document,
    create_workspace,
    delete_document_db,
    delete_workspace_db,
    get_document,
    get_workspace,
    list_documents,
    list_workspaces,
    update_document_chunks,
)
from ..rag import document_store as doc_store
from ..rag import rag_retriever
from ..rag import vector_store as vs
from ..rag.parsers import extract_text
from ..security import content_guard
from ..security.guard_db import insert_audit_record
from .schemas import CreateWorkspaceReq, WorkspaceQueryReq

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/workspaces")
async def create_workspace_api(req: CreateWorkspaceReq):
    ws_id = await create_workspace(name=req.name, description=req.description)
    return {"workspace_id": ws_id, "name": req.name, "description": req.description}


@router.get("/workspaces")
async def list_workspaces_api():
    return await list_workspaces()


@router.delete("/workspaces/{workspace_id}")
async def delete_workspace_api(workspace_id: str):
    ws = await get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    vs.delete_workspace(workspace_id)
    await delete_workspace_db(workspace_id)
    return {"deleted": True, "workspace_id": workspace_id}


@router.post("/workspaces/{workspace_id}/documents")
async def upload_document_api(workspace_id: str, file: UploadFile = File(...)):
    """Parse → security-scan → index → persist a document into a workspace."""
    ws = await get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    raw_file_bytes = await file.read()
    filename = file.filename or "upload"
    file_type = doc_store.detect_file_type(filename)

    try:
        extracted_text = extract_text(raw_file_bytes, file_type)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse document: {e}")

    try:
        guard_result = await content_guard.scan(extracted_text)
    except Exception as e:
        logger.error("Content guard failed for %s: %s", filename, e, exc_info=True)
        try:
            await insert_audit_record(
                document_id=f"guard_error:{workspace_id}:{uuid4()}",
                verdict="BLOCKED",
                patterns_hit=["guard_unavailable"],
                llm_reason="Content guard unavailable during upload",
            )
        except Exception as audit_err:
            logger.error(
                "Failed to persist guard failure audit: %s", audit_err, exc_info=True
            )
        raise HTTPException(
            status_code=503, detail="Document security scan unavailable. Please retry."
        )

    guard_status = "clean"
    file_bytes_for_index = raw_file_bytes
    if guard_result:
        guard_status = guard_result.verdict.lower()
        if guard_result.verdict == "BLOCKED":
            await insert_audit_record(
                document_id=f"blocked:{workspace_id}:{uuid4()}",
                verdict=guard_result.verdict,
                patterns_hit=guard_result.patterns_hit,
                llm_reason=guard_result.llm_reason or None,
            )
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Document blocked by security guard: "
                    f"{guard_result.llm_reason or 'Malicious content detected'}"
                ),
            )
        if guard_result.verdict == "FLAGGED" and guard_result.sanitized_text:
            # Re-embed only sanitized plain text to avoid persisting untrusted directives.
            file_type = "txt"
            file_bytes_for_index = guard_result.sanitized_text.encode("utf-8")

    doc_id = await create_document(
        workspace_id=workspace_id,
        filename=filename,
        file_type=file_type,
        chunk_count=0,
        guard_status=guard_status,
        status="pending",
    )

    if guard_result:
        await insert_audit_record(
            document_id=doc_id,
            verdict=guard_result.verdict,
            patterns_hit=guard_result.patterns_hit,
            llm_reason=guard_result.llm_reason or None,
        )

    try:
        chunk_count, embedded_count = await doc_store.index_document(
            workspace_id=workspace_id,
            doc_id=doc_id,
            filename=filename,
            file_bytes=file_bytes_for_index,
            file_type=file_type,
        )
        if chunk_count > 0 and embedded_count == 0:
            await update_document_chunks(doc_id, 0, status="error")
            raise RuntimeError(
                "Embedding produced 0 vectors — check GEMINI_API_KEY and the embed_model setting."
            )
        await update_document_chunks(doc_id, embedded_count, status="ready")
    except Exception as e:
        logger.error("Indexing failed for doc %s: %s", doc_id, e, exc_info=True)
        try:
            await update_document_chunks(doc_id, 0, status="error")
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Document indexing failed: {e}")

    return {
        "doc_id": doc_id,
        "filename": filename,
        "file_type": file_type,
        "chunk_count": embedded_count,
        "guard_status": guard_status,
    }


@router.get("/workspaces/{workspace_id}/documents")
async def list_documents_api(workspace_id: str):
    ws = await get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return await list_documents(workspace_id)


@router.delete("/workspaces/{workspace_id}/documents/{doc_id}")
async def delete_document_api(workspace_id: str, doc_id: str):
    doc = await get_document(doc_id)
    if not doc or doc["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="Document not found")
    vs.delete_document(workspace_id, doc_id)
    await delete_document_db(doc_id)
    return {"deleted": True, "doc_id": doc_id}


@router.post("/workspaces/{workspace_id}/query")
async def query_workspace_api(workspace_id: str, req: WorkspaceQueryReq):
    ws = await get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    context = await rag_retriever.retrieve(workspace_id, req.query, top_k=req.top_k)
    return {"workspace_id": workspace_id, "query": req.query, "context": context}
