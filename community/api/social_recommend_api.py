"""Independent API surface for ready-to-publish social recommendations."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Body, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from community.social_recommend import context as product_context
from community.store import db


router = APIRouter(prefix="/api/v1/social-recommendations", tags=["social-recommendations"])


def _who(email: str | None) -> str:
    return email or "local-dev"


def _module_error(exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": "The social recommendation module is temporarily unavailable.",
            "module": "social_recommendations",
            "error": str(exc)[:250],
        },
    )


@router.get("/status")
def status():
    try:
        run = db.one(
            """
            SELECT id, status, model, prompt_version, context_version, window_days,
                   stats, error, created_at, completed_at
            FROM social_recommendation_runs
            ORDER BY created_at DESC LIMIT 1
            """
        )
        state = db.one(
            """
            SELECT last_success_at, last_error, last_error_at, items_last_run
            FROM pipeline_state
            WHERE stage='social_recommend' AND source='ready_copy'
            """
        )
        return {
            "module": "social_recommendations",
            "ready": True,
            "context": product_context.summary(),
            "latest_run": run,
            "pipeline_state": state,
        }
    except Exception as exc:
        return _module_error(exc)


@router.get("/preview")
def preview(days: int = Query(30, ge=1, le=90)):
    """Read-only evidence readiness; never calls Claude."""
    try:
        from community.social_recommend.service import preview as build_preview

        return build_preview(days)
    except Exception as exc:
        return _module_error(exc)


@router.get("")
def list_recommendations(
    segment: Literal["retail", "api"] | None = None,
    status: Literal["draft", "approved", "rejected", "published"] | None = None,
    platform: Literal["linkedin", "x", "instagram", "youtube"] | None = None,
    limit: int = Query(30, ge=1, le=100),
):
    try:
        where = [
            "r.run_id = (SELECT id FROM social_recommendation_runs "
            "WHERE status='succeeded' ORDER BY created_at DESC LIMIT 1)"
        ]
        params: dict = {"limit": limit}
        if segment:
            where.append("r.segment = %(segment)s")
            params["segment"] = segment
        if status:
            where.append("r.status = %(status)s")
            params["status"] = status
        if platform:
            where.append("r.platform = %(platform)s")
            params["platform"] = platform
        rows = db.query(
            """
            SELECT r.id, r.run_id, r.day, r.recommendation_key, r.segment,
                   r.platform, r.post_format, r.title, r.hook, r.body, r.cta,
                   r.exact_copy, r.hashtags, r.mapped_features, r.source_evidence,
                   r.rationale, r.visual_brief, r.recommended_timing,
                   r.priority_score, r.status, r.compliance_status, r.model,
                   r.prompt_version, r.context_version, r.edited_by,
                   r.created_at, r.updated_at
            FROM social_recommendations r
            WHERE
            """ + " AND ".join(where) +
            " ORDER BY r.priority_score DESC, r.id ASC LIMIT %(limit)s",
            params,
        )
        return rows
    except Exception as exc:
        return _module_error(exc)


@router.post("/generate")
def generate(body: dict = Body(default={})):
    """Generate a new stored set. A failure is returned locally to this route."""
    days = body.get("days", 30)
    if not isinstance(days, int) or not 1 <= days <= 90:
        raise HTTPException(400, "days must be an integer between 1 and 90")
    try:
        from community.social_recommend.service import run

        result = run(days=days, force=True)
        return JSONResponse(status_code=200 if result.get("ok") else 422, content=result)
    except Exception as exc:
        return _module_error(exc)


@router.post("/{recommendation_id}/status")
def change_status(
    recommendation_id: int,
    body: dict = Body(...),
    x_auth_request_email: str | None = Header(None),
):
    new_status = body.get("status")
    if new_status not in {"approved", "rejected", "published"}:
        raise HTTPException(400, "status must be approved, rejected, or published")
    try:
        with db.tx() as conn:
            row = conn.execute(
                "SELECT status FROM social_recommendations WHERE id=%s FOR UPDATE",
                (recommendation_id,),
            ).fetchone()
            if not row:
                raise HTTPException(404, "recommendation not found")
            conn.execute(
                "UPDATE social_recommendations SET status=%s, edited_by=%s, "
                "updated_at=now() WHERE id=%s",
                (new_status, _who(x_auth_request_email), recommendation_id),
            )
            conn.execute(
                "INSERT INTO social_recommendation_events "
                "(recommendation_id, event_type, actor, note) VALUES (%s,%s,%s,%s)",
                (
                    recommendation_id, new_status, _who(x_auth_request_email),
                    (body.get("note") or "")[:500] or None,
                ),
            )
        return {"ok": True, "id": recommendation_id, "status": new_status}
    except HTTPException:
        raise
    except Exception as exc:
        return _module_error(exc)


@router.post("/{recommendation_id}/edit")
def edit_copy(
    recommendation_id: int,
    body: dict = Body(...),
    x_auth_request_email: str | None = Header(None),
):
    exact_copy = (body.get("exact_copy") or "").strip()
    if not exact_copy:
        raise HTTPException(400, "exact_copy is required")
    if len(exact_copy) > 12000:
        raise HTTPException(400, "exact_copy is too long")
    try:
        from community.recommend.compliance import check

        ok, reasons = check(
            exact_copy,
            "social_recommendation_manual_edit",
            {"kind": "social_recommendation_edit", "id": recommendation_id},
        )
        if not ok:
            raise HTTPException(422, {"message": "Copy failed compliance", "reasons": reasons})
        with db.tx() as conn:
            row = conn.execute(
                "SELECT id FROM social_recommendations WHERE id=%s FOR UPDATE",
                (recommendation_id,),
            ).fetchone()
            if not row:
                raise HTTPException(404, "recommendation not found")
            conn.execute(
                "UPDATE social_recommendations SET exact_copy=%s, edited_by=%s, "
                "updated_at=now() WHERE id=%s",
                (exact_copy, _who(x_auth_request_email), recommendation_id),
            )
            conn.execute(
                "INSERT INTO social_recommendation_events "
                "(recommendation_id, event_type, actor, note) VALUES (%s,'edited',%s,%s)",
                (
                    recommendation_id, _who(x_auth_request_email),
                    (body.get("note") or "Manual copy edit")[:500],
                ),
            )
        return {"ok": True, "id": recommendation_id, "exact_copy": exact_copy}
    except HTTPException:
        raise
    except Exception as exc:
        return _module_error(exc)
