import asyncio
import logging
import os
import re
import time

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .modes.loader import load_modes

from .db import (
    init_db,
    create_session,
    list_sessions,
    get_session,
    add_message,
    get_messages,
    list_memory_items,
    upsert_memory_item,
    delete_memory_item,
    get_session_summary,
    count_messages,
    list_alerts,
    update_alert_status,
    list_tool_settings,
    upsert_tool_setting,
    get_due_alerts,
    # Feature 1 — RAG Workspace
    create_workspace,
    list_workspaces,
    get_workspace,
    delete_workspace_db,
    create_document,
    list_documents,
    get_document,
    delete_document_db,
    update_document_chunks,
    create_chat_job,
    get_chat_job,
    fail_chat_job,
)

from .security import content_guard
from .security.guard_db import insert_audit_record, get_audit_by_doc, list_audit_records

from .tools.bootstrap import build_tools_registry

from .llm_client import llm_chat, init_llm_client, close_llm_client
from .config import get_settings
from .chat_jobs import ChatJobEngine

# Feature 1 — RAG imports
from .rag import document_store as doc_store
from .rag import rag_retriever
from .rag import vector_store as vs
from .rag.parsers import extract_text

# Feature 2 — Research imports
from .research import research_agent
from .research.research_db import (
    create_research_session,
    get_research_session,
    list_research_sessions,
)

TOOLS_REGISTRY = build_tools_registry()

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
logger = logging.getLogger(__name__)
CHAT_JOB_ENGINE: ChatJobEngine | None = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

settings = get_settings()

# Load AssistantModes at startup (replaces PERSONAS)
MODES = load_modes()


@app.on_event("startup")
async def _startup():
    await init_db()
    await init_llm_client()
    global CHAT_JOB_ENGINE
    CHAT_JOB_ENGINE = ChatJobEngine(settings=settings, modes=MODES, tools_registry=TOOLS_REGISTRY)
    await CHAT_JOB_ENGINE.start()


@app.on_event("shutdown")
async def _shutdown():
    global CHAT_JOB_ENGINE
    if CHAT_JOB_ENGINE:
        await CHAT_JOB_ENGINE.stop()
        CHAT_JOB_ENGINE = None
    await close_llm_client()


# ─────────────────────────────────────────────────────────────────────────────
# System Prompt Builder
# ─────────────────────────────────────────────────────────────────────────────

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_mode_prompt(mode_id: str) -> str | None:
    """Load a mode's base system prompt from prompts/modes/<mode_id>.txt."""
    prompt_file = _PROMPTS_DIR / "modes" / f"{mode_id}.txt"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8").strip()
    return None


def build_system_prompt(
    mode: Dict[str, Any],
    memory_items: List[Dict[str, Any]] | None = None,
    tools: List[Any] | None = None,
    rag_context: str = "",
) -> str:
    """
    Builds the LLM system prompt from an AssistantMode and runtime context.

    The static personality/rules section is loaded from
    prompts/modes/<mode_id>.txt. Dynamic context (memory items, RAG/web
    results) is appended at runtime.

    Falls back to deriving rules from the mode's policy fields if no prompt
    file exists for the given mode_id.
    """
    today_str = datetime.utcnow().strftime("%B %d, %Y")
    mode_id = mode.get("id", "")
    base = _load_mode_prompt(mode_id)

    if base:
        parts = [f"Today's date is {today_str} (UTC).", base]
    else:
        # Fallback: derive rules from policy fields
        rp = mode.get("response_policy", {})
        mp = mode.get("memory_policy", {})
        sp = mode.get("safety_policy", {})
        empathy = rp.get("empathy_level", 0.5)
        directness = rp.get("directness_level", 0.5)
        verbosity = rp.get("verbosity", "short")
        fmt = rp.get("format", "freeform")
        tone = rp.get("tone", "neutral")

        rules = []
        rules.append(f"You are operating in '{mode['name']}' mode: {mode['description']}")
        rules.append(f"Empathy level: {empathy} (0=detached, 1=highly empathetic).")
        rules.append(f"Directness level: {directness} (0=indirect, 1=very direct).")
        rules.append(f"Tone: {tone}.")
        rules.append("You are a helpful AI assistant. Always reply in plain natural language. Never output tool names, JSON, or structured function calls in your response.")
        if tools:
            tool_names = ", ".join(t.name for t in tools)
            rules.append(f"You have access to these tools when the user explicitly asks: {tool_names}. Only invoke a tool when clearly requested — never for greetings, small talk, or general questions.")
        if verbosity == "short":
            rules.append("Keep responses concise. Avoid long essays.")
        elif verbosity == "long":
            rules.append("Provide thorough, detailed responses when helpful.")
        else:
            rules.append("Responses may be moderately detailed when helpful.")
        if fmt == "steps":
            rules.append("Prefer numbered steps and clear next actions.")
        elif fmt == "bullets":
            rules.append("Prefer bullet points.")
        else:
            rules.append("Use natural paragraphs when appropriate.")
        if mp.get("enabled"):
            scope = mp.get("scope", "session")
            rules.append(f"Memory is enabled. Scope: {scope}. Only use user-provided facts/preferences.")
        else:
            rules.append("Memory is disabled. Do not claim to remember past sessions.")
        if sp.get("no_deception", True):
            rules.append("Do not pretend to be sentient or claim real-world experiences.")
        if sp.get("no_dependency", True):
            rules.append("Avoid encouraging emotional dependency. Be supportive but not possessive.")
        if sp.get("no_medical_legal_claims", True):
            rules.append("Do not provide medical or legal advice as definitive. Recommend professional help when appropriate.")
        parts = [f"Today's date is {today_str} (UTC).", "\n".join([f"- {r}" for r in rules])]

    if memory_items:
        mem_lines = ["Memory Context (user-provided facts/preferences):"]
        for m in memory_items[:20]:
            mem_lines.append(f"- {m['key']}: {m['value']} (scope={m['scope']})")
        parts.append("\n".join(mem_lines))

    if rag_context:
        is_web = "[Web Search Results]" in rag_context
        if is_web:
            parts.append("You have been given live web search results below. Read ALL of them carefully and give a comprehensive answer that covers every relevant item found. Do not say 'no specific details' or 'not mentioned' — just summarise what the results say:")
        else:
            parts.append("Answer using the information below. Reply naturally without referencing where the information came from:")
        parts.append(rag_context)

    return "\n\n".join(parts)


_RISK_PATTERNS = [
    re.compile(r"\b(suicide|self[- ]harm|kill myself|hurt myself)\b", re.IGNORECASE),
    re.compile(r"\b(make a bomb|explosive|weapon|poison)\b", re.IGNORECASE),
    re.compile(r"\b(hack|phishing|malware|ransomware|exploit)\b", re.IGNORECASE),
    re.compile(r"\b(medical advice|legal advice|diagnose|prescription)\b", re.IGNORECASE),
    re.compile(r"\b(override|ignore previous|system prompt|jailbreak)\b", re.IGNORECASE),
]


def _risk_triggered(text: str) -> bool:
    return any(p.search(text or "") for p in _RISK_PATTERNS)


def _ms_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000.0, 2)


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response Models
# ─────────────────────────────────────────────────────────────────────────────

class CreateSessionReq(BaseModel):
    mode_id: str = Field(..., description="AssistantMode ID (e.g. 'focus', 'research')")

class ChatSendReq(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1, max_length=4000)
    workspace_id: Optional[str] = Field(None, description="Optional workspace for RAG context injection")
    mode_id: Optional[str] = Field(None, description="Override session mode for this message (e.g. switching modes mid-conversation)")

class MemoryUpsertReq(BaseModel):
    scope: str = Field(..., pattern="^(global|session)$")
    key: str = Field(..., min_length=1, max_length=64)
    value: str = Field(..., min_length=1, max_length=400)
    confidence: float = Field(0.8, ge=0.0, le=1.0)
    session_id: str | None = None

class CreateAlertReq(BaseModel):
    scope: str = Field("session", pattern="^(global|session)$")
    session_id: str | None = None
    title: str = Field(..., min_length=1, max_length=120)
    message: str = Field(..., min_length=1, max_length=500)

class ToolSettingUpsertReq(BaseModel):
    scope: str = Field(..., pattern="^(global|session)$")
    tool_id: str = Field(..., min_length=1, max_length=64)
    enabled: bool
    session_id: str | None = None

class CreateWorkspaceReq(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=500)

class WorkspaceQueryReq(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(3, ge=1, le=10)

class ScanTextReq(BaseModel):
    text: str = Field(..., min_length=1, max_length=100_000)
    document_id: str | None = Field(None)

class StartResearchReq(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    workspace_id: Optional[str] = Field(None)

class SaveResearchReq(BaseModel):
    session_id: str = Field(..., description="Chat session to save memory into")
    scope: str = Field("global", pattern="^(global|session)$")


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


# ─────────────────────────────────────────────────────────────────────────────
# AssistantModes (replaces /personas)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/modes")
def list_modes_api():
    """Returns all loaded AssistantMode definitions."""
    return [m.model_dump() for m in MODES.values()]


@app.get("/modes/{mode_id}")
def get_mode_api(mode_id: str):
    """Returns a single AssistantMode by ID."""
    mode = MODES.get(mode_id)
    if not mode:
        raise HTTPException(status_code=404, detail="Mode not found")
    return mode.model_dump()


# ─────────────────────────────────────────────────────────────────────────────
# Sessions
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/sessions")
async def create_session_api(req: CreateSessionReq):
    if req.mode_id not in MODES:
        raise HTTPException(status_code=400, detail=f"Invalid mode_id '{req.mode_id}'. Available: {list(MODES.keys())}")
    session_id = await create_session(req.mode_id)
    return {"session_id": session_id}


@app.get("/sessions")
async def list_sessions_api():
    return await list_sessions()


@app.get("/sessions/{session_id}/messages")
async def get_session_messages_api(session_id: str, limit: int = 50):
    s = await get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await get_messages(session_id, limit=limit)
    return {"session": s, "messages": messages}


@app.get("/sessions/{session_id}/summary")
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
            "next_update_at": ((msg_count // settings.summary_cadence) + 1) * settings.summary_cadence,
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# Memory
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/memory")
async def list_memory_api(scope: str = "global", session_id: str | None = None, limit: int = 50):
    if scope not in ("global", "session"):
        raise HTTPException(status_code=400, detail="scope must be 'global' or 'session'")
    return await list_memory_items(scope=scope, session_id=session_id, limit=limit)


@app.post("/memory")
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


@app.delete("/memory/{mem_id}")
async def delete_memory_api(mem_id: str):
    ok = await delete_memory_item(mem_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory item not found")
    return {"deleted": True}


# ─────────────────────────────────────────────────────────────────────────────
# Chat
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/chat/send")
async def chat_send_api(req: ChatSendReq):
    request_started = time.perf_counter()
    timings_ms: Dict[str, float] = {}

    load_started = time.perf_counter()
    s = await get_session(req.session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    # Allow per-request mode override (e.g. user switching modes mid-conversation)
    mode_id = req.mode_id if (req.mode_id and req.mode_id in MODES) else s["mode_id"]
    mode_obj = MODES.get(mode_id)
    if not mode_obj:
        raise HTTPException(status_code=500, detail=f"Session mode '{mode_id}' not found in registry")

    # Convert to plain dict for downstream compatibility
    mode = mode_obj.model_dump()

    # Load memory items according to mode's memory policy
    mem_items: List[Dict[str, Any]] = []
    mem_policy = mode.get("memory_policy", {})
    if mem_policy.get("enabled"):
        scope = mem_policy.get("scope", "session")
        if scope == "global":
            mem_items = await list_memory_items(scope="global", session_id=None, limit=50)
        else:
            global_mem_task = asyncio.create_task(
                list_memory_items(scope="global", session_id=None, limit=50)
            )
            session_mem_task = asyncio.create_task(
                list_memory_items(scope="session", session_id=req.session_id, limit=50)
            )
            global_mem, session_mem = await asyncio.gather(global_mem_task, session_mem_task)
            mem_items = global_mem + session_mem
    timings_ms["session_memory_load"] = _ms_since(load_started)

    persistence_started = time.perf_counter()
    await add_message(req.session_id, "user", req.message)

    msgs = await get_messages(req.session_id, limit=50)
    history = [{"role": m["role"], "content": m["content"]} for m in msgs if m["role"] in ("user", "assistant")]

    # RAG context injection (Feature 1)
    rag_started = time.perf_counter()
    rag_context = ""
    rag_sources: List[Dict[str, Any]] = []
    if req.workspace_id:
        try:
            rag_sources = await rag_retriever.retrieve_sources(req.workspace_id, req.message)
            rag_context = rag_retriever.format_context(rag_sources)
        except Exception as e:
            logger.warning("RAG retrieval failed for workspace %s: %s", req.workspace_id, e)
    timings_ms["rag_retrieval"] = _ms_since(rag_started)

    mode_id = mode.get("id", "")

    # ── Deep Research mode — full pipeline ───────────────────────────────────
    if mode_id == "research":
        try:
            from .research import web_searcher, research_planner, report_builder
            research_started = time.perf_counter()

            # Step 1: Plan sub-queries
            queries = await research_planner.plan_queries(req.message)
            logger.info("Research plan for '%s': %s", req.message[:60], queries)

            # Step 2: Run all sub-queries in parallel-ish (sequential, capped)
            # Use more results per query for list/recommend/compare questions
            _list_keywords = ("list", "recommend", "compare", "best", "top", "which", "pros", "cons")
            is_recommendation_query = any(kw in req.message.lower() for kw in _list_keywords)
            results_per_query = 6 if is_recommendation_query else 4

            all_results = []
            for q in queries[:4]:  # cap at 4 to keep latency reasonable
                results = await web_searcher.search(q, max_results=results_per_query)
                all_results.extend(results)
            all_results = web_searcher.deduplicate(all_results)

            # Step 3: Synthesise report (uses report_builder LLM prompt)
            final_text = await report_builder.build_report(req.message, all_results, rag_context)
            timings_ms["research_pipeline"] = _ms_since(research_started)
            logger.info("Deep research completed in %.0f ms, %d sources", timings_ms["research_pipeline"], len(all_results))

        except Exception as e:
            logger.error("Deep research pipeline failed: %s", e)
            final_text = f"Research pipeline encountered an error: {e}. Please try again."

        await add_message(req.session_id, "assistant", final_text)
        timings_ms["persistence"] = _ms_since(persistence_started)

        return {
            "session_id": req.session_id,
            "assistant": final_text,
            "rag_used": bool(rag_sources),
            "sources": rag_sources,
            "web_sources": all_results,
            "tool_events": [],
            "timings_ms": timings_ms,
        }

    # ── Web Search mode — single search + chat ───────────────────────────────
    web_context = ""
    if mode_id == "focus":
        try:
            from .research.web_searcher import search as web_search
            web_results = await web_search(req.message, max_results=8)
            if web_results:
                lines = ["[Web Search Results]"]
                for i, r in enumerate(web_results, 1):
                    lines.append(f"{i}. {r['title']}")
                    lines.append(f"   {r['snippet']}")
                    lines.append(f"   URL: {r['url']}")
                web_context = "\n".join(lines)
        except Exception as e:
            logger.warning("Web search failed: %s", e)

    combined_context = (rag_context + "\n\n" + web_context).strip() if (rag_context and web_context) else (web_context or rag_context)

    all_tools = TOOLS_REGISTRY.list_tools()
    system_prompt = build_system_prompt(mode, mem_items, tools=all_tools, rag_context=combined_context)
    current_history = history[:-1]

    try:
        llm_started = time.perf_counter()
        messages = [{"role": "system", "content": system_prompt}] + current_history + [{"role": "user", "content": req.message}]
        final_text = await llm_chat(messages)
        timings_ms["llm_draft"] = _ms_since(llm_started)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM call failed: {e}")

    await add_message(req.session_id, "assistant", final_text)
    timings_ms["persistence"] = _ms_since(persistence_started)

    enqueue_started = time.perf_counter()
    job = await create_chat_job(
        session_id=req.session_id,
        mode_id=mode_id,
        user_message=req.message,
        assistant_final=final_text,
        max_retries=settings.chat_jobs_max_retries,
    )
    queue_error = None
    if not CHAT_JOB_ENGINE or not CHAT_JOB_ENGINE.enqueue_nowait(job["id"]):
        queue_error = "queue_unavailable_or_full"
        await fail_chat_job(job["id"], queue_error)
    timings_ms["queue_enqueue"] = _ms_since(enqueue_started)
    timings_ms["total"] = _ms_since(request_started)

    pipeline_debug: Dict[str, Any] = {
        "status": "queued" if not queue_error else "failed",
        "job_id": job["id"],
        "queued_at": job["queued_at"],
    }
    if queue_error:
        pipeline_debug["error"] = queue_error

    logger.info(
        "chat_send_timing session=%s mode=%s rag=%s timings_ms=%s",
        req.session_id,
        mode_id,
        bool(rag_sources),
        timings_ms,
    )

    return {
        "session_id": req.session_id,
        "mode_id": mode_id,
        "assistant": final_text,
        "rag_used": bool(rag_sources),
        "sources": rag_sources,
        "pipeline": pipeline_debug,
        "tool_events": [],
        "timings_ms": timings_ms,
    }


@app.get("/chat/jobs/{job_id}")
async def get_chat_job_api(job_id: str):
    job = await get_chat_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Chat job not found")
    return {
        "job_id": job["id"],
        "status": job["status"],
        "attempts": job["attempts"],
        "queued_at": job["queued_at"],
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "pipeline_result": job.get("pipeline_result"),
        "tool_events": job.get("tool_events"),
        "error": job.get("last_error"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Alerts
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/alerts")
async def list_alerts_api(scope: str = "global", session_id: str | None = None, status: str | None = None, limit: int = 50):
    if scope not in ("global", "session"):
        raise HTTPException(status_code=400, detail="scope must be 'global' or 'session'")
    if scope == "global":
        return await list_alerts(scope="global", status=status, limit=limit)
    return await list_alerts(scope="session", session_id=session_id, status=status, limit=limit)

@app.post("/alerts/{alert_id}/done")
async def mark_alert_done_api(alert_id: str):
    ok = await update_alert_status(alert_id, "done")
    if not ok:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"ok": True}

@app.post("/alerts/{alert_id}/cancel")
async def mark_alert_cancel_api(alert_id: str):
    ok = await update_alert_status(alert_id, "cancelled")
    if not ok:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"ok": True}

@app.get("/alerts/due")
async def get_due_alerts_api(session_id: str | None = None, limit: int = 10):
    return await get_due_alerts(session_id=session_id, limit=limit)


# ─────────────────────────────────────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/tools")
def list_tools_api():
    return [{"tool_id": t.id, "name": t.name, "description": t.description} for t in TOOLS_REGISTRY.list_tools()]

@app.get("/tools/settings")
async def list_tool_settings_api(scope: str = "global", session_id: str | None = None):
    if scope not in ("global", "session"):
        raise HTTPException(status_code=400, detail="scope must be global|session")
    if scope == "session" and not session_id:
        raise HTTPException(status_code=400, detail="session_id is required for session scope")
    return await list_tool_settings(scope=scope, session_id=session_id)

@app.put("/tools/settings")
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


# ─────────────────────────────────────────────────────────────────────────────
# Security / Content Guard
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/security/scan")
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

@app.get("/security/audit")
async def list_audit_api(verdict: str | None = None, limit: int = 100):
    if verdict and verdict not in ("CLEAN", "FLAGGED", "BLOCKED"):
        raise HTTPException(status_code=400, detail="verdict must be CLEAN, FLAGGED, or BLOCKED")
    return await list_audit_records(verdict_filter=verdict, limit=limit)

@app.get("/security/audit/{document_id}")
async def get_audit_by_doc_api(document_id: str):
    record = await get_audit_by_doc(document_id)
    if not record:
        raise HTTPException(status_code=404, detail="No audit record found for this document")
    return record


# ─────────────────────────────────────────────────────────────────────────────
# Feature 1 — RAG Document Workspaces
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/workspaces")
async def create_workspace_api(req: CreateWorkspaceReq):
    """Creates a new workspace."""
    ws_id = await create_workspace(name=req.name, description=req.description)
    return {"workspace_id": ws_id, "name": req.name, "description": req.description}


@app.get("/workspaces")
async def list_workspaces_api():
    """Lists all workspaces."""
    return await list_workspaces()


@app.delete("/workspaces/{workspace_id}")
async def delete_workspace_api(workspace_id: str):
    """Deletes a workspace, its DB documents, and its ChromaDB collection."""
    ws = await get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    vs.delete_workspace(workspace_id)
    await delete_workspace_db(workspace_id)
    return {"deleted": True, "workspace_id": workspace_id}


@app.post("/workspaces/{workspace_id}/documents")
async def upload_document_api(workspace_id: str, file: UploadFile = File(...)):
    """
    Uploads and indexes a document into a workspace.

    Pipeline:
      1. Security guard scan (content_guard).
      2. If BLOCKED, reject with 400.
      3. If FLAGGED, use sanitized text.
      4. Index into ChromaDB via document_store.
      5. Create a DB record with chunk_count.
    """
    ws = await get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")

    raw_file_bytes = await file.read()
    filename = file.filename or "upload"
    file_type = doc_store.detect_file_type(filename)

    # Parse file content first, then run content guard on extracted text.
    try:
        extracted_text = extract_text(raw_file_bytes, file_type)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse document: {e}")

    # Security gate
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
            logger.error("Failed to persist guard failure audit: %s", audit_err, exc_info=True)
        raise HTTPException(status_code=503, detail="Document security scan unavailable. Please retry.")

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
            raise HTTPException(status_code=400, detail=f"Document blocked by security guard: {guard_result.llm_reason or 'Malicious content detected'}")
        if guard_result.verdict == "FLAGGED" and guard_result.sanitized_text:
            # Parse sanitized text as plain text to avoid re-embedding untrusted directives.
            file_type = "txt"
            file_bytes_for_index = guard_result.sanitized_text.encode("utf-8")

    # Create DB record as pending before indexing.
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

    # Index into ChromaDB
    try:
        chunk_count, embedded_count = await doc_store.index_document(
            workspace_id=workspace_id,
            doc_id=doc_id,
            filename=filename,
            file_bytes=file_bytes_for_index,
            file_type=file_type,
        )
        if chunk_count > 0 and embedded_count == 0:
            # Parsed but embedding completely failed — mark as error so user knows
            await update_document_chunks(doc_id, 0, status="error")
            raise RuntimeError("Embedding produced 0 vectors — check GEMINI_API_KEY and the embed_model setting.")
        await update_document_chunks(doc_id, embedded_count, status="ready")
    except Exception as e:
        logger.error("Indexing failed for doc %s: %s", doc_id, e, exc_info=True)
        # Mark as error (don't delete — user can see it failed and retry)
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


@app.get("/workspaces/{workspace_id}/documents")
async def list_documents_api(workspace_id: str):
    """Lists all documents in a workspace."""
    ws = await get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return await list_documents(workspace_id)


@app.delete("/workspaces/{workspace_id}/documents/{doc_id}")
async def delete_document_api(workspace_id: str, doc_id: str):
    """Removes a document from DB and ChromaDB."""
    doc = await get_document(doc_id)
    if not doc or doc["workspace_id"] != workspace_id:
        raise HTTPException(status_code=404, detail="Document not found")
    vs.delete_document(workspace_id, doc_id)
    await delete_document_db(doc_id)
    return {"deleted": True, "doc_id": doc_id}


@app.post("/workspaces/{workspace_id}/query")
async def query_workspace_api(workspace_id: str, req: WorkspaceQueryReq):
    """Standalone RAG query — returns relevant chunks without a chat session."""
    ws = await get_workspace(workspace_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    context = await rag_retriever.retrieve(workspace_id, req.query, top_k=req.top_k)
    return {"workspace_id": workspace_id, "query": req.query, "context": context}


# ─────────────────────────────────────────────────────────────────────────────
# Feature 2 — Research Mode
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/research")
async def start_research_api(req: StartResearchReq):
    """Creates a new research session and returns its ID. Connect to /research/{id}/stream to run it."""
    research_id = await create_research_session(
        question=req.question,
        workspace_id=req.workspace_id,
    )
    return {"research_id": research_id, "question": req.question}


@app.get("/research")
async def list_research_api(limit: int = 50):
    """Lists all past research sessions, newest first."""
    return await list_research_sessions(limit=limit)


@app.get("/research/{research_id}")
async def get_research_api(research_id: str):
    """Returns the status, plan, and report for a research session."""
    session = await get_research_session(research_id)
    if not session:
        raise HTTPException(status_code=404, detail="Research session not found")
    return session


@app.get("/research/{research_id}/stream")
async def research_stream_api(research_id: str):
    """
    SSE endpoint. Connecting here runs the full research pipeline for the given
    session and streams progress events as they happen.
    """
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


@app.post("/research/{research_id}/save")
async def save_research_api(research_id: str, req: SaveResearchReq):
    """Saves a completed research report as a memory item in the given chat session."""
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
