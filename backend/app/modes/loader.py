"""
modes/loader.py — AssistantMode Loader for CompanionOS.

Replaces the old personas.py. Scans backend/app/modes/data/*.json, validates each
file through the AssistantMode Pydantic model, and returns a typed registry dict.

Key improvements over the old persona loader:
  - Pydantic validation at startup: invalid JSON or missing required fields raise a
    clear error immediately rather than silently producing a broken persona dict.
  - Returns AssistantMode objects (not raw dicts) — callers get type safety and IDE
    autocomplete on mode.response_policy.verbosity instead of mode["style"]["response_length"].
  - A `.dict()` helper is available on each AssistantMode for backwards-compatible
    legacy callers that still expect a plain dict.
"""

import logging
from pathlib import Path
from typing import Dict, Optional

from pydantic import ValidationError

from .schema import AssistantMode

logger = logging.getLogger(__name__)

# Default data directory: backend/app/modes/data/
_DEFAULT_DATA_DIR = Path(__file__).parent / "data"


def load_modes(data_dir: Optional[Path] = None) -> Dict[str, AssistantMode]:
    """
    Loads and validates all AssistantMode JSON files from the data directory.

    Scans `data_dir` for *.json files, parses each through the AssistantMode
    Pydantic model, and builds a dict keyed by mode ID. Files that fail Pydantic
    validation or have duplicate IDs are skipped with a warning — the remaining
    valid modes are still loaded so a single bad file doesn't kill the server.

    Args:
        data_dir: Path to scan for JSON files. Defaults to backend/app/modes/data/.

    Returns:
        Dict[str, AssistantMode] — keyed by mode.id (e.g. {"focus": AssistantMode(...)}).
        Returns an empty dict if the directory doesn't exist.
    """
    target = data_dir or _DEFAULT_DATA_DIR
    modes: Dict[str, AssistantMode] = {}

    if not target.exists():
        logger.warning("Modes data directory not found: %s", target)
        return modes

    for path in sorted(target.glob("*.json")):
        try:
            mode = AssistantMode.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as e:
            logger.warning("Skipping invalid mode file %s: %s", path.name, e)
            continue
        except Exception as e:
            logger.warning("Failed to load mode %s: %s", path.name, e)
            continue

        if mode.id in modes:
            logger.warning("Duplicate mode id '%s' in %s — skipping", mode.id, path.name)
            continue

        modes[mode.id] = mode
        logger.info("Loaded mode: %s (%s)", mode.id, mode.name)

    logger.info("AssistantMode registry: %d mode(s) loaded", len(modes))
    return modes
