"""
rag/rag_retriever.py — RAG query orchestrator for CompanionOS.

Given a workspace ID and a user query, this module:
  1. Embeds the query using the configured Gemini embedding model.
  2. Runs cosine similarity search in the workspace's ChromaDB collection.
  3. Formats the top-k results into a human-readable context string
     that gets injected into the LLM system prompt.

The returned context string follows a structured format so the LLM
can cite sources clearly in its response.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, TypedDict

from .embedder import embed_text
from .vector_store import search
from ..db import get_document

logger = logging.getLogger(__name__)


class RAGSource(TypedDict):
    document_id: str
    filename: str
    chunk_index: int
    score: float
    snippet: str


def _snippet(text: str, max_chars: int = 220) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "…"


def format_context(sources: List[RAGSource]) -> str:
    """
    Formats structured sources into an injectable context string for the system prompt.
    """
    if not sources:
        return ""

    lines: List[str] = ["[Document Context]"]
    for s in sources:
        lines.append(s["snippet"])
        lines.append("")
    return "\n".join(lines).strip()


async def retrieve_sources(
    workspace_id: str,
    query: str,
    top_k: int = 3,
    doc_filename_map: Optional[Dict[str, str]] = None,
) -> List[RAGSource]:
    """
    Retrieves top-k machine-readable RAG source objects for a workspace query.
    """
    if not query.strip():
        return []

    try:
        query_embedding = await embed_text(query)
    except Exception as e:
        logger.warning("Failed to embed query for RAG retrieval: %s", e)
        return []

    results = search(workspace_id, query_embedding, top_k=top_k)
    if not results:
        return []

    filename_cache: Dict[str, str] = doc_filename_map or {}
    sources: List[RAGSource] = []
    for result in results:
        doc_id = result["doc_id"]
        filename_meta = (result.get("filename") or "").strip()
        chunk_idx = int(result["chunk_index"])
        text = result["text"]
        score = float(result.get("score", 0.0))

        if filename_meta:
            filename_cache[doc_id] = filename_meta
        elif doc_id not in filename_cache:
            try:
                doc = await get_document(doc_id)
                filename_cache[doc_id] = doc["filename"] if doc else doc_id
            except Exception:
                filename_cache[doc_id] = doc_id

        sources.append(
            {
                "document_id": doc_id,
                "filename": filename_cache[doc_id],
                "chunk_index": chunk_idx,
                "score": round(score, 4),
                "snippet": _snippet(text),
            }
        )

    return sources


async def retrieve(
    workspace_id: str,
    query: str,
    top_k: int = 3,
    doc_filename_map: Optional[Dict[str, str]] = None,
) -> str:
    """
    Retrieves the most relevant document chunks for a query and formats them
    as an injectable context string for the system prompt.

    Args:
        workspace_id:     The workspace to search within.
        query:            The user's current message / search query.
        top_k:            Number of chunks to retrieve (default 3).
        doc_filename_map: Optional pre-fetched {doc_id: filename} cache to avoid
                          per-chunk DB lookups. If None, filenames are fetched from DB.

    Returns:
        A formatted context string like:
            [Document Context]
            Source: report.pdf (chunk 2)
            The quarterly revenue increased by 23%...

            Source: notes.txt (chunk 0)
            Meeting agenda: Q1 review...

        Returns an empty string if the workspace has no documents or the query
        lacks sufficient similarity to any chunk.
    """
    sources = await retrieve_sources(
        workspace_id=workspace_id,
        query=query,
        top_k=top_k,
        doc_filename_map=doc_filename_map,
    )
    return format_context(sources)
