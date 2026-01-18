import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import requests


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """
    Best-effort extraction of a JSON object from model output.
    Accepts:
      - pure JSON
      - JSON fenced in ```json ... ```
      - extra text before/after
    """
    text = text.strip()

    # fenced block
    fence = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except Exception:
            pass

    # first {...} object
    first = re.search(r"(\{.*\})", text, flags=re.DOTALL)
    if first:
        blob = first.group(1)
        try:
            return json.loads(blob)
        except Exception:
            # try to trim to last closing brace
            last_brace = blob.rfind("}")
            if last_brace != -1:
                try:
                    return json.loads(blob[: last_brace + 1])
                except Exception:
                    return None
    return None


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _load_mx1_prompts() -> Tuple[str, str]:
    """
    Load system.txt and schema.json from prompts/mx1 directory.
    Returns: (system_prompt, schema_json)
    """
    prompts_dir = Path(__file__).parent / "prompts" / "mx1"
    system_file = prompts_dir / "system.txt"
    schema_file = prompts_dir / "schema.json"
    
    system_text = ""
    schema_text = ""
    
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
    persona: Dict[str, Any],
    session_summary: Optional[Dict[str, Any]],
    recent_messages: List[Dict[str, str]],
    allow_global_write: bool = True,
) -> str:
    """
    MX1 prompt: extract durable memory items + summary patch.
    Conservative: prefer writing nothing.
    """
    # Load prompt templates from files
    system_prompt, schema_json = _load_mx1_prompts()
    
    mem_policy = persona.get("memory_policy", {})
    scope_pref = mem_policy.get("scope", "session")
    enabled = bool(mem_policy.get("enabled", False))

    # We still build prompt even if disabled; caller decides to run.
    # This makes testing easier.
    summary_text = ""
    open_loops_text = "[]"
    if session_summary:
        summary_text = session_summary.get("summary", "") or ""
        open_loops = session_summary.get("open_loops", [])
        # Convert list to JSON string if needed
        if isinstance(open_loops, list):
            open_loops_text = json.dumps(open_loops)
        else:
            open_loops_text = str(open_loops) if open_loops else "[]"

    # keep only last 10
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

    # write scope rules:
    # - default write scope is persona scope, but we allow global for durable items
    allowed_scopes = ["session"]
    if allow_global_write:
        allowed_scopes.append("global")

    # Build the complete prompt using the loaded templates
    prompt = f"""{system_prompt}

MEMORY POLICY:
enabled={enabled}
persona_scope_preference={scope_pref}
allowed_scopes={allowed_scopes}

CURRENT SESSION SUMMARY (may be empty):
summary: {summary_text}
open_loops_json: {open_loops_text}

RECENT CONVERSATION (last {len(msgs)} messages):
{convo}

OUTPUT JSON SCHEMA:
    {schema_json}
    """
    
    return prompt.strip()


def run_mx1_ollama(
    ollama_base_url: str,
    model: str,
    prompt: str,
    timeout_s: int = 45,
) -> str:
    """
    Calls Ollama /api/generate (single prompt) for structured JSON output.
    """
    resp = requests.post(
        f"{ollama_base_url}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=timeout_s,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", "")


def validate_mx1_output(
    data: Dict[str, Any],
    confidence_threshold: float = 0.8,
    allow_scopes: Tuple[str, ...] = ("global", "session"),
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Returns (accepted_items, summary_patch). Drops unsafe/invalid items.
    """
    items_in = data.get("items", [])
    if not isinstance(items_in, list):
        items_in = []

    accepted: List[Dict[str, Any]] = []
    for it in items_in[:5]:  # hard cap to prevent spam
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

    # summary patch
    sp = data.get("summary_patch", {})
    if not isinstance(sp, dict):
        sp = {}

    summary = sp.get("summary", "")
    open_loops = sp.get("open_loops", [])
    if not isinstance(summary, str):
        summary = ""
    if not isinstance(open_loops, list):
        open_loops = []

    # normalize open loops to strings
    open_loops_norm: List[str] = []
    for x in open_loops[:10]:
        if isinstance(x, str) and x.strip():
            open_loops_norm.append(x.strip())

    summary_patch = {"summary": summary.strip(), "open_loops": open_loops_norm}
    return accepted, summary_patch


def extract_mx1(
    ollama_base_url: str,
    model: str,
    persona: Dict[str, Any],
    session_summary: Optional[Dict[str, Any]],
    recent_messages: List[Dict[str, str]],
    confidence_threshold: float = 0.8,
    allow_global_write: bool = True,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str]:
    """
    Full pipeline:
      prompt -> model -> json parse -> validate
    Returns: (accepted_items, summary_patch, raw_model_text)
    """
    prompt = build_mx1_prompt(
        persona=persona,
        session_summary=session_summary,
        recent_messages=recent_messages,
        allow_global_write=allow_global_write,
    )

    raw = run_mx1_ollama(ollama_base_url, model, prompt)
    data = _extract_json_object(raw) or {}
    accepted_items, summary_patch = validate_mx1_output(
        data,
        confidence_threshold=confidence_threshold,
        allow_scopes=("global", "session") if allow_global_write else ("session",),
    )
    return accepted_items, summary_patch, raw


def generate_session_summary(
    messages: List[str],
    ollama_base_url: str | None = None,
    model: str | None = None,
    timeout_s: int = 45,
) -> str:
    """
    Returns a concise 3–4 sentence summary.
    Call LLM here to generate summary from messages.
    """
    # Get defaults from environment if not provided
    if ollama_base_url is None:
        ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
    if model is None:
        model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    # Format messages for the prompt
    conversation_text = "\n".join([f"- {msg}" for msg in messages[-20:]])  # Use last 20 messages
    
    prompt = f"""You are a helpful assistant. Generate a concise 3-4 sentence summary of the following conversation.

Conversation:
{conversation_text}

Summary:"""
    
    try:
        resp = requests.post(
            f"{ollama_base_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()
        summary = data.get("response", "").strip()
        
        # Ensure it's 3-4 sentences (roughly)
        sentences = summary.split('.')
        if len(sentences) > 4:
            summary = '. '.join(sentences[:4]) + '.'
        elif len(sentences) < 3 and summary:
            # If too short, try to expand or return as-is
            pass
        
        return summary if summary else "Session conversation summary."
    except Exception as e:
        # Fallback summary on error
        return f"Session with {len(messages)} messages."