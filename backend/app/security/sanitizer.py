"""
sanitizer.py — Strips detected injection patterns from FLAGGED documents.

Replaces each matched injection phrase with a [CONTENT REMOVED] marker so the
surrounding context (legitimate content) is preserved while the adversarial
payload is neutralised.
"""

import re
from typing import List

# Replacement marker inserted in place of removed content
REMOVAL_MARKER = "[CONTENT REMOVED]"

# We reuse the same compiled patterns from injection_detector to keep consistency
from .injection_detector import _PATTERNS


def sanitize(text: str, patterns_hit: List[str]) -> str:
    """
    Remove matched injection patterns from `text`.

    Only applies the regex substitutions for the pattern categories that were
    actually flagged in the Stage 1 scan, keeping the operation targeted.

    Args:
        text:         Raw document text that was flagged.
        patterns_hit: List of category names that Stage 1 / Stage 2 matched.

    Returns:
        Sanitised text with injection phrases replaced by REMOVAL_MARKER.
    """
    sanitized = text

    for category, regex in _PATTERNS:
        if category in patterns_hit:
            sanitized = regex.sub(REMOVAL_MARKER, sanitized)

    # Clean up multiple consecutive markers
    sanitized = re.sub(
        r"(\[CONTENT REMOVED\]\s*){2,}",
        REMOVAL_MARKER + " ",
        sanitized,
    )

    return sanitized.strip()
