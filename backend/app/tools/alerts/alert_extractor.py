"""
alert_extractor.py — LLM-Based Alert Intent Extraction for CompanionOS.

This module is responsible for detecting when a user has asked CompanionOS to
schedule a reminder or alert, and extracting the structured details (title, due time,
repeat rule) from the conversation context.

Why LLM-based extraction?
  - Alert creation requests are expressed in free natural language:
    "Remind me to call John tomorrow at 3pm" or "Set a daily reminder to drink water".
    Simple keyword matching fails on this diversity. An LLM understands intent,
    resolves relative times ("tomorrow"), and extracts the full alert structure.

How it works:
  1. `load_alert_prompts()` reads a system prompt and a user prompt template.
  2. `extract_alerts()` assembles the full prompt by injecting conversation context,
     memory, and the current timestamp (critical for resolving relative times).
  3. The assembled prompt is sent to the LLM via the central `llm_chat()`.
  4. The TOON response is parsed by `parse_toon_output()` and validated inline.

Safety guardrails:
  - At most 2 alerts can be created per message turn to prevent runaway creation.
  - `due_at` and `title` are required fields — alerts missing either are silently dropped.
  - `repeat_rule` is validated against an allowlist ("DAILY", "WEEKLY" only).
  - On any exception, returns `{"create": []}` so the chat flow is never interrupted.
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...utils import parse_toon_output
from ...llm_client import llm_chat


def _read_text(path: Path) -> str:
    """
    Reads a UTF-8 encoded text file from disk.

    A minimal utility wrapper around `Path.read_text()` used for loading
    prompt template files. Centralizing the encoding parameter prevents
    charset errors on Windows where the default encoding is not UTF-8.
    """
    return path.read_text(encoding="utf-8")


def _prompt_dir() -> Path:
    """
    Returns the absolute path to the alert tool's prompts directory.

    Prompts live at `tools/alerts/prompts/` relative to this file.
    Using `Path(__file__).resolve().parent` ensures correct resolution regardless
    of the server's working directory.
    """
    return Path(__file__).resolve().parent / "prompts"


def load_alert_prompts() -> tuple[str, str]:
    """
    Loads the alert extraction system and template prompt files from disk.

    Two files are loaded:
      - `system.txt`:   Standing instructions for the LLM — defines its role as an
                        alert extraction assistant, the output TOON schema, and rules
                        like 'only create alerts if the user explicitly requests them'.
      - `template.txt`: A user-turn template with {placeholders} substituted at
                        runtime with current_time, mode_json, memory_text, etc.

    Returns:
        Tuple of (system_prompt_text, user_template_text).
    """
    d = _prompt_dir()
    system_txt = _read_text(d / "system.txt")
    template_txt = _read_text(d / "template.txt")
    return system_txt, template_txt


def _format_messages_for_prompt(messages: List[Dict[str, str]]) -> str:
    """
    Formats the last 10 messages from the conversation into a plain-text block.

    Used to inject conversation context into the alert extraction prompt.
    The LLM needs this to resolve context-dependent references like "the meeting
    we discussed" or "what I mentioned earlier".

    Limited to the last 10 messages to keep prompt size under control.
    Empty message content is skipped to avoid blank lines in the prompt.

    Args:
        messages: List of message dicts with 'role' and 'content' fields.

    Returns:
        A formatted string of "ROLE: content" lines joined by newlines.
    """
    lines = []
    for m in messages[-10:]:
        role = m.get("role", "unknown")
        content = (m.get("content", "") or "").strip()
        if content:
            lines.append(f"{role.upper()}: {content}")
    return "\n".join(lines)


def _format_memory_for_prompt(memory_items: Optional[List[Dict[str, Any]]]) -> str:
    """
    Formats memory items into a readable key-value block for the LLM prompt.

    Memory context helps the LLM make more accurate alert extractions. For example,
    if memory contains `user_timezone: Asia/Kolkata`, the LLM can use it to set
    the correct due_at timezone when the user says "3pm".

    Limited to first 20 items to prevent context window overflow.

    Args:
        memory_items: List of memory item dicts with 'key' and 'value' fields.

    Returns:
        A formatted "- key: value" string, or "(none)" if empty.
    """
    if not memory_items:
        return "(none)"
    lines = []
    for m in memory_items[:20]:
        k = m.get("key", "")
        v = m.get("value", "")
        lines.append(f"- {k}: {v}")
    return "\n".join(lines)


async def extract_alerts(
    mode_json: Dict[str, Any],
    memory_items: Optional[List[Dict[str, Any]]],
    recent_messages: List[Dict[str, str]],
    assistant_final_text: str,
    timeout_s: int = 60,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Detects alert creation intent in the conversation and extracts structured alert data.

    This function runs as part of the post-chat tool pipeline. It looks at the FULL
    conversation context — not just the latest message — to correctly identify and
    extract alert intent even when spread across multiple turns.

    Approach:
      1. Loads the system + template prompts.
      2. Captures the current timestamp in IST (Asia/Kolkata) — required for resolving
         relative time expressions like "tomorrow", "in 2 hours", or "next Monday".
      3. Assembles the user prompt by filling in all placeholders.
      4. Calls the LLM via the central `llm_chat()` async client.
      5. Parses the TOON response and validates each alert against required fields.

    Args:
        mode_json:            Full mode config dict (injected into prompt for context).
        memory_items:         Current session + global memory items.
        recent_messages:      Last N message dicts from the session.
        assistant_final_text: The assistant's final response text, which may contain
                              confirmation language like "I've set that reminder for you."
        timeout_s:            LLM request timeout in seconds. Default 60.

    Returns:
        A dict with a single "create" key containing a list of validated alert dicts:
        {
            "create": [
                {
                    "title": "Call John",
                    "body": "Remember to call John about the project",
                    "due_at": "2025-01-15T15:00:00+05:30",
                    "repeat_rule": null | "DAILY" | "WEEKLY"
                }
            ]
        }
        Returns `{"create": []}` on any failure — never raises.
    """
    system_prompt, template_prompt = load_alert_prompts()
    
    from datetime import datetime
    import pytz
    tz = pytz.timezone("Asia/Kolkata")
    now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

    mode_str = json.dumps(mode_json, indent=2)
    memory_text = _format_memory_for_prompt(memory_items)
    messages_json = json.dumps(recent_messages, indent=2)
    
    # Build user prompt from template
    user_prompt = template_prompt.format(
        current_time=now_str,
        mode_json=mode_str,
        memory_text=memory_text,
        recent_messages_json=messages_json,
        assistant_final_text=assistant_final_text,
    )
    
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        response_text = await llm_chat(
            messages=messages,
            timeout_s=timeout_s,
        )
        
        result = parse_toon_output(response_text)
        if not result or not isinstance(result, dict):
            return {"create": []}
        
        create_list = result.get("create", [])
        if not isinstance(create_list, list):
            return {"create": []}
        
        validated = []
        for alert in create_list[:2]:
            if not isinstance(alert, dict):
                continue
            title = str(alert.get("title") or "").strip()
            due_at = str(alert.get("due_at") or "").strip()
            if not title or not due_at:
                continue
            repeat_rule = alert.get("repeat_rule")
            if repeat_rule and repeat_rule not in ("DAILY", "WEEKLY"):
                repeat_rule = None
            validated.append({
                "title": title,
                "body": str(alert.get("body") or "").strip() or None,
                "due_at": due_at,
                "repeat_rule": repeat_rule,
            })
        return {"create": validated}
    except Exception as e:
        import logging
        logging.error(f"Alert extraction failed: {e}", exc_info=True)
        return {"create": []}
