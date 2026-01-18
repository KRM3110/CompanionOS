"""
LLM intent extraction for alerts.
Extracts alert creation intent from conversation.
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


def _read_text(path: Path) -> str:
    """Read text file with UTF-8 encoding."""
    return path.read_text(encoding="utf-8")


def _prompt_dir() -> Path:
    """Get the prompts directory for alerts."""
    return Path(__file__).resolve().parent / "prompts"


def load_alert_prompts() -> tuple[str, str]:
    """Load system and template prompts."""
    d = _prompt_dir()
    system_txt = _read_text(d / "system.txt")
    template_txt = _read_text(d / "template.txt")
    return system_txt, template_txt


def _format_messages_for_prompt(messages: List[Dict[str, str]]) -> str:
    """Format recent messages for prompt."""
    lines = []
    for m in messages[-10:]:  # Last 10 messages
        role = m.get("role", "unknown")
        content = (m.get("content", "") or "").strip()
        if content:
            lines.append(f"{role.upper()}: {content}")
    return "\n".join(lines)


def _format_memory_for_prompt(memory_items: Optional[List[Dict[str, Any]]]) -> str:
    """Format memory items for prompt."""
    if not memory_items:
        return "(none)"
    lines = []
    for m in memory_items[:20]:
        k = m.get("key", "")
        v = m.get("value", "")
        lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def _ollama_chat(
    ollama_base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout_s: int = 60,
) -> str:
    """Call Ollama /api/chat endpoint."""
    resp = requests.post(
        f"{ollama_base_url}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        },
        timeout=timeout_s,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("message", {}).get("content", "")


def _extract_json_from_response(text: str) -> Optional[Dict[str, Any]]:
    """Extract JSON object from LLM response."""
    text = text.strip()
    
    # Try to find JSON object
    # Look for ```json ... ``` blocks first
    import re
    json_block = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if json_block:
        try:
            return json.loads(json_block.group(1))
        except json.JSONDecodeError:
            pass
    
    # Look for first {...} object
    first_brace = text.find("{")
    if first_brace != -1:
        last_brace = text.rfind("}")
        if last_brace > first_brace:
            try:
                return json.loads(text[first_brace:last_brace + 1])
            except json.JSONDecodeError:
                pass
    
    return None


def extract_alerts(
    persona_json: Dict[str, Any],
    memory_items: Optional[List[Dict[str, Any]]],
    recent_messages: List[Dict[str, str]],
    assistant_final_text: str,
    ollama_base_url: str | None = None,
    model: str | None = None,
    timeout_s: int = 60,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Extract alert creation intent from conversation.
    
    Args:
        persona_json: Persona configuration
        memory_items: List of memory items
        recent_messages: Last 10 messages (user + assistant)
        assistant_final_text: Final assistant message text
        ollama_base_url: Ollama base URL (defaults to env var)
        model: Ollama model name (defaults to env var)
        timeout_s: Request timeout
    
    Returns:
        Dict with "create" key containing list of alert dicts:
        {
            "create": [
                {
                    "title": "...",
                    "body": "...",
                    "due_at": "YYYY-MM-DDTHH:MM:SS+05:30",
                    "repeat_rule": null | "DAILY" | "WEEKLY"
                }
            ]
        }
    """
    # Get defaults from environment
    if ollama_base_url is None:
        ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
    if model is None:
        model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    
    # Load prompts
    system_prompt, template_prompt = load_alert_prompts()
    
    # Format inputs
    from datetime import datetime
    import pytz
    tz = pytz.timezone("Asia/Kolkata")
    now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

    persona_str = json.dumps(persona_json, indent=2)
    memory_text = _format_memory_for_prompt(memory_items)
    messages_json = json.dumps(recent_messages, indent=2)
    
    # Build user prompt from template
    user_prompt = template_prompt.format(
        current_time=now_str,
        persona_json=persona_str,
        memory_text=memory_text,
        recent_messages_json=messages_json,
        assistant_final_text=assistant_final_text,
    )
    
    try:
        # Call Ollama
        response_text = _ollama_chat(
            ollama_base_url=ollama_base_url,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_s=timeout_s,
        )
        
        # Extract JSON
        result = _extract_json_from_response(response_text)
        
        if not result:
            return {"create": []}
        
        # Validate structure
        if not isinstance(result, dict):
            return {"create": []}
        
        create_list = result.get("create", [])
        if not isinstance(create_list, list):
            return {"create": []}
        
        # Validate and limit to 2 reminders
        validated = []
        for alert in create_list[:2]:  # Max 2
            if not isinstance(alert, dict):
                continue
            
            # Required fields
            title = str(alert.get("title") or "").strip()
            due_at = str(alert.get("due_at") or "").strip()
            
            if not title or not due_at:
                continue
            
            # Validate repeat_rule
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
        # On error, return empty
        import logging
        logging.error(f"Alert extraction failed: {e}", exc_info=True)
        return {"create": []}
