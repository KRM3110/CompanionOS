import json
import logging
from pathlib import Path
from typing import Dict

PERSONAS_DIR = Path("/app/personas")

REQUIRED_FIELDS = {
    "id",
    "name",
    "description",
    "sliders",
    "style",
    "memory_policy",
    "ethical_bounds",
    "tool_permissions",
}


def _is_valid_persona(data: dict) -> bool:
    return REQUIRED_FIELDS.issubset(data.keys())


def load_personas() -> Dict[str, dict]:
    personas: Dict[str, dict] = {}

    if not PERSONAS_DIR.exists():
        logging.warning("Personas directory not found: %s", PERSONAS_DIR)
        return personas

    for path in PERSONAS_DIR.glob("*.json"):
        try:
            with open(path, "r") as f:
                data = json.load(f)

            if not _is_valid_persona(data):
                logging.warning("Skipping invalid persona (missing fields): %s", path.name)
                continue

            persona_id = data["id"]
            if persona_id in personas:
                logging.warning("Duplicate persona id '%s' in %s — skipping", persona_id, path.name)
                continue

            personas[persona_id] = data

        except Exception as e:
            logging.warning("Failed to load persona %s: %s", path.name, e)

    return personas