"""
injection_detector.py — Stage 1 of the Content Guard pipeline.

Fast regex-based scan of raw document text. Returns a result dict with:
  - verdict:            "CLEAN" | "SUSPICIOUS"
  - patterns_hit:       list of matched pattern category names
  - suspicious_chunks:  list of text snippets that triggered patterns
                        (passed to Stage 2 llm_guard if verdict is SUSPICIOUS)
"""

import re
from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# Pattern library
# Each entry: (category_name, compiled_regex)
# ---------------------------------------------------------------------------

_PATTERNS: List[tuple] = [
    # Role override
    (
        "role_override",
        re.compile(
            r"ignore\s+(?:all\s+)?previous\s+instructions?"
            r"|disregard\s+your\s+system\s+prompt"
            r"|you\s+are\s+now\b"
            r"|act\s+as\s+if\s+you"
            r"|pretend\s+you\s+are\s+(?:a\s+)?(?:different|new|another)",
            re.IGNORECASE,
        ),
    ),
    # Instruction injection
    (
        "instruction_injection",
        re.compile(
            r"\bnew\s+instruction\s*:"
            r"|\bsystem\s+override\s*:"
            r"|\badmin\s+command\s*:"
            r"|\[INST\]"
            r"|<<SYS>>"
            r"|\boverride\s+mode\b",
            re.IGNORECASE,
        ),
    ),
    # Jailbreak markers
    (
        "jailbreak",
        re.compile(
            r"\bDAN\s+mode\b"
            r"|\bdeveloper\s+mode\b"
            r"|\bno\s+restrictions?\b"
            r"|\bunrestricted\s+mode\b"
            r"|\bbypass\s+(?:all\s+)?safety\b"
            r"|\bjailbreak\b"
            r"|\bgrandma\s+exploit\b",
            re.IGNORECASE,
        ),
    ),
    # Hidden text tricks
    (
        "hidden_text",
        re.compile(
            r"[\u200b\u200c\u200d\u2060\u2062\u2063\u2064\ufeff]"  # zero-width / invisible chars
            r"|(?:\s{20,})"  # 20+ consecutive whitespace chars (whitespace stuffing)
            r"|(?:[A-Za-z0-9+/]{40,}={0,2}(?:\s|$))",  # base64 blocks ≥40 chars
            re.UNICODE,
        ),
    ),
    # Prompt leaking
    (
        "prompt_leaking",
        re.compile(
            r"repeat\s+your\s+system\s+prompt"
            r"|print\s+your\s+(?:full\s+)?instructions?"
            r"|reveal\s+your\s+(?:full\s+)?context"
            r"|show\s+me\s+your\s+prompt"
            r"|what\s+(?:is|are)\s+your\s+instructions?",
            re.IGNORECASE,
        ),
    ),
    # Exfiltration
    (
        "exfiltration",
        re.compile(
            r"\bsend\s+(?:data\s+)?to\s+(?:https?://|www\.)"
            r"|\bPOST\s+to\s+https?://"
            r"|\bcurl\s+https?://"
            r"|\bwget\s+https?://"
            r"|\bfetch\s*\(\s*['\"]https?://",
            re.IGNORECASE,
        ),
    ),
]

# Size of context window extracted around each match (chars)
_CONTEXT_WINDOW = 200


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class DetectionResult:
    verdict: str  # "CLEAN" | "SUSPICIOUS"
    patterns_hit: List[str] = field(default_factory=list)
    suspicious_chunks: List[str] = field(default_factory=list)


def scan(text: str) -> DetectionResult:
    """
    Run all regex patterns against `text`.

    Returns DetectionResult with:
      - verdict = "CLEAN"      → no patterns matched
      - verdict = "SUSPICIOUS" → one or more patterns matched; suspicious_chunks
                                  contains context snippets for Stage 2.
    """
    patterns_hit: List[str] = []
    suspicious_chunks: List[str] = []

    for category, regex in _PATTERNS:
        for match in regex.finditer(text):
            if category not in patterns_hit:
                patterns_hit.append(category)
            start = max(0, match.start() - _CONTEXT_WINDOW)
            end = min(len(text), match.end() + _CONTEXT_WINDOW)
            chunk = text[start:end].strip()
            if chunk not in suspicious_chunks:
                suspicious_chunks.append(chunk)

    if patterns_hit:
        return DetectionResult(
            verdict="SUSPICIOUS",
            patterns_hit=patterns_hit,
            suspicious_chunks=suspicious_chunks,
        )

    return DetectionResult(verdict="CLEAN")
