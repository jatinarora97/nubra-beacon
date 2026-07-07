"""Discovery endpoints (work plan E1/N11) — emergent-topic suggestions.

Separate router so it composes into read_api without editing it:
    from community.api.discover_api import router as discover_router
    app.include_router(discover_router)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from community.store import db

router = APIRouter(prefix="/api/v1")


@router.get("/topic-suggestions")
def topic_suggestions():
    """Suggested topics awaiting a human decision, largest clusters first."""
    return db.query(
        "SELECT topic_key, label, suggested_why AS why, suggested_count AS item_count, "
        "suggested_at FROM topic_taxonomy WHERE status = 'suggested' "
        "ORDER BY suggested_count DESC NULLS LAST, suggested_at DESC")


def _transition(topic_key: str, new_status: str) -> dict:
    row = db.one(
        "UPDATE topic_taxonomy SET status = %s, active = %s "
        "WHERE topic_key = %s AND status = 'suggested' "
        "RETURNING topic_key, label, status",
        (new_status, new_status == "active", topic_key))
    if not row:
        raise HTTPException(404, "no such suggested topic (already decided?)")
    return row


@router.post("/topic-suggestions/{topic_key}/activate")
def activate_topic(topic_key: str):
    """Suggested -> active: the topic joins the taxonomy offered to enrichment."""
    return _transition(topic_key, "active")


@router.post("/topic-suggestions/{topic_key}/reject")
def reject_topic(topic_key: str):
    """Suggested -> rejected: kept so the same cluster is not re-suggested."""
    return _transition(topic_key, "rejected")
