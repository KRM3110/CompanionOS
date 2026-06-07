import asyncio
import logging
import time
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from .. import state
from ..db import (
    add_message,
    create_chat_job,
    fail_chat_job,
    get_chat_job,
    get_messages,
    get_session,
    list_memory_items,
)
from ..llm_client import llm_chat
from ..prompt_builder import build_system_prompt
from ..rag import rag_retriever
from .schemas import ChatSendReq

router = APIRouter()
logger = logging.getLogger(__name__)


def _ms_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000.0, 2)


@router.post("/chat/send")
async def chat_send_api(req: ChatSendReq):
    request_started = time.perf_counter()
    timings_ms: Dict[str, float] = {}

    load_started = time.perf_counter()
    s = await get_session(req.session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    mode_id = req.mode_id if (req.mode_id and req.mode_id in state.MODES) else s["mode_id"]
    mode_obj = state.MODES.get(mode_id)
    if not mode_obj:
        raise HTTPException(
            status_code=500, detail=f"Session mode '{mode_id}' not found in registry"
        )

    mode = mode_obj.model_dump()

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
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in msgs
        if m["role"] in ("user", "assistant")
    ]

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

    if mode_id == "research":
        try:
            from ..research import report_builder, research_planner, web_searcher

            research_started = time.perf_counter()
            queries = await research_planner.plan_queries(req.message)
            logger.info("Research plan for '%s': %s", req.message[:60], queries)

            _list_keywords = ("list", "recommend", "compare", "best", "top", "which", "pros", "cons")
            is_recommendation_query = any(kw in req.message.lower() for kw in _list_keywords)
            results_per_query = 6 if is_recommendation_query else 4

            all_results: List[Dict[str, Any]] = []
            for q in queries[:4]:
                results = await web_searcher.search(q, max_results=results_per_query)
                all_results.extend(results)
            all_results = web_searcher.deduplicate(all_results)

            final_text = await report_builder.build_report(req.message, all_results, rag_context)
            timings_ms["research_pipeline"] = _ms_since(research_started)
            logger.info(
                "Deep research completed in %.0f ms, %d sources",
                timings_ms["research_pipeline"],
                len(all_results),
            )
        except Exception as e:
            logger.error("Deep research pipeline failed: %s", e)
            final_text = f"Research pipeline encountered an error: {e}. Please try again."
            all_results = []

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

    web_context = ""
    focus_web_results: List[Dict[str, Any]] = []
    facts_context = ""
    if mode_id == "focus":
        try:
            from ..research.web_searcher import search as web_search

            focus_web_results = await web_search(req.message, max_results=8)
            if focus_web_results:
                lines = ["[Web Search Results]"]
                for i, r in enumerate(focus_web_results, 1):
                    lines.append(f"{i}. {r['title']}")
                    lines.append(f"   {r['snippet']}")
                    lines.append(f"   URL: {r['url']}")
                web_context = "\n".join(lines)
        except Exception as e:
            logger.warning("Web search failed: %s", e)

        # Typed retrievers: a small classifier LLM decides whether the message
        # needs authoritative version / release data and which registry to
        # hit. Returns a markdown table the chat model can copy directly.
        # No-op (silent) for conceptual / how-to / chitchat messages.
        try:
            from ..research import typed_retrievers

            facts_result = await typed_retrievers.gather_facts(req.message)
            if facts_result.has_facts:
                facts_context = "[AUTHORITATIVE FACTS]\n" + facts_result.text
        except Exception as e:
            logger.warning("Typed retrievers failed in focus mode: %s", e)

    # Context order matters for model attention: earliest blocks are oldest
    # in working memory. RAG comes first (long-lived workspace context),
    # then web search results (transient), then FACTS last so authoritative
    # data is the model's most-recent input before generation.
    context_blocks = [rag_context, web_context, facts_context]
    combined_context = "\n\n".join(b for b in context_blocks if b)

    all_tools = state.TOOLS_REGISTRY.list_tools()
    system_prompt = build_system_prompt(
        mode, mem_items, tools=all_tools, rag_context=combined_context
    )
    current_history = history[:-1]

    try:
        llm_started = time.perf_counter()
        messages = (
            [{"role": "system", "content": system_prompt}]
            + current_history
            + [{"role": "user", "content": req.message}]
        )
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
        max_retries=state.settings.chat_jobs_max_retries,
    )
    queue_error = None
    if not state.CHAT_JOB_ENGINE or not state.CHAT_JOB_ENGINE.enqueue_nowait(job["id"]):
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
        "web_sources": focus_web_results,
        "pipeline": pipeline_debug,
        "tool_events": [],
        "timings_ms": timings_ms,
    }


@router.get("/chat/jobs/{job_id}")
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
