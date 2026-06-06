from __future__ import annotations

import logging
from typing import Any, Dict, List

from ..base import ToolContext
from ..base import ToolPlugin

from .alert_extractor import extract_alerts
from .alert_service import execute_alert_creation

logger = logging.getLogger(__name__)


class AlertsTool:
    id = "alerts"
    name = "Alerts"
    description = "WORKING alert/reminder system. When user asks to set a reminder, CONFIRM you will do it. The alert is saved and will appear in their Alerts Panel. Say: 'Done! I've set a reminder for [time].' Do NOT say you cannot set alerts."

    def should_run(self, ctx: ToolContext) -> bool:
        return True

    def run(self, ctx: ToolContext) -> List[Dict[str, Any]]:
        logger.debug("AlertsTool.run called for session %s", ctx.session_id)
        extracted_data = extract_alerts(
            mode_json=ctx.mode,
            memory_items=ctx.memory_items,
            recent_messages=ctx.recent_messages,
            assistant_final_text=ctx.assistant_final,
        )
        logger.debug("extract_alerts returned: %s", extracted_data)

        alerts_to_create = extracted_data.get("create", [])

        if not alerts_to_create:
            logger.debug("No alerts to create in extraction.")
            return []

        logger.debug("Creating %d alert(s)", len(alerts_to_create))
        created = execute_alert_creation(
            session_id=ctx.session_id,
            alerts=alerts_to_create,
        )
        logger.debug("execute_alert_creation returned: %s", created)

        if not created:
            return []

        # Tool events for UI
        return [{
            "type": "alert_created",
            "count": len(created),
            "items": created,  # include minimal fields (id/title/due/status/scope)
        }]
