"""
pipeline.py — Post-Chat Processing Pipeline for CompanionOS.

After every complete user ↔ assistant exchange, this module runs a sequence of
background processing steps that keep the system's memory and context summaries
fresh and up-to-date. It is called by `main.py` via `asyncio.create_task()` or
directly after the response is assembled.

Responsibilities:
  1. MX1 Memory Extraction:
     Reads the last N messages, assembles a prompt, calls the LLM, and upserts any
     high-confidence memory items (facts, preferences) into the database.
  2. Session Summary Update (Cadence-Controlled):
     Every `SUMMARY_CADENCE` messages, the latest MX1 response's `summary_patch`
     is persisted as the session's rolling summary. This gives the LLM a compact,
     context-rich anchor for future messages without passing the full history.

Why cadence-based?
  - Running memory extraction + summary update on EVERY message would double the
    LLM API calls and latency. By gating on a cadence (default every 6 messages),
    we balance freshness with efficiency.

Error Handling:
  - The pipeline is designed to be non-fatal. If MX1 fails for any reason, the
    chat response has already been sent to the user — the pipeline runs afterward.
  - On cadence when MX1 fails, an emergency summary is written so the session is
    never left with a completely stale context record.
"""

import logging
from typing import Any, Dict, List

from .memory_extractor import extract_mx1
from .db import (
    count_messages,
    get_messages,
    get_session_summary,
    upsert_memory_item,
    upsert_session_summary,
)
from .config import get_settings

logger = logging.getLogger(__name__)

# Load the singleton settings once at module import time.
settings = get_settings()


def _fallback_summary_from_recent(recent: List[Dict[str, str]], msg_count: int) -> str:
    """
    Generates a minimal text summary from the tail of recent messages.

    This is only called when MX1 runs at a cadence point but the model returns
    an empty or unparseable summary_patch. We still need to write something to
    the session_summaries table so the next call has context to build on.

    Approach:
      - Takes the last 4 messages (to keep context small) and concatenates
        them as role: content[:80] snippets, separated by ' | '.
      - Prefixes with the total message count so subsequent reads know the
        density/length of the session even without rich content.

    Args:
        recent:    List of recent message dicts with 'role' and 'content'.
        msg_count: Total number of messages in the session (for the prefix).

    Returns:
        A plain-text fallback summary string. Never empty.
    """
    if not recent:
        return f"Session with {msg_count} messages."

    # Take last 4 messages and compress into short snippets.
    tail = recent[-4:]
    snippets = []
    for m in tail:
        role = m.get("role", "unknown")
        content = (m.get("content") or "").strip().replace("\n", " ")
        if content:
            snippets.append(f"{role}: {content[:80]}")

    joined = " | ".join(snippets[:3])
    return f"Session with {msg_count} messages. Recent: {joined}"


async def run_post_chat_pipeline(session_id: str, mode: Dict[str, Any]) -> Dict[str, Any]:
    """
    Orchestrates the full post-chat processing pipeline for a completed exchange.

    This is called after the user's message and the assistant's final response have
    both been persisted to the database. It runs two sub-steps:

      Step 1 — MX1 Memory Extraction:
        Fetches the last `settings.mx1_recent_messages` messages, builds the MX1 prompt
        (using mode config + existing summary + conversation), calls the LLM, and
        upserts all accepted memory items. Items below the confidence threshold or
        with invalid keys are silently dropped here.

      Step 2 — Cadence-gated Summary Update:
        Checks if `current_message_count % settings.summary_cadence == 0`.
        If yes, takes the `summary_patch` from MX1 and persists it as the session
        summary. If MX1 returned empty content, a fallback summary is written instead.

    The function NEVER raises. All errors are caught, logged, and recorded in the
    `debug` return dict. The chat response has already been sent to the user, so
    pipeline failures must not crash the request.

    Args:
        session_id: The active session UUID.
        mode:       The full AssistantMode dict for the active session, needed to configure
                    MX1's memory policy (scope, enabled flag, etc).

    Returns:
        A debug dict containing pipeline diagnostics, suitable for inclusion in the
        API response body for developer inspection:
          - msg_count:             Total messages in session after this exchange.
          - should_update_summary: Whether the cadence gate was triggered.
          - memory_items_upserted: Count of memory items actually written to DB.
          - summary_updated:       Whether the session summary was updated.
          - summary_len:           Character length of the written summary.
          - errors:                List of error strings if anything went wrong.
    """
    debug: Dict[str, Any] = {
        "session_id": session_id,
        "msg_count": None,
        "should_update_summary": None,
        "memory_items_upserted": 0,
        "summary_updated": False,
        "summary_len": 0,
        "errors": [],
    }

    try:
        # Step 1a: Load recent messages for MX1 context window.
        # We fetch up to 50 but slice to `mx1_recent_messages` for the prompt
        # to avoid sending an excessively large token payload to the model.
        msgs = await get_messages(session_id, limit=50)
        recent = [{"role": m["role"], "content": m["content"]} for m in msgs][-settings.mx1_recent_messages:]

        # Step 1b: Check the cadence gate BEFORE running MX1.
        # We compute it early so the debug dict is always populated, even on error.
        msg_count = await count_messages(session_id)
        should_update_summary = (msg_count % settings.summary_cadence == 0)

        debug["msg_count"] = msg_count
        debug["should_update_summary"] = should_update_summary

        # Step 1c: Load current session summary to give MX1 rolling context.
        # May be None for new sessions — extract_mx1 handles this gracefully.
        session_summary = await get_session_summary(session_id)

        # Step 1d: Run MX1 — the core memory and summary extraction call.
        # Returns: accepted_items (validated), summary_patch (new summary text),
        # and raw (the raw model output string for debugging).
        items, summary_patch, raw = await extract_mx1(
            mode=mode,
            session_summary=session_summary,
            recent_messages=recent,
            confidence_threshold=settings.mx1_confidence_threshold,
            allow_global_write=settings.allow_global_write,
        )

        # Step 1e: Upsert all accepted memory items into the database.
        # `upsert_memory_item` does an INSERT or UPDATE based on (scope, key, session_id).
        upserted = 0
        for it in items:
            scope = it["scope"]
            await upsert_memory_item(
                scope=scope,
                key=it["key"],
                value=it["value"],
                confidence=float(it.get("confidence", 0.0)),
                # Session-scoped memories are tied to this session;
                # global memories have no session_id so they persist across all sessions.
                session_id=session_id if scope == "session" else None,
                source_message_id=None,
            )
            upserted += 1

        debug["memory_items_upserted"] = upserted

        # Step 2: Update session summary only when cadence gate is triggered.
        if should_update_summary:
            summary_text = (summary_patch.get("summary") or "").strip()

            if summary_text:
                # MX1 produced a meaningful summary — persist it directly.
                await upsert_session_summary(
                    session_id=session_id,
                    summary=summary_text,
                    open_loops=summary_patch.get("open_loops", []),
                )
                debug["summary_updated"] = True
                debug["summary_len"] = len(summary_text)
                logger.info(
                    f"Pipeline summary updated for {session_id} (len={len(summary_text)})"
                )
            else:
                # MX1 failed to produce a summary — use the lightweight fallback
                # so the session record is never left completely stale at a cadence point.
                fallback = _fallback_summary_from_recent(recent, msg_count)
                await upsert_session_summary(
                    session_id=session_id,
                    summary=fallback,
                    open_loops=summary_patch.get("open_loops", []),
                )
                debug["summary_updated"] = True
                debug["summary_len"] = len(fallback)
                debug["errors"].append(
                    "MX1 returned empty summary at cadence; used fallback summary."
                )

    except Exception as e:
        # The pipeline failed entirely (e.g. LLM timeout, DB error).
        # Record the error and attempt a minimal emergency summary if we're at cadence.
        debug["errors"].append(f"pipeline_error: {str(e)}")
        logger.error(f"Post-chat pipeline failed for {session_id}: {e}", exc_info=True)

        try:
            # Emergency path: if the cadence gate would have fired, write a stub summary
            # so the next session load always has *something* to anchor context on.
            msg_count = await count_messages(session_id)
            if msg_count % settings.summary_cadence == 0:
                emergency = f"Session with {msg_count} messages. Summary temporarily unavailable."
                await upsert_session_summary(
                    session_id=session_id,
                    summary=emergency,
                    open_loops=[],
                )
                debug["msg_count"] = msg_count
                debug["should_update_summary"] = True
                debug["summary_updated"] = True
                debug["summary_len"] = len(emergency)
                debug["errors"].append("MX1 failed at cadence; wrote emergency summary.")
        except Exception as e2:
            debug["errors"].append(f"emergency_summary_failed: {str(e2)}")
            logger.error(f"Emergency summary failed for {session_id}: {e2}", exc_info=True)

    return debug
