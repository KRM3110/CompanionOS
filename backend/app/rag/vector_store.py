"""
rag/vector_store.py — ChromaDB vector store interface for CompanionOS RAG.

Uses ChromaDB's PersistentClient to maintain one collection per workspace.
Each collection stores chunks as documents with their embeddings and metadata,
enabling cosine similarity search at query time.

Design notes:
  - One ChromaDB collection per workspace (named "ws_{workspace_id}").
  - Chunks are identified by composite IDs: "{doc_id}_chunk_{i}".
  - Deleting a document filters by doc_id metadata; deleting a workspace
    deletes the entire collection.
  - The ChromaDB path is read from settings (CHROMA_DATA_PATH env var) so it
    uses the Docker volume mount correctly.
  - Thread-safe: ChromaDB PersistentClient handles concurrent access.
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _get_chroma_path() -> str:
    """Returns the ChromaDB data path from settings (env-configurable)."""
    from ..config import get_settings
    path = Path(get_settings().chroma_data_path)
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def _get_client():
    """Returns a ChromaDB PersistentClient pointed at the configured data path."""
    try:
        import chromadb
    except ImportError:
        raise ImportError("chromadb is required: pip install chromadb")
    return chromadb.PersistentClient(path=_get_chroma_path())


def _collection_name(workspace_id: str) -> str:
    """Sanitizes workspace_id into a valid ChromaDB collection name.

    ChromaDB collection names must be 3–63 chars, alphanumeric + dash/underscore.
    """
    safe = workspace_id.replace("-", "_")[:50]
    return f"ws_{safe}"


def upsert_chunks(
    workspace_id: str,
    doc_id: str,
    filename: str,
    chunks: List[str],
    embeddings: List[List[float]],
) -> int:
    """
    Upserts text chunks and their embeddings into the workspace's ChromaDB collection.

    Args:
        workspace_id: The workspace UUID.
        doc_id:       The document UUID — stored as metadata for later deletion.
        filename:     Original filename, stored in metadata so retrieval results
                      can identify their source without a DB round-trip.
        chunks:       List of text chunk strings.
        embeddings:   Corresponding embedding vectors (same length as chunks).

    Returns:
        Number of chunks successfully upserted.

    Raises:
        ValueError: If chunks and embeddings have different lengths.
    """
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"upsert_chunks: chunks ({len(chunks)}) and embeddings ({len(embeddings)}) must match"
        )
    if not chunks:
        return 0

    client = _get_client()
    collection = client.get_or_create_collection(
        name=_collection_name(workspace_id),
        metadata={"hnsw:space": "cosine"},
    )

    ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
    metadatas = [
        {"doc_id": doc_id, "filename": filename, "chunk_index": i}
        for i in range(len(chunks))
    ]

    collection.upsert(
        ids=ids,
        documents=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
    )
    logger.info(
        "Upserted %d chunks for doc=%s workspace=%s", len(chunks), doc_id, workspace_id
    )
    return len(chunks)


def search(
    workspace_id: str,
    query_embedding: List[float],
    top_k: int = 3,
    doc_id_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Performs cosine similarity search in a workspace's ChromaDB collection.

    Args:
        workspace_id:    The workspace UUID to search within.
        query_embedding: Embedded query vector.
        top_k:           Number of top results to return.
        doc_id_filter:   If set, restrict results to a specific document.

    Returns:
        List of result dicts: [{text, doc_id, filename, chunk_index, score}]
        Returns empty list if the collection doesn't exist or has no documents.
    """
    client = _get_client()
    col_name = _collection_name(workspace_id)

    try:
        collection = client.get_collection(name=col_name)
    except Exception:
        logger.debug("No ChromaDB collection found for workspace %s", workspace_id)
        return []

    count = collection.count()
    if count == 0:
        return []

    where = {"doc_id": doc_id_filter} if doc_id_filter else None

    try:
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, count),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        logger.warning("ChromaDB search failed for workspace %s: %s", workspace_id, e)
        return []

    output = []
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]

    for text, meta, dist in zip(docs, metas, dists):
        output.append(
            {
                "text": text,
                "doc_id": meta.get("doc_id", ""),
                "filename": meta.get("filename", ""),
                "chunk_index": meta.get("chunk_index", 0),
                # Convert cosine distance → similarity score in [0, 1]
                "score": round(max(0.0, 1.0 - float(dist)), 4),
            }
        )

    return output


def workspace_chunk_count(workspace_id: str) -> int:
    """Returns the total number of chunks stored for a workspace."""
    client = _get_client()
    try:
        collection = client.get_collection(name=_collection_name(workspace_id))
        return collection.count()
    except Exception:
        return 0


def delete_document(workspace_id: str, doc_id: str) -> bool:
    """
    Removes all chunks belonging to a specific document from the workspace collection.

    Returns True if deletion succeeded, False if the collection doesn't exist.
    """
    client = _get_client()
    col_name = _collection_name(workspace_id)

    try:
        collection = client.get_collection(name=col_name)
        collection.delete(where={"doc_id": doc_id})
        logger.info("Deleted chunks for doc=%s from workspace=%s", doc_id, workspace_id)
        return True
    except Exception as e:
        logger.warning("Failed to delete doc %s chunks: %s", doc_id, e)
        return False


def delete_workspace(workspace_id: str) -> bool:
    """
    Deletes the entire ChromaDB collection for a workspace.

    Returns True if the collection was deleted, False if it didn't exist.
    """
    client = _get_client()
    col_name = _collection_name(workspace_id)

    try:
        client.delete_collection(name=col_name)
        logger.info("Deleted ChromaDB collection for workspace=%s", workspace_id)
        return True
    except Exception as e:
        logger.warning("Failed to delete collection for workspace %s: %s", workspace_id, e)
        return False
