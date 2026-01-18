# app/tools/alerts/tool.py
from __future__ import annotations

from typing import Any, Dict, List

from ..base import ToolContext
from ..base import ToolPlugin

# your existing modules (you said you already have these)
from .alert_extractor import extract_alerts
from .alert_service import execute_alert_creation


class AlertsTool:
    id = "alerts"
    name = "Alerts"
    description = "WORKING alert/reminder system. When user asks to set a reminder, CONFIRM you will do it. The alert is saved and will appear in their Alerts Panel. Say: 'Done! I've set a reminder for [time].' Do NOT say you cannot set alerts."

    def should_run(self, ctx: ToolContext) -> bool:
        # simple default: if persona memory policy enabled OR always
        # you can tighten later (only for Coach persona, etc.)
        return True

    def run(self, ctx: ToolContext) -> List[Dict[str, Any]]:
        print(f"[DEBUG] AlertsTool.run called for session {ctx.session_id}")
        extracted_data = extract_alerts(
            ollama_base_url=ctx.ollama_base_url,
            model=ctx.ollama_model,
            persona_json=ctx.persona,
            memory_items=ctx.memory_items,
            recent_messages=ctx.recent_messages,
            assistant_final_text=ctx.assistant_final,
        )
        print(f"[DEBUG] extract_alerts returned: {extracted_data}")

        # extracted_data is {"create": [...]}
        alerts_to_create = extracted_data.get("create", [])
        
        if not alerts_to_create:
            print("[DEBUG] No alerts to create found in extraction.")
            return []

        print(f"[DEBUG] Attempting to create {len(alerts_to_create)} alerts...")
        created = execute_alert_creation(
            session_id=ctx.session_id,
            alerts=alerts_to_create,
        )
        print(f"[DEBUG] execute_alert_creation returned: {created}")

        if not created:
            return []

        # Tool events for UI
        return [{
            "type": "alert_created",
            "count": len(created),
            "items": created,  # include minimal fields (id/title/due/status/scope)
        }]