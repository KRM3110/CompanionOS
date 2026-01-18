"""
DB-facing execution for alerts.
Handles database operations for alert management.
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from ...db import (
    create_alert,
    list_alerts,
    update_alert_status,
)

logger = logging.getLogger(__name__)


def execute_alert_creation(
    alerts: List[Dict[str, Any]],
    session_id: Optional[str] = None,
    scope: str = "session",
) -> List[Dict[str, Any]]:
    """
    Execute alert creation from extractor output.
    
    Args:
        alerts: List of alert dicts with keys: title, body, due_at, repeat_rule
        session_id: Optional session ID for session-scoped alerts
        scope: "global" or "session"
    
    Returns:
        List of created alert events for pipeline.tool_events
    """
    tool_events = []
    
    for alert_data in alerts[:2]:  # Cap at 2 per turn
        try:
            print(f"[DEBUG] Processing alert data: {alert_data}")
            title = str(alert_data.get("title") or "").strip()
            body = str(alert_data.get("body") or "").strip()
            due_at = str(alert_data.get("due_at") or "").strip()
            confidence = alert_data.get("confidence", 0.8)
            source_message_id = alert_data.get("source_message_id")
            
            if not title or not due_at:
                logger.warning(f"Skipping alert with missing title or due_at: {alert_data}")
                print(f"[DEBUG] Missing title or due_at. Title: '{title}', Due: '{due_at}'")
                continue
            
            # Validate confidence
            try:
                confidence = float(confidence)
                confidence = max(0.0, min(1.0, confidence))
            except (ValueError, TypeError):
                confidence = 0.8
            
            print(f"[DEBUG] Creating alert in DB: {title} at {due_at} (scope={scope})")
            # Create alert in DB
            alert_id = create_alert(
                scope=scope,
                session_id=session_id if scope == "session" else None,
                title=title,
                body=body,
                due_at=due_at,
                confidence=confidence,
                source_message_id=source_message_id,
            )
            print(f"[DEBUG] Alert created successfully with ID: {alert_id}")
            
            # Add tool event
            tool_events.append({
                "type": "alert_created",
                "alert_id": alert_id,
                "title": title,
                "due_at": due_at,
            })
            
            logger.info(f"Created alert: {title} (due: {due_at})")
            
        except Exception as e:
            print(f"[DEBUG] ERROR creating alert: {e}")
            logger.error(f"Failed to create alert {alert_data}: {e}", exc_info=True)
    
    return tool_events


def get_alerts_for_session(
    session_id: str,
    scope: str = "session",
    status: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Get alerts for a session."""
    return list_alerts(scope=scope, session_id=session_id, status=status, limit=limit)


def get_global_alerts(status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Get global alerts."""
    return list_alerts(scope="global", session_id=None, status=status, limit=limit)


def mark_alert_done(alert_id: str) -> bool:
    """Mark an alert as done."""
    return update_alert_status(alert_id, "done")


def mark_alert_cancelled(alert_id: str) -> bool:
    """Mark an alert as cancelled."""
    return update_alert_status(alert_id, "cancelled")
