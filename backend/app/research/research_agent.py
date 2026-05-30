import json
import logging
from typing import Any, AsyncIterator, Optional

from . import web_searcher, research_planner, report_builder
from .research_db import update_research_plan, save_research_report, fail_research_session

logger = logging.getLogger(__name__)


def _event(event_type: str, **kwargs: Any) -> str:
    """Serialise an SSE data payload."""
    return json.dumps({"type": event_type, **kwargs})


async def run_research(
    research_id: str,
    question: str,
    workspace_id: Optional[str],
) -> AsyncIterator[str]:
    """
    Async generator that executes the full research pipeline and yields SSE
    JSON event strings.

    Event types emitted (all as SSE `data:` lines):
      planning      — LLM is generating search queries
      planned       — queries ready; payload: {queries: [str]}
      searching     — about to issue a web search; payload: {query: str, index: int, total: int}
      search_result — one query done; payload: {query: str, result_count: int}
      rag           — document retrieval running (only if workspace_id provided)
      building      — LLM is synthesising the report
      done          — report ready; payload: {report_md: str, sources: [...]}
      error         — something failed; payload: {message: str}
    """
    try:
        # ── Step 1: Generate search plan ───────────────────────────────────────
        yield _event("planning", message="Generating search plan...")
        try:
            queries = await research_planner.plan_queries(question)
        except Exception as e:
            logger.error("Planning failed for %s: %s", research_id, e)
            queries = [question]

        await update_research_plan(research_id, queries)
        yield _event("planned", queries=queries)

        # ── Step 2: Execute searches ────────────────────────────────────────────
        all_results = []
        for idx, query in enumerate(queries):
            yield _event("searching", query=query, index=idx + 1, total=len(queries))
            results = await web_searcher.search(query, max_results=5)
            all_results.extend(results)
            yield _event("search_result", query=query, result_count=len(results))

        # De-duplicate by URL
        all_results = web_searcher.deduplicate(all_results)

        # ── Step 3: RAG document context (optional) ─────────────────────────────
        rag_context = ""
        if workspace_id:
            yield _event("rag", message="Retrieving document context...")
            try:
                from ..rag import rag_retriever
                rag_sources = await rag_retriever.retrieve_sources(workspace_id, question)
                rag_context = rag_retriever.format_context(rag_sources)
            except Exception as e:
                logger.warning("RAG retrieval failed during research: %s", e)

        # ── Step 4: Synthesise report ───────────────────────────────────────────
        yield _event("building", message="Building research report...")
        try:
            report_md = await report_builder.build_report(question, all_results, rag_context)
        except Exception as e:
            logger.error("Report building failed for %s: %s", research_id, e)
            report_md = f"# Research: {question}\n\nReport generation failed: {e}"

        # ── Step 5: Persist results ─────────────────────────────────────────────
        await save_research_report(research_id, report_md, all_results)

        yield _event("done", report_md=report_md, sources=all_results)

    except Exception as e:
        logger.error("Research agent error for %s: %s", research_id, e, exc_info=True)
        try:
            await fail_research_session(research_id, str(e))
        except Exception:
            pass
        yield _event("error", message=str(e))
