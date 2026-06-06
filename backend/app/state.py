"""Process-wide singletons shared across route modules.

Loaded once at import; ``CHAT_JOB_ENGINE`` is filled in on FastAPI startup.
Route modules read these directly rather than receiving them via dependency
injection.
"""

from __future__ import annotations

from typing import Optional

from .chat_jobs import ChatJobEngine
from .config import get_settings
from .modes.loader import load_modes
from .tools.bootstrap import build_tools_registry

settings = get_settings()
MODES = load_modes()
TOOLS_REGISTRY = build_tools_registry()

CHAT_JOB_ENGINE: Optional[ChatJobEngine] = None
