# app/tools/registry.py
from __future__ import annotations

import os
from typing import Dict, List

from .base import ToolPlugin


def env_bool(name: str, default: bool = True) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "y", "on")


class ToolsRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolPlugin] = {}

    def register(self, tool: ToolPlugin) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolPlugin | None:
        return self._tools.get(name)

    def list_tools(self) -> List[ToolPlugin]:
        return list(self._tools.values())

    def enabled_tools(self) -> List[ToolPlugin]:
        """
        Global tool enable/disable flags (simple version).
        Later: enable per persona/session.
        """
        enabled: List[ToolPlugin] = []
        for t in self.list_tools():
            # e.g. TOOLS_ALERTS_ENABLED=true
            flag = f"TOOLS_{t.name.upper()}_ENABLED"
            if env_bool(flag, default=True):
                enabled.append(t)
        return enabled