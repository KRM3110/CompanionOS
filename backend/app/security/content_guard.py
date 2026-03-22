"""
content_guard.py — Orchestrator for the Content Guard pipeline (Feature 3).

Pipeline:
  1. Stage 1: injection_detector.scan()   — fast regex
  2. (if SUSPICIOUS) Stage 2: llm_guard.scan_chunks() — Ollama LLM check
  3. (if FLAGGED) sanitizer.sanitize()   — strip injections from text
  4. Return GuardResult with final verdict + sanitised text

Outcomes:
  CLEAN   → index full original text
  FLAGGED → index sanitised text (injection phrases replaced)
  BLOCKED → raise HTTPException(400) — do not index
"""

import logging
from dataclasses import dataclass, field
from typing import List

from . import injection_detector, llm_guard, sanitizer

logger = logging.getLogger(__name__)


@dataclass
class GuardResult:
    verdict: str               # "CLEAN" | "FLAGGED" | "BLOCKED"
    sanitized_text: str        # original text if CLEAN, sanitised if FLAGGED
    patterns_hit: List[str] = field(default_factory=list)
    llm_reason: str = ""


def scan(text: str) -> GuardResult:
    """
    Run the full two-stage content guard on raw document text.

    Args:
        text: Raw extracted text from the uploaded document.

    Returns:
        GuardResult with the final verdict and (possibly sanitised) text.
    """
    # ------------------------------------------------------------------
    # Stage 1 — Fast regex scan
    # ------------------------------------------------------------------
    stage1 = injection_detector.scan(text)
    logger.info("Content guard Stage 1: verdict=%s patterns=%s", stage1.verdict, stage1.patterns_hit)

    if stage1.verdict == "CLEAN":
        return GuardResult(
            verdict="CLEAN",
            sanitized_text=text,
        )

    # ------------------------------------------------------------------
    # Stage 2 — LLM secondary verdict (only runs when Stage 1 flags)
    # ------------------------------------------------------------------
    stage2 = llm_guard.scan_chunks(stage1.suspicious_chunks)
    logger.info("Content guard Stage 2: verdict=%s reason=%s", stage2["verdict"], stage2["reason"])

    final_verdict = stage2["verdict"]
    llm_reason = stage2["reason"]

    if final_verdict == "BLOCKED":
        return GuardResult(
            verdict="BLOCKED",
            sanitized_text="",  # never indexed
            patterns_hit=stage1.patterns_hit,
            llm_reason=llm_reason,
        )

    if final_verdict == "FLAGGED":
        clean_text = sanitizer.sanitize(text, stage1.patterns_hit)
        return GuardResult(
            verdict="FLAGGED",
            sanitized_text=clean_text,
            patterns_hit=stage1.patterns_hit,
            llm_reason=llm_reason,
        )

    # Stage 2 returned CLEAN despite Stage 1 hit — trust the LLM, but still sanitise lightly
    # (conservative: Stage 1 regex hit something, so we sanitise even on CLEAN LLM verdict)
    clean_text = sanitizer.sanitize(text, stage1.patterns_hit)
    return GuardResult(
        verdict="FLAGGED",
        sanitized_text=clean_text,
        patterns_hit=stage1.patterns_hit,
        llm_reason="Stage 1 regex hit; LLM found CLEAN but content was sanitised conservatively.",
    )
