import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _prompt_dir() -> Path:
    # backend/app/agents/judge/prompts
    return Path(__file__).resolve().parent / "prompts"


def load_judge_prompts() -> tuple[str, str]:
    d = _prompt_dir()
    system_txt = _read_text(d / "judge_system.txt")
    user_txt = _read_text(d / "judge_user.txt")
    return system_txt, user_txt


def _memory_to_text(memory_items: Optional[List[Dict[str, Any]]]) -> str:
    if not memory_items:
        return "(none)"
    # keep short and deterministic
    lines = []
    for m in memory_items[:20]:
        k = m.get("key", "")
        v = m.get("value", "")
        scope = m.get("scope", "")
        lines.append(f"- {k}: {v} (scope={scope})")
    return "\n".join(lines)


def _ollama_chat(
    ollama_base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    timeout_s: int = 60,
    max_tokens: int = 256,
) -> str:
    resp = requests.post(
        f"{ollama_base_url}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            # Ollama supports options; num_predict maps to max tokens generated.
            "options": {"num_predict": max_tokens},
        },
        timeout=timeout_s,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["message"]["content"]


def run_judge(
    *,
    persona: Dict[str, Any],
    user_message: str,
    assistant_draft: str,
    memory_items: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Returns dict with keys: verdict, rewritten_response, reason, risk_tags.
    Safe fallback: PASS if judge fails.
    """
    judge_enabled = os.getenv("JUDGE_ENABLED", "true").lower() in ("1", "true", "yes", "y")
    if not judge_enabled:
        return {"verdict": "PASS", "rewritten_response": None, "reason": "judge_disabled", "risk_tags": []}

    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
    judge_model = os.getenv("JUDGE_MODEL", os.getenv("OLLAMA_MODEL", "llama3.2:3b"))
    judge_timeout = int(os.getenv("JUDGE_TIMEOUT_S", "60"))
    judge_max_tokens = int(os.getenv("JUDGE_MAX_TOKENS", "256"))

    system_txt, user_template = load_judge_prompts()

    persona_json = json.dumps(persona, ensure_ascii=False, indent=2)
    memory_text = _memory_to_text(memory_items)

    user_prompt = user_template.format(
        persona_json=persona_json,
        memory_text=memory_text,
        user_message=user_message.strip(),
        assistant_draft=assistant_draft.strip(),
    )

    try:
        raw = _ollama_chat(
            ollama_base_url=ollama_base_url,
            model=judge_model,
            system_prompt=system_txt,
            user_prompt=user_prompt,
            timeout_s=judge_timeout,
            max_tokens=judge_max_tokens,
        )

        # The judge must return JSON only, but models sometimes add extra text.
        # Try best-effort extraction.
        raw_str = raw.strip()
        start = raw_str.find("{")
        end = raw_str.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError(f"Judge did not return JSON: {raw_str[:200]}")

        obj = json.loads(raw_str[start : end + 1])

        verdict = obj.get("verdict", "PASS")
        if verdict not in ("PASS", "REWRITE", "BLOCK"):
            verdict = "PASS"

        rewritten = obj.get("rewritten_response", None)
        feedback = obj.get("feedback", "")
        
        if verdict == "PASS":
            rewritten = None
            feedback = None
        elif verdict == "REWRITE":
            # If judge says rewrite but gives no feedback or rewrite, fallback
            if not rewritten and not feedback:
                verdict = "PASS"
        
        reason = obj.get("reason", "")
        risk_tags = obj.get("risk_tags", [])
        if not isinstance(risk_tags, list):
            risk_tags = []

        return {
            "verdict": verdict,
            "feedback": feedback,
            "rewritten_response": rewritten,
            "reason": str(reason)[:200],
            "risk_tags": [str(t)[:40] for t in risk_tags[:10]],
        }

    except Exception as e:
        # Safe fallback: don’t block user due to judge failure
        return {"verdict": "PASS", "feedback": None, "rewritten_response": None, "reason": f"judge_failed:{e}", "risk_tags": ["judge_error"]}