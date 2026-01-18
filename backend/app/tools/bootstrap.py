# app/tools/bootstrap.py
from __future__ import annotations

from .registry import ToolsRegistry
from .alerts.tool import AlertsTool


def build_tools_registry() -> ToolsRegistry:
    reg = ToolsRegistry()
    reg.register(AlertsTool())
    return reg