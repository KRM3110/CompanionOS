"""
Research report builder.

Assembles a single LLM call that produces a markdown report from three
optional input streams:

  results      — deduplicated web search results, each potentially
                 enriched with a `body` field by `source_fetcher`. Order
                 reflects search ranking.
  facts        — authoritative structured text from `typed_retrievers`
                 (npm / PyPI / GitHub releases). Treated as ground truth
                 in the prompt and in the post-processing pass below.
  rag_context  — excerpts from the user's workspace documents.

A single call to `llm_chat` produces the report. After generation, the
output is scanned for markdown rows that look like version tables; any
row whose date disagrees with the canonical FACTS value is rewritten.
This is the deterministic safety net for models prone to producing
plausible-but-wrong dates when copying a structured table.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from ..llm_client import llm_chat
from .typed_retrievers import extract_version_date_map

logger = logging.getLogger(__name__)

# Matches a markdown row whose first cell is a version-shaped string and
# whose second cell is a YYYY-MM-DD date. Captures both the values and the
# surrounding whitespace/pipes so a rewrite can reconstruct the row exactly
# without disturbing formatting.
_REPORT_TABLE_ROW_RE = re.compile(
    r"^(\|\s*)(v?\d+\.\d+(?:\.\d+)?(?:-[\w.]+)?)(\s*\|\s*)(\d{4}-\d{2}-\d{2})(\s*\|.*)$",
    re.MULTILINE,
)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts" / "research"

MAX_SOURCES_IN_PROMPT = 10
SOURCE_BODY_CHAR_BUDGET = 2200
SOURCE_SNIPPET_FALLBACK_CHARS = 600


def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def _format_sources(results: List[Dict[str, Any]]) -> str:
    """Number every source [N], include extracted body when present."""
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
    facts: str,
    sources_block: str,
    rag_context: str,
) -> str:
    # Block order matters: the model gives strongest weight to the most
    # recently read context. SOURCES is the citation pool and goes in the
    # middle. FACTS is authoritative and goes LAST so it remains foremost
    # in the model's attention when generation starts.
    parts: List[str] = [f"USER QUESTION: {question}"]

    if sources_block:
        parts.append("SOURCES (numbered — cite with [N] for any claim you draw from them):\n" + sources_block)
    else:
        parts.append("SOURCES: (no web sources retrieved)")
    if rag_context:
        parts.append("DOCUMENTS (user's workspace):\n" + rag_context)
    if facts:
        parts.append(
            "FACTS (authoritative structured data — these OVERRIDE any "
            "contradicting prose in SOURCES; render version lists from here, "
            "not from SOURCES):\n" + facts
        )
    return "\n\n".join(parts)


def _fallback_report(question: str, results: List[Dict[str, Any]]) -> str:
    source_list = "\n".join(
        f"{i}. [{(r.get('title') or 'Source').strip()}]({(r.get('url') or '').strip()})"
        for i, r in enumerate(results, 1)
        if r.get("url")
    )
    return (
        f"# {question}\n\n"
        "**Direct answer.** Report generation failed at the LLM step. "
        "The retrieved sources are listed below — you may want to retry or "
        "consult them directly.\n\n"
        f"## Sources\n{source_list or '(none)'}"
    )


async def build_report(
    question: str,
    results: List[Dict[str, Any]],
    rag_context: str = "",
    facts: str = "",
) -> str:
    """
    Produce a markdown research report grounded in the provided inputs.

    Returns a graceful fallback message when no inputs were supplied or
    when the LLM call fails — callers can render the return value
    directly without checking for None.
    """
    if not results and not rag_context and not facts:
        return (
            f"# {question}\n\n"
            "**Direct answer.** No web sources, no authoritative facts, "
            "and no workspace documents were retrieved for this question. "
            "Try rephrasing with a more specific subject."
        )

    system_prompt = _load_prompt("report_builder.txt")
    sources_block = _format_sources(results)
    user_content = _build_user_message(question, facts, sources_block, rag_context)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    try:
        report = await llm_chat(messages, timeout_s=180)
    except Exception as e:
        logger.error("Report builder LLM call failed: %s", e)
        return _fallback_report(question, results)

    report = report.strip() or _fallback_report(question, results)

    # Post-process: rewrite version-table dates to match the canonical
    # values in FACTS. This compensates for models that re-emit a
    # plausible-looking but incorrect date sequence even when the source
    # table was supplied verbatim. Rows whose date already matches FACTS
    # pass through untouched; rows whose version is not in FACTS are not
    # rewritten (we have no canonical to write).
    if facts:
        canonical = extract_version_date_map(facts)
        if canonical:
            corrections = {"count": 0}

            def _fix_row(m: "re.Match[str]") -> str:
                version = m.group(2)
                canonical_date = canonical.get(version)
                if canonical_date and canonical_date != m.group(4):
                    corrections["count"] += 1
                    return f"{m.group(1)}{version}{m.group(3)}{canonical_date}{m.group(5)}"
                return m.group(0)

            report = _REPORT_TABLE_ROW_RE.sub(_fix_row, report)
            if corrections["count"]:
                logger.info(
                    "Report post-process: corrected %d version-table dates against FACTS.",
                    corrections["count"],
                )

    return report
