"""System-prompt assembly for AssistantModes."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_mode_prompt(mode_id: str) -> str | None:
    prompt_file = _PROMPTS_DIR / "modes" / f"{mode_id}.txt"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8").strip()
    return None


def build_system_prompt(
    mode: Dict[str, Any],
    memory_items: List[Dict[str, Any]] | None = None,
    tools: List[Any] | None = None,
    rag_context: str = "",
) -> str:
    """Compose the LLM system prompt from a mode definition and runtime context.

    The static personality/rules section is loaded from
    ``prompts/modes/<mode_id>.txt``. When no prompt file exists for the mode,
    rules are derived from the mode's policy fields. Dynamic context (memory,
    RAG/web results) is appended at the end.
    """
    today_str = datetime.utcnow().strftime("%B %d, %Y")
    mode_id = mode.get("id", "")
    base = _load_mode_prompt(mode_id)

    if base:
        parts = [f"Today's date is {today_str} (UTC).", base]
        if tools:
            tool_lines = ["AVAILABLE TOOLS (these run automatically after your reply — do NOT refuse capability):"]
            for t in tools:
                desc = getattr(t, "description", "") or ""
                tool_lines.append(f"- {t.name}: {desc}")
            parts.append("\n".join(tool_lines))
    else:
        rp = mode.get("response_policy", {})
        mp = mode.get("memory_policy", {})
        sp = mode.get("safety_policy", {})
        empathy = rp.get("empathy_level", 0.5)
        directness = rp.get("directness_level", 0.5)
        verbosity = rp.get("verbosity", "short")
        fmt = rp.get("format", "freeform")
        tone = rp.get("tone", "neutral")

        rules: List[str] = []
        rules.append(f"You are operating in '{mode['name']}' mode: {mode['description']}")
        rules.append(f"Empathy level: {empathy} (0=detached, 1=highly empathetic).")
        rules.append(f"Directness level: {directness} (0=indirect, 1=very direct).")
        rules.append(f"Tone: {tone}.")
        rules.append(
            "You are a helpful AI assistant. Always reply in plain natural language. "
            "Never output tool names, JSON, or structured function calls in your response."
        )
        if tools:
            tool_names = ", ".join(t.name for t in tools)
            rules.append(
                f"You have access to these tools when the user explicitly asks: {tool_names}. "
                "Only invoke a tool when clearly requested — never for greetings, small talk, "
                "or general questions."
            )
        if verbosity == "short":
            rules.append("Keep responses concise. Avoid long essays.")
        elif verbosity == "long":
            rules.append("Provide thorough, detailed responses when helpful.")
        else:
            rules.append("Responses may be moderately detailed when helpful.")
        if fmt == "steps":
            rules.append("Prefer numbered steps and clear next actions.")
        elif fmt == "bullets":
            rules.append("Prefer bullet points.")
        else:
            rules.append("Use natural paragraphs when appropriate.")
        if mp.get("enabled"):
            scope = mp.get("scope", "session")
            rules.append(
                f"Memory is enabled. Scope: {scope}. Only use user-provided facts/preferences."
            )
        else:
            rules.append("Memory is disabled. Do not claim to remember past sessions.")
        if sp.get("no_deception", True):
            rules.append("Do not pretend to be sentient or claim real-world experiences.")
        if sp.get("no_dependency", True):
            rules.append(
                "Avoid encouraging emotional dependency. Be supportive but not possessive."
            )
        if sp.get("no_medical_legal_claims", True):
            rules.append(
                "Do not provide medical or legal advice as definitive. "
                "Recommend professional help when appropriate."
            )
        parts = [
            f"Today's date is {today_str} (UTC).",
            "\n".join([f"- {r}" for r in rules]),
        ]

    if memory_items:
        mem_lines = ["Memory Context (user-provided facts/preferences):"]
        for m in memory_items[:20]:
            mem_lines.append(f"- {m['key']}: {m['value']} (scope={m['scope']})")
        parts.append("\n".join(mem_lines))

    if rag_context:
        is_web = "[Web Search Results]" in rag_context
        if is_web:
            parts.append(
                "You have been given live web search results below. Read ALL of them carefully "
                "and synthesise a single direct answer that covers every relevant item found.\n"
                "\n"
                "Strict rules for the reply:\n"
                "- Write in natural prose. Do NOT reference the search results as 'Result 1', "
                "'Result 2', '(Results 2, 8)', or any equivalent numbered back-reference. The "
                "user sees the sources separately below the message; inline numbered citations "
                "are noise.\n"
                "- Do NOT meta-comment on the search results themselves "
                "('the provided results indicate', 'the search results do not specify', "
                "'no specific details were mentioned'). Just answer the question.\n"
                "- If the results genuinely contradict each other or are thin, pick the "
                "best-supported answer and state it directly. Don't hedge.\n"
                "- Lead with the answer, not with a preamble.\n"
                "\n"
                "Search results:"
            )
        else:
            parts.append(
                "Answer using the information below. Reply naturally without referencing where "
                "the information came from:"
            )
        parts.append(rag_context)

    return "\n\n".join(parts)
