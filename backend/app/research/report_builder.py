import logging
from pathlib import Path
from typing import Any, Dict, List

from ..llm_client import llm_chat

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts" / "research"


def _load_prompt(name: str) -> str:
    """Load a prompt from prompts/research/<name>."""
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def _format_snippets(results: List[Dict[str, Any]], rag_context: str = "") -> str:
    parts: List[str] = []
    # Cap at 8 results — small models lose coherence with too many sources
    for i, r in enumerate(results[:8], 1):
        title = r.get("title", "")
        url = r.get("url", "")
        snippet = r.get("snippet", "")
        # Truncate very long snippets so context fits in the model's window
        if len(snippet) > 800:
            snippet = snippet[:800] + "…"
        parts.append(f"[{i}] {title}\nURL: {url}\nContent: {snippet}")
    if rag_context:
        parts.append(f"[Document Context]\n{rag_context}")
    return "\n\n".join(parts)


async def build_report(
    question: str,
    results: List[Dict[str, Any]],
    rag_context: str = "",
) -> str:
    """
    Ask the LLM to synthesise a structured Markdown research report.

    Args:
        question:    Original research question (used as context for the LLM).
        results:     Merged, de-duplicated list of {title, url, snippet} dicts.
        rag_context: Optional pre-retrieved document context string.

    Returns:
        Markdown-formatted report string.
    """
    if not results and not rag_context:
        return f"# Research: {question}\n\n## Summary\nNo search results were retrieved for this query."

    system_prompt = _load_prompt("report_builder.txt")
    snippets = _format_snippets(results, rag_context)
    user_content = f"Research question: {question}\n\nFINDINGS:\n{snippets}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    try:
        return await llm_chat(messages, timeout_s=120)
    except Exception as e:
        logger.error("Report builder LLM call failed: %s", e)
        # Return a minimal fallback report with sources listed
        source_list = "\n".join(
            f"{i}. [{r.get('title', 'Source')}]({r.get('url', '')})"
            for i, r in enumerate(results, 1)
        )
        return (
            f"# Research: {question}\n\n"
            "## Summary\nReport generation failed due to an LLM error.\n\n"
            f"## Sources\n{source_list}"
        )
