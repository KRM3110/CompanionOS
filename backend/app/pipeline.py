import os
import logging
from typing import Any, Dict, List, Tuple

from .memory_extractor import extract_mx1
from .db import (
    get_messages,
    count_messages,
    get_session_summary,
    upsert_session_summary,
    upsert_memory_item,
)

logger = logging.getLogger(__name__)

# ---- Pipeline Config ----
MX1_CONFIDENCE_THRESHOLD = float(os.getenv("MX1_CONFIDENCE_THRESHOLD", "0.8"))
MX1_RECENT_MESSAGES = int(os.getenv("MX1_RECENT_MESSAGES", "10"))  # use last N messages
SUMMARY_CADENCE = int(os.getenv("SUMMARY_CADENCE", "6"))           # update summary every N msgs
ALLOW_GLOBAL_WRITE = os.getenv("ALLOW_GLOBAL_WRITE", "true").lower() == "true"

# Ollama settings (same defaults as main.py)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


def _fallback_summary_from_recent(recent: List[Dict[str, str]], msg_count: int) -> str:
    """Safe fallback if MX1 doesn't produce a summary."""
    if not recent:
        return f"Session with {msg_count} messages."

    # Take last 4 messages and compress
    tail = recent[-4:]
    snippets = []
    for m in tail:
        role = m.get("role", "unknown")
        content = (m.get("content") or "").strip().replace("\n", " ")
        if content:
            snippets.append(f"{role}: {content[:80]}")

    joined = " | ".join(snippets[:3])
    return f"Session with {msg_count} messages. Recent: {joined}"


def run_post_chat_pipeline(session_id: str, persona: Dict[str, Any]) -> Dict[str, Any]:
    """
    Runs AFTER user+assistant messages are persisted.

    Responsibilities:
    - MX1 memory extraction + upsert (thresholded)
    - session summary update on cadence (every SUMMARY_CADENCE messages)

    Returns debug info for API response.
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
        # 1) Load recent messages
        msgs = get_messages(session_id, limit=50)
        recent = [{"role": m["role"], "content": m["content"]} for m in msgs][-MX1_RECENT_MESSAGES:]

        # 2) Compute cadence
        msg_count = count_messages(session_id)
        should_update_summary = (msg_count % SUMMARY_CADENCE == 0)

        debug["msg_count"] = msg_count
        debug["should_update_summary"] = should_update_summary

        # 3) Load existing summary (may be None)
        session_summary = get_session_summary(session_id)

        # 4) Run MX1
        items, summary_patch, raw = extract_mx1(
            ollama_base_url=OLLAMA_BASE_URL,
            model=OLLAMA_MODEL,
            persona=persona,
            session_summary=session_summary,
            recent_messages=recent,
            confidence_threshold=MX1_CONFIDENCE_THRESHOLD,
            allow_global_write=ALLOW_GLOBAL_WRITE,
        )

        # 5) Upsert memory items
        upserted = 0
        for it in items:
            scope = it["scope"]
            upsert_memory_item(
                scope=scope,
                key=it["key"],
                value=it["value"],
                confidence=float(it.get("confidence", 0.0)),
                session_id=session_id if scope == "session" else None,
                source_message_id=None,
            )
            upserted += 1

        debug["memory_items_upserted"] = upserted

        # 6) Summary update only on cadence
        if should_update_summary:
            summary_text = (summary_patch.get("summary") or "").strip()

            if summary_text:
                upsert_session_summary(
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
                # fallback summary
                fallback = _fallback_summary_from_recent(recent, msg_count)
                upsert_session_summary(
                    session_id=session_id,
                    summary=fallback,
                    open_loops=summary_patch.get("open_loops", []),
                )
                debug["summary_updated"] = True
                debug["summary_len"] = len(fallback)
                debug["errors"].append(
                    "MX1 returned empty summary at cadence; used fallback summary."
                )
                logger.warning(
                    f"MX1 empty summary at cadence for {session_id}. Raw preview: "
                    f"{(raw or '')[:200]}"
                )

    except Exception as e:
        debug["errors"].append(f"pipeline_error: {str(e)}")
        logger.error(f"Post-chat pipeline failed for {session_id}: {e}", exc_info=True)

        # Emergency summary if cadence hit but MX1 failed
        try:
            msg_count = count_messages(session_id)
            if msg_count % SUMMARY_CADENCE == 0:
                emergency = f"Session with {msg_count} messages. Summary temporarily unavailable."
                upsert_session_summary(
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