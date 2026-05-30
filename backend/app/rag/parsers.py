"""
rag/parsers.py — Document text extraction for CompanionOS RAG pipeline.

Supports PDF, DOCX, TXT, and Markdown files. After extraction, text is
chunked into overlapping segments suitable for embedding and retrieval.

Chunking strategy:
  - Character-level sliding window (not token-level) for simplicity.
  - Overlap between chunks ensures context isn't lost at boundaries.
  - Default chunk_size=500, overlap=50 — comfortably under the Gemini
    embedding model's input limit.
"""

from __future__ import annotations
import io
import logging
from typing import List

logger = logging.getLogger(__name__)


def parse_pdf(file_bytes: bytes) -> str:
    """
    Extracts plain text from a PDF byte stream using pypdf.

    Args:
        file_bytes: Raw PDF file bytes.

    Returns:
        Full extracted text as a single string, pages joined by newlines.

    Raises:
        ImportError: If pypdf is not installed.
        Exception: On corrupt or unreadable PDF.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError("pypdf is required for PDF parsing: pip install pypdf")

    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            pages.append(text.strip())
    return "\n".join(pages)


def parse_docx(file_bytes: bytes) -> str:
    """
    Extracts plain text from a DOCX byte stream using python-docx.

    Args:
        file_bytes: Raw DOCX file bytes.

    Returns:
        Full document text, paragraphs joined by newlines.

    Raises:
        ImportError: If python-docx is not installed.
    """
    try:
        from docx import Document
    except ImportError:
        raise ImportError("python-docx is required for DOCX parsing: pip install python-docx")

    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def parse_text(file_bytes: bytes) -> str:
    """
    Decodes a raw text file (TXT or MD) from bytes to UTF-8 string.

    Args:
        file_bytes: Raw file bytes.

    Returns:
        Decoded text content.
    """
    try:
        return file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return file_bytes.decode("latin-1", errors="replace")


def extract_text(file_bytes: bytes, file_type: str) -> str:
    """
    Route bytes to the correct parser based on file_type and return plain text.
    """
    ft = file_type.lower().lstrip(".")
    if ft == "pdf":
        return parse_pdf(file_bytes)
    if ft in ("docx", "doc"):
        return parse_docx(file_bytes)
    if ft in ("txt", "md", "markdown"):
        return parse_text(file_bytes)

    logger.warning("Unknown file type '%s', treating as plain text", file_type)
    return parse_text(file_bytes)


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    Splits a long text into overlapping character-level chunks.

    Args:
        text:       Full text to split.
        chunk_size: Maximum characters per chunk.
        overlap:    Character overlap between consecutive chunks to preserve context.

    Returns:
        List of non-empty text chunk strings.

    Example:
        chunk_text("abcde", chunk_size=3, overlap=1) → ["abc", "cde"]
    """
    text = text.strip()
    if not text:
        return []

    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start += chunk_size - overlap

    return chunks


def extract_chunks(file_bytes: bytes, file_type: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    """
    Route bytes to the correct parser based on file_type, then chunk the result.

    Args:
        file_bytes: Raw uploaded file bytes.
        file_type:  One of "pdf", "docx", "txt", "md".
        chunk_size: Characters per chunk.
        overlap:    Overlap between chunks.

    Returns:
        List of text chunk strings ready for embedding.
    """
    text = extract_text(file_bytes, file_type)
    return chunk_text(text, chunk_size=chunk_size, overlap=overlap)
