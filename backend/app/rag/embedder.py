"""
rag/embedder.py — Text embedding via Google Gemini for CompanionOS RAG.

Wraps `GoogleGenerativeAIEmbeddings` from `langchain-google-genai` so callers
get a small async surface that matches the rest of the codebase.

Design decisions:
  - One cached embeddings client per process (built on first use).
  - `embed_chunks` uses `aembed_documents` for native batching — one request
    for the whole chunk list instead of one request per chunk.
  - Graceful degradation: on failure we log and return whatever we have so
    indexing of partially-good documents can still proceed.
"""

from __future__ import annotations
import asyncio
import logging
from functools import lru_cache
from typing import List

from langchain_google_genai import GoogleGenerativeAIEmbeddings

from ..config import get_settings

logger = logging.getLogger(__name__)

EMBED_QUERY_TIMEOUT_S = 30
EMBED_BATCH_TIMEOUT_S = 120


@lru_cache(maxsize=1)
def _get_client() -> GoogleGenerativeAIEmbeddings:
    settings = get_settings()
    return GoogleGenerativeAIEmbeddings(
        model=settings.embed_model,
        google_api_key=settings.gemini_api_key,
    )


async def embed_text(text: str, embed_model: str | None = None) -> List[float]:
    """
    Embed a single text string using the configured Gemini embedding model.

    `embed_model` is accepted for backward compatibility but ignored — the
    model is resolved from settings at client construction time.
    """
    del embed_model
    client = _get_client()
    return await asyncio.wait_for(
        client.aembed_query(text), timeout=EMBED_QUERY_TIMEOUT_S
    )


async def embed_chunks(
    chunks: List[str],
    embed_model: str | None = None,
) -> List[List[float]]:
    """
    Embed a list of text chunks in a single batched call.

    Empty / whitespace-only chunks are filtered before sending. On a batch
    failure (or timeout) we log and return an empty list so the caller can
    mark the document as failed-to-index rather than crash.
    """
    del embed_model
    cleaned = [c for c in chunks if c and c.strip()]
    if not cleaned:
        return []

    try:
        client = _get_client()
        embeddings = await asyncio.wait_for(
            client.aembed_documents(cleaned), timeout=EMBED_BATCH_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        logger.warning("Embedding batch timed out after %ds (%d chunks)", EMBED_BATCH_TIMEOUT_S, len(cleaned))
        return []
    except Exception as e:
        logger.warning("Failed to embed %d chunks: %s", len(cleaned), e)
        return []

    logger.info("Embedded %d/%d chunks", len(embeddings), len(chunks))
    return embeddings
