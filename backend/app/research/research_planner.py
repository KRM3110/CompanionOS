import logging
import re
from pathlib import Path
from typing import List

from ..llm_client import llm_chat

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts" / "research"


def _load_prompt(name: str) -> str:
    """Load a prompt from prompts/research/<name>."""
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


async def plan_queries(question: str) -> List[str]:
    """
    Ask the LLM to decompose a research question into 3–5 focused search queries.
    Returns a list of query strings.
    """
    system_prompt = _load_prompt("planner.txt")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Research question: {question}"},
    ]
    try:
        raw = await llm_chat(messages, timeout_s=45, max_tokens=300)
        return _parse_numbered_list(raw)
    except Exception as e:
        logger.error("Research planner LLM call failed: %s", e)
        # Fall back to using the original question as-is
        return [question]


def _parse_numbered_list(text: str) -> List[str]:
    """Extract lines from a numbered list like '1. foo\n2. bar'."""
    queries: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        # Match lines that start with a number followed by . or )
        match = re.match(r"^\d+[\.\)]\s+(.+)$", line)
        if match:
            queries.append(match.group(1).strip())
    if not queries:
        # If the LLM didn't follow the format, split by newlines and filter empties
        queries = [line.strip() for line in text.splitlines() if line.strip()]
    return queries[:5]  # cap at 5
