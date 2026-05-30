"""
utils.py — Shared Utility Functions for CompanionOS.

This module centralizes all cross-cutting parsing and data-transformation utilities
that are used by multiple modules. By housing them here, we eliminate copy-pasted
code across the agent and extractor modules.

Primary responsibility:
  - Parsing LLM output formatted in TOON (Token-Oriented Object Notation) back into
    Python dictionaries. TOON is a compact, YAML-like format that reduces LLM output
    token consumption by 30-60% compared to JSON, since it omits curly braces, array
    brackets, and redundant double-quotes.

Approach:
  - TOON output is structurally identical to simple YAML, so `yaml.safe_load` is used
    as the primary parser — no custom grammar is needed.
  - A regex pre-pass strips any markdown fences (```toon, ```yaml) that the LLM may
    wrap its output in, making the parser tolerant of model verbosity.
  - A JSON fallback catches cases where a model reverted to JSON despite instructions.
"""

import json
import re
import yaml
from typing import Any, Dict, Optional


def parse_toon_output(text: str) -> Optional[Dict[str, Any]]:
    """
    Parses a raw LLM response expected to be in TOON or YAML format.

    TOON output from the LLM looks like clean, indented key-value pairs without
    any of the structural noise found in JSON (no {}, [], or "" required):

        verdict: PASS
        reason: Response is safe and on-persona.
        risk_tags:
          - none

    This function handles three formats in order of preference:
      1. A fenced TOON or YAML block (```toon ... ``` or ```yaml ... ```)
      2. Raw, unfenced TOON/YAML text
      3. Fallback: a fenced JSON block (```json ... ```) for model non-compliance

    Args:
        text: Raw string output from the LLM response.

    Returns:
        A Python dict if parsing succeeds, or None if all strategies fail.
        Returning None signals to the caller that the response was malformed,
        so they can fall back to a safe default (e.g., PASS for the judge).
    """
    text = text.strip()

    # --- Strategy 1: Strip markdown fences if present ---
    # Some models wrap their structured output in ```toon or ```yaml blocks
    # even when instructed not to. We strip the fence and parse the inner content.
    fence = re.search(r"```(?:toon|yaml)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    try:
        # --- Strategy 2: Parse as YAML ---
        # TOON is structurally compatible with YAML. `yaml.safe_load` handles
        # unquoted strings, nested indentation, and inline lists correctly.
        # We use `safe_load` (not `load`) to prevent arbitrary Python object
        # instantiation from untrusted LLM output.
        parsed = yaml.safe_load(text)
        if isinstance(parsed, dict):
            return parsed
        # If YAML returns a list or scalar, it means the model produced
        # an unexpected root type — we fall through to the JSON fallback.
    except Exception:
        # YAML parse error — model may have produced something structurally invalid.
        # Fall through to the JSON fallback below.
        pass

    # --- Strategy 3: Fallback — fenced JSON block ---
    # In rare cases, a model may default back to JSON even after TOON instructions.
    # We still accept it to ensure the system stays functional.
    json_fence = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if json_fence:
        try:
            return json.loads(json_fence.group(1))
        except json.JSONDecodeError:
            pass

    # All strategies exhausted — caller must handle None gracefully.
    return None
