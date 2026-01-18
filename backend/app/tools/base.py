# app/tools/base.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol


@dataclass
class ToolContext:
    """
    Shared context passed to all tools.
    Keep it stable so tools remain swappable.
    """
    session_id: str
    persona: Dict[str, Any]
    memory_items: List[Dict[str, Any]]
    session_summary: Optional[Dict[str, Any]]  # whatever your db.get_session_summary returns
    recent_messages: List[Dict[str, str]]      # [{"role": "...", "content": "..."}]
    user_message: str
    assistant_final: str

    # Model config (for tools that call Ollama)
    ollama_base_url: str
    ollama_model: str


class ToolPlugin(Protocol):
    """
    A tool plugin must:
    - decide when it should run
    - extract structured intent (LLM or deterministic)
    - execute/persist side-effects
    - return UI-friendly tool events
    """
    id: str
    name: str

    def should_run(self, ctx: ToolContext) -> bool:
        ...

    def run(self, ctx: ToolContext) -> List[Dict[str, Any]]:
        """
        Returns a list of "tool events" for the UI, e.g.
        [{"type":"alert_created","tool":"alerts","count":1,"items":[...]}]
        """
        ...