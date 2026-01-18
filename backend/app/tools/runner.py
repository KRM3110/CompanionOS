# app/tools/runner.py
from __future__ import annotations

import logging
from typing import Any, Dict, List

from .base import ToolContext
from .registry import ToolsRegistry


def run_tools(registry: ToolsRegistry, ctx: ToolContext, enabled_map: dict[str, bool]) -> list[dict]:
    events: list[dict] = []
    for tool in registry.list_tools():
        if not enabled_map.get(tool.id, True):
            events.append({
                "tool_id": tool.id,
                "event": "skipped",
                "title": "Tool disabled",
                "message": f"{tool.id} is disabled for this session.",
                "data": {}
            })
            continue

        try:
            tool_events = tool.run(ctx)
            events.extend(tool_events or [])
        except Exception as e:
            logging.error(f"Tool {tool.id} failed: {e}", exc_info=True)  # <--- Print to logs!
            events.append({
                "tool_id": tool.id,
                "event": "error",
                "title": "Tool failed",
                "message": str(e),
                "data": {}
            })
    return events