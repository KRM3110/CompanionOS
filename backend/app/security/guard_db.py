"""
guard_db.py — Database helpers for the guard_audit table (Feature 3).

Provides insert, query-by-doc, and list-all functions.
All functions are thin wrappers around raw SQLite — no ORM needed.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .db import get_conn

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.utcnow().isoformat() + "Z"


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def insert_audit_record(
    document_id: str,
    verdict: str,
    patterns_hit: Optional[List[str]] = None,
    llm_reason: Optional[str] = None,
) -> str:
    """
    Insert a guard audit record for a scanned document.

    Args:
        document_id:  ID of the document that was scanned (from documents table).
        verdict:      "CLEAN" | "FLAGGED" | "BLOCKED"
        patterns_hit: List of pattern category names that were matched (may be empty).
        llm_reason:   Reason string from Stage 2 LLM guard (may be None if Stage 2 not run).

    Returns:
        The new audit record's UUID.
    """
    audit_id = str(uuid4())
    patterns_json = json.dumps(patterns_hit or [])

    conn = get_conn()
    conn.execute(
        """
        INSERT INTO guard_audit (id, document_id, verdict, patterns_hit, llm_reason, scanned_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (audit_id, document_id, verdict, patterns_json, llm_reason, _utc_now()),
    )
    conn.commit()
    conn.close()
    logger.info("guard_audit: %s → %s (doc=%s)", audit_id, verdict, document_id)
    return audit_id


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_audit_by_doc(document_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve the guard audit record for a specific document_id.
    Returns None if no record exists (e.g. document pre-dates Feature 3).
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM guard_audit WHERE document_id = ? ORDER BY scanned_at DESC LIMIT 1",
        (document_id,),
    ).fetchone()
    conn.close()

    if not row:
        return None

    result = dict(row)
    try:
        result["patterns_hit"] = json.loads(result["patterns_hit"] or "[]")
    except (json.JSONDecodeError, TypeError):
        result["patterns_hit"] = []
    return result


def list_audit_records(
    verdict_filter: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    List guard audit records, optionally filtered by verdict.

    Args:
        verdict_filter: "CLEAN" | "FLAGGED" | "BLOCKED" | None (all)
        limit:          Max records to return (default 100).
    """
    conn = get_conn()

    if verdict_filter:
        rows = conn.execute(
            """
            SELECT * FROM guard_audit
            WHERE verdict = ?
            ORDER BY scanned_at DESC
            LIMIT ?
            """,
            (verdict_filter, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM guard_audit
            ORDER BY scanned_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    conn.close()

    results = []
    for row in rows:
        r = dict(row)
        try:
            r["patterns_hit"] = json.loads(r["patterns_hit"] or "[]")
        except (json.JSONDecodeError, TypeError):
            r["patterns_hit"] = []
        results.append(r)
    return results
