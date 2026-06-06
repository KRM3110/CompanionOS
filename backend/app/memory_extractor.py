"""
memory_extractor.py — MX1 Memory Extraction Agent for CompanionOS.

MX1 ("Memory Extraction v1") is the automatic background memory system. After each
user ↔ assistant exchange, the pipeline calls this module to analyze the conversation
and extract durable facts about the user (e.g. "user_prefers_dark_mode: true") and
a rolling summary of what has been discussed.

How it works:
  1. `build_mx1_prompt()` assembles a rich instruction prompt that includes the
     mode's memory policy, the current session summary, and the last N messages.
  2. The prompt instructs the LLM to respond in TOON format with two sections:
       - `items`: A list of memory key-value pairs with confidence scores.
       - `summary_patch`: A new rolling summary of the conversation + open loops.
  3. `extract_mx1()` calls Gemini via `llm_client.llm_generate()`.
  4. The raw output is parsed by `utils.parse_toon_output()`.
  5. `validate_mx1_output()` filters out low-confidence, malformed, or out-of-scope
     memory items before they are persisted — acting as a safety gate.

Design principles:
  - Conservative: the system prompt instructs MX1 to prefer writing NOTHING over
    writing something uncertain. Only high-confidence, clearly user-stated facts
    should be extracted.
  - Idempotent: memory items use an upsert strategy (scope + key = unique), so
    re-running MX1 on the same conversation will update, not duplicate, items.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .utils import parse_toon_output
from .llm_client import llm_generate
from .config import get_settings

settings = get_settings()


def _clamp01(x: float) -> float:
    """Clamps a float value to the range [0.0, 1.0]."""
    return max(0.0, min(1.0, float(x)))


def _load_mx1_prompts() -> Tuple[str, str]:
    """
    Loads the MX1 system prompt and output schema from filesystem template files.

    Returns:
        Tuple of (system_prompt_text, schema_json_text).

    Raises:
        FileNotFoundError: If either template file is missing.
    """
    prompts_dir = Path(__file__).parent / "prompts" / "mx1"
    system_file = prompts_dir / "system.txt"
    schema_file = prompts_dir / "schema.json"

    if system_file.exists():
        with open(system_file, "r", encoding="utf-8") as f:
            system_text = f.read().strip()
    else:
        raise FileNotFoundError(f"System prompt file not found: {system_file}")

    if schema_file.exists():
        with open(schema_file, "r", encoding="utf-8") as f:
            schema_text = f.read().strip()
    else:
        raise FileNotFoundError(f"Schema file not found: {schema_file}")

    return system_text, schema_text


def build_mx1_prompt(
    mode: Dict[str, Any],
    session_summary: Optional[Dict[str, Any]],
    recent_messages: List[Dict[str, str]],
    allow_global_write: bool = True,
) -> str:
    """
    Assembles the complete LLM prompt for one MX1 extraction pass.

    Args:
        mode:            The AssistantMode dict. Used for memory_policy.
        session_summary: Existing session_summaries row, or None for new sessions.
        recent_messages: Full message history list — sliced to the last 10 internally.
        allow_global_write: If False, the prompt restricts writes to 'session' scope.

    Returns:
        A single assembled prompt string ready to pass to `llm_generate()`.
    """
    system_prompt, _ = _load_mx1_prompts()

    mem_policy = mode.get("memory_policy", {})
    scope_pref = mem_policy.get("scope", "session")
    enabled = bool(mem_policy.get("enabled", False))

    summary_text = ""
    open_loops_text = "[]"
    if session_summary:
        summary_text = session_summary.get("summary", "") or ""
        open_loops = session_summary.get("open_loops", [])
        open_loops_text = str(open_loops) if open_loops else "[]"

    # Limit to last 10 messages to control prompt token size.
    msgs = recent_messages[-10:]
    convo_lines = []
    for m in msgs:
        role = m.get("role", "")
        content = (m.get("content", "") or "").strip()
        if not content:
            continue
        if role == "assistant":
            convo_lines.append(f"ASSISTANT: {content}")
        else:
            convo_lines.append(f"USER: {content}")
    convo = "\n".join(convo_lines)

    allowed_scopes = ["session"]
    if allow_global_write:
        allowed_scopes.append("global")

    prompt = f"""{system_prompt}

MEMORY POLICY:
enabled={enabled}
mode_scope_preference={scope_pref}
allowed_scopes={allowed_scopes}

CURRENT SESSION SUMMARY (may be empty):
summary: {summary_text}
open_loops: {open_loops_text}

RECENT CONVERSATION (last {len(msgs)} messages):
{convo}

OUTPUT TOON SCHEMA:
Format your output as a clean TOON mapping with no markdown blocks:
items:
  - scope: session
    key: user_likes_dogs
    value: true
    confidence: 0.9
summary_patch:
  summary: User likes dogs.
  open_loops:
    - find a dog
"""
    return prompt.strip()


def validate_mx1_output(
    data: Dict[str, Any],
    confidence_threshold: float = 0.8,
    allow_scopes: Tuple[str, ...] = ("global", "session"),
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Validates and filters MX1 model output before any database writes occur.

    This is the safety gate between raw LLM output and persistent storage.

    Validation rules:
      - `scope` must be one of the allowed scopes.
      - `key` must be snake_case alphanumeric, 1-64 chars.
      - `value` must be a non-empty string ≤ 400 chars.
      - `confidence` must be ≥ threshold after clamping to [0, 1].
      - Hard cap of 5 items per pass prevents over-extraction.

    Args:
        data:                 The parsed TOON dict from the model output.
        confidence_threshold: Items below this score are rejected.
        allow_scopes:         Tuple of allowed scope strings.

    Returns:
        Tuple of (accepted_items, summary_patch).
    """
    items_in = data.get("items", [])
    if not isinstance(items_in, list):
        items_in = []

    accepted: List[Dict[str, Any]] = []
    for it in items_in[:5]:  # Hard cap: maximum 5 memory items per MX1 pass.
        if not isinstance(it, dict):
            continue
        scope = it.get("scope")
        key = it.get("key")
        value = it.get("value")
        conf = it.get("confidence", 0.0)

        if scope not in allow_scopes:
            continue
        if not isinstance(key, str) or not (1 <= len(key) <= 64):
            continue
        if not re.fullmatch(r"[a-z0-9_]+", key):
            continue
        if not isinstance(value, str) or not (1 <= len(value) <= 400):
            continue

        try:
            conf_f = _clamp01(float(conf))
        except Exception:
            conf_f = 0.0

        if conf_f < confidence_threshold:
            continue

        accepted.append(
            {"scope": scope, "key": key, "value": value.strip(), "confidence": conf_f}
        )

    sp = data.get("summary_patch", {})
    if not isinstance(sp, dict):
        sp = {}

    summary = sp.get("summary", "")
    open_loops = sp.get("open_loops", [])
    if not isinstance(summary, str):
        summary = ""
    if not isinstance(open_loops, list):
        open_loops = []

    open_loops_norm: List[str] = []
    for x in open_loops[:10]:
        if isinstance(x, str) and x.strip():
            open_loops_norm.append(x.strip())

    summary_patch = {"summary": summary.strip(), "open_loops": open_loops_norm}
    return accepted, summary_patch


async def extract_mx1(
    mode: Dict[str, Any],
    session_summary: Optional[Dict[str, Any]],
    recent_messages: List[Dict[str, str]],
    confidence_threshold: float = 0.8,
    allow_global_write: bool = True,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str]:
    """
    Runs the full MX1 memory extraction pipeline end-to-end.

    Args:
        mode:                 The full AssistantMode dict for the active session.
        session_summary:      Current session summary dict, or None for new sessions.
        recent_messages:      Last N messages from the session history.
        confidence_threshold: Minimum confidence for a memory item to be accepted.
        allow_global_write:   Whether to allow items to be written to global scope.

    Returns:
        Tuple of (accepted_items, summary_patch, raw_model_text).
    """
    prompt = build_mx1_prompt(
        mode=mode,
        session_summary=session_summary,
        recent_messages=recent_messages,
        allow_global_write=allow_global_write,
    )

    raw = await llm_generate(prompt, timeout_s=45)
    data = parse_toon_output(raw) or {}
    accepted_items, summary_patch = validate_mx1_output(
        data,
        confidence_threshold=confidence_threshold,
        allow_scopes=("global", "session") if allow_global_write else ("session",),
    )
    return accepted_items, summary_patch, raw


async def generate_session_summary(
    messages: List[str],
    timeout_s: int = 45,
) -> str:
    """
    Generates a concise 3-4 sentence plain-text summary of a list of messages.

    Args:
        messages:  List of plain-text message strings.
        timeout_s: Max wait time for the LLM.

    Returns:
        A 3-4 sentence summary string, or a safe fallback.
    """
    conversation_text = "\n".join([f"- {msg}" for msg in messages[-20:]])

    prompt = f"""You are a helpful assistant. Generate a concise 3-4 sentence summary of the following conversation.
Conversation:
{conversation_text}

Summary:"""
    try:
        summary = await llm_generate(prompt, timeout_s=timeout_s)
        summary = summary.strip()
        sentences = summary.split(".")
        if len(sentences) > 4:
            summary = ". ".join(sentences[:4]) + "."
        return summary if summary else "Session conversation summary."
    except Exception:
        return f"Session with {len(messages)} messages."