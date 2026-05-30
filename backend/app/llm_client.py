"""
llm_client.py - Centralized Async LLM Client for CompanionOS.

Powered by LangChain + Google Gemini. All chat and generate calls route through
here. Gemini also provides RAG embeddings (see rag/embedder.py).

Public API:
    llm_chat     - multi-turn conversation (system / user / assistant messages)
    llm_generate - single-prompt completion (wraps llm_chat internally)

Lifecycle hooks init_llm_client / close_llm_client are no-ops kept for
main.py startup/shutdown hook compatibility.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _build_llm(
    max_tokens: Optional[int] = None,
    timeout_s: Optional[int] = None,
) -> ChatGoogleGenerativeAI:
    """Instantiate a ChatGoogleGenerativeAI client from current settings."""
    kwargs: Dict[str, Any] = {
        "model": settings.gemini_model,
        "google_api_key": settings.gemini_api_key,
        "temperature": 0.7,
    }
    if max_tokens:
        kwargs["max_output_tokens"] = max_tokens
    if timeout_s:
        kwargs["timeout"] = timeout_s
    return ChatGoogleGenerativeAI(**kwargs)


def _to_langchain_messages(messages: List[Dict[str, str]]) -> List[BaseMessage]:
    """Convert message dicts to LangChain message objects."""
    lc: List[BaseMessage] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system":
            lc.append(SystemMessage(content=content))
        elif role == "assistant":
            lc.append(AIMessage(content=content))
        else:
            lc.append(HumanMessage(content=content))
    return lc


async def llm_chat(
    messages: List[Dict[str, str]],
    timeout_s: int = 60,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """
    Send a multi-turn chat request to Google Gemini via LangChain.

    Args:
        messages:   List of {"role": "system"|"user"|"assistant", "content": "..."} dicts.
        timeout_s:  Hard upper bound on the LLM call. Passed to the Gemini client AND
                    enforced as an outer asyncio.wait_for so a hung connection is killed.
        model:      Optional model override (e.g. "gemini-1.5-pro" for a harder task).
        max_tokens: Cap on output tokens. Passed as max_output_tokens to the Gemini client.

    Returns:
        The assistant's response as a plain string.
    """
    llm = _build_llm(max_tokens=max_tokens, timeout_s=timeout_s)
    if model:
        llm.model = model
    lc_messages = _to_langchain_messages(messages)
    response = await asyncio.wait_for(llm.ainvoke(lc_messages), timeout=timeout_s)
    return response.content


async def llm_generate(
    prompt: str,
    timeout_s: int = 60,
    model: Optional[str] = None,
) -> str:
    """
    Send a single-prompt completion request to Gemini via LangChain.

    Wraps llm_chat internally — the prompt is sent as a plain user message.

    Args:
        prompt:    The complete assembled prompt string.
        timeout_s: Hard upper bound on the LLM call (forwarded to llm_chat).
        model:     Optional model override.

    Returns:
        The model's response as a plain string.
    """
    return await llm_chat(
        [{"role": "user", "content": prompt}],
        timeout_s=timeout_s,
        model=model,
    )


# ---------------------------------------------------------------------------
# Lifecycle hooks — no-ops (no persistent client to open/close)
# ---------------------------------------------------------------------------
async def init_llm_client() -> None:
    """No-op kept for startup hook compatibility."""
    logger.info("LLM client ready — provider: Google Gemini (%s)", settings.gemini_model)


async def close_llm_client() -> None:
    """No-op kept for shutdown hook compatibility."""
