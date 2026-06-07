"""
Research report builder.

Assembles a single LLM call that turns the available context into a
markdown report. The pipeline supplies:

  results      — deduplicated web search results, each potentially
                 enriched with a `body` field by `source_fetcher`.
  rag_context  — excerpts from the user's workspace documents.

The report builder is intentionally thin: it formats the context blocks
and hands them to the LLM. The intelligence belongs upstream (planner,
source fetcher) and in the model itself.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

from ..llm_client import llm_chat

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts" / "research"

MAX_SOURCES_IN_PROMPT = 10
SOURCE_BODY_CHAR_BUDGET = 2200
SOURCE_SNIPPET_FALLBACK_CHARS = 600


def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def _format_sources(results: List[Dict[str, Any]]) -> str:
    """Number each source [N] and include extracted body when available."""
    blocks: List[str] = []
    for i, r in enumerate(results[:MAX_SOURCES_IN_PROMPT], 1):
        title = (r.get("title") or "").strip() or "(untitled)"
        url = (r.get("url") or "").strip()
        body = (r.get("body") or "").strip()
        if body:
            text = body[:SOURCE_BODY_CHAR_BUDGET]
            if len(body) > SOURCE_BODY_CHAR_BUDGET:
                text += " …[truncated]"
            label = "Content"
        else:
            text = (r.get("snippet") or "")[:SOURCE_SNIPPET_FALLBACK_CHARS]
            label = "Snippet"
        blocks.append(f"[{i}] {title}\nURL: {url}\n{label}: {text}")
    return "\n\n".join(blocks)


def _build_user_message(
    question: str,
    sources_block: str,
    rag_context: str,
) -> str:
    parts: List[str] = [f"USER QUESTION: {question}"]
    if sources_block:
        parts.append("SOURCES:\n" + sources_block)
    if rag_context:
        parts.append("DOCUMENTS:\n" + rag_context)
    return "\n\n".join(parts)


def _fallback_report(question: str, results: List[Dict[str, Any]]) -> str:
    source_list = "\n".join(
        f"{i}. [{(r.get('title') or 'Source').strip()}]({(r.get('url') or '').strip()})"
        for i, r in enumerate(results, 1)
        if r.get("url")
    )
    return (
        f"# {question}\n\n"
        "Report generation failed at the LLM step. The retrieved sources "
        "are listed below.\n\n"
        f"## Sources\n{source_list or '(none)'}"
    )


async def build_report(
    question: str,
    results: List[Dict[str, Any]],
    rag_context: str = "",
) -> str:
    """Single LLM call returning a markdown research report."""
    if not results and not rag_context:
        return (
            f"# {question}\n\n"
            "No web sources or workspace documents were retrieved for this "
            "question."
        )

    system_prompt = _load_prompt("report_builder.txt")
    sources_block = _format_sources(results)
    user_content = _build_user_message(question, sources_block, rag_context)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    try:
        report = await llm_chat(messages, timeout_s=180)
    except Exception as e:
        logger.error("Report builder LLM call failed: %s", e)
        return _fallback_report(question, results)
    return report.strip() or _fallback_report(question, results)
