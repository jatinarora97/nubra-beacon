"""General content queue (/content page) — the general_marketing lens.

Same engine, endpoints and act/dismiss workflow as /api-trading/content,
without the API_TRADING_ENABLED gate (general marketing is always on).
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Header

from community.api.api_trading_api import queue_rows, queue_transition
from community.social_recommend.api_lens import GENERAL_LENS

router = APIRouter(prefix="/api/v1/content-queue", tags=["content-queue"])


@router.get("")
def content_queue(platform: str | None = None, status: str = "draft",
                  limit: int = 60, window: str | None = None,
                  from_ts: str | None = None, to_ts: str | None = None):
    return queue_rows(GENERAL_LENS, platform, status, limit,
                      window, from_ts, to_ts)


@router.post("/{brief_id}/act")
def act(brief_id: int, payload: dict = Body(default={}),
        x_auth_request_email: str | None = Header(default=None),
        x_forwarded_email: str | None = Header(default=None)):
    return queue_transition(GENERAL_LENS, brief_id, "published", "published",
                            x_auth_request_email or x_forwarded_email or "dashboard",
                            (payload.get("note") or "").strip() or None)


@router.post("/{brief_id}/dismiss")
def dismiss(brief_id: int, payload: dict = Body(default={}),
            x_auth_request_email: str | None = Header(default=None),
            x_forwarded_email: str | None = Header(default=None)):
    return queue_transition(GENERAL_LENS, brief_id, "rejected", "rejected",
                            x_auth_request_email or x_forwarded_email or "dashboard",
                            (payload.get("note") or "").strip() or None)


@router.post("/top-up", status_code=202)
def top_up():
    from community.social_recommend import api_lens
    return api_lens.top_up(lens=GENERAL_LENS)
