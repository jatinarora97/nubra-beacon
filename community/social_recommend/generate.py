"""DB-backed social recommendation stage.

Reads recent Beacon signals + current Nubra features, writes recommended social
post ideas and deterministic drafts. This is safe: all records start as
`suggested`; no external publishing happens.
"""
from __future__ import annotations

from datetime import datetime, timezone

from community.config.log import get_logger
from community.reference import features as db_features
from community.reference.nubra_context import feature_rows
from community.social_recommend.engine import build_recommendations
from community.social_recommend.models import FeatureContext, SourceSignal
from community.store import db, repositories as repo

log = get_logger("social_recommend")


def _feature_contexts() -> list[FeatureContext]:
    try:
        rows = db_features.current()
    except Exception:
        rows = []
    if rows:
        return [
            FeatureContext(
                id=f"f_{r.get('id')}",
                feature=r["feature"],
                description=r["description"],
                status=r["status"],
                category=r.get("category"),
                seo_keywords=r.get("seo_keywords") or [],
            )
            for r in rows
        ]

    _, fallback_rows = feature_rows()
    return [
        FeatureContext(feature=name, description=desc, status=status, category=category, seo_keywords=kws)
        for name, desc, status, category, kws in fallback_rows
    ]


def _signals(days: int = 7, limit: int = 500) -> list[SourceSignal]:
    rows = db.query(
        """
        SELECT si.source, si.source_type, si.text, si.url, si.created_at, si.raw,
               COALESCE((si.engagement->>'score')::float, 0) AS engagement_score,
               ie.topic_key, ie.intent, ie.audience
        FROM social_items si
        LEFT JOIN item_enrichment ie ON ie.item_id = si.item_id
        WHERE si.duplicate_of IS NULL
          AND si.created_at >= now() - (%s || ' days')::interval
          AND length(COALESCE(si.text, '')) >= 20
        ORDER BY COALESCE((si.engagement->>'score')::float, 0) DESC, si.created_at DESC
        LIMIT %s
        """,
        (days, limit),
    )
    return [
        SourceSignal(
            source=r["source"],
            source_type=r["source_type"],
            text=r["text"] or "",
            url=r["url"] or "",
            topic_key=r.get("topic_key"),
            intent=r.get("intent"),
            audience=r.get("audience"),
            engagement_score=float(r.get("engagement_score") or 0),
            created_at=r["created_at"].isoformat() if r.get("created_at") else None,
            raw=r.get("raw") or {},
        )
        for r in rows
    ]


def _persist(rec) -> bool:
    with db.conn() as c:
        row = c.execute(
            """
            INSERT INTO social_post_recommendations (
                recommendation_key, title, summary, recommendation_type,
                target_persona, platform, format_family, priority_score,
                mapped_features, source_signals, reason, post_angle, updated_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
            ON CONFLICT (recommendation_key) DO UPDATE SET
                title = EXCLUDED.title,
                summary = EXCLUDED.summary,
                recommendation_type = EXCLUDED.recommendation_type,
                target_persona = EXCLUDED.target_persona,
                platform = EXCLUDED.platform,
                format_family = EXCLUDED.format_family,
                priority_score = EXCLUDED.priority_score,
                mapped_features = EXCLUDED.mapped_features,
                source_signals = EXCLUDED.source_signals,
                reason = EXCLUDED.reason,
                post_angle = EXCLUDED.post_angle,
                updated_at = now()
            RETURNING id, (xmax = 0) AS inserted
            """,
            (
                rec.recommendation_key,
                rec.title,
                rec.summary,
                rec.recommendation_type,
                rec.target_persona,
                rec.platform,
                rec.format_family,
                rec.priority_score,
                db.jsonb(rec.mapped_features),
                db.jsonb(rec.source_signals),
                rec.reason,
                rec.post_angle,
            ),
        ).fetchone()
        recommendation_id = row["id"]
        c.execute(
            """
            INSERT INTO social_post_drafts (
                recommendation_id, channel, draft_copy, creative_brief, prompt_version
            )
            VALUES (%s,%s,%s,%s,%s)
            """,
            (recommendation_id, rec.platform, rec.draft_copy, rec.creative_brief, "deterministic-v1"),
        )
        return bool(row["inserted"])


def run(days: int = 7, limit: int = 500, max_recommendations: int = 12, **_) -> dict:
    signals = _signals(days=days, limit=limit)
    feature_contexts = _feature_contexts()
    recs = build_recommendations(signals, feature_contexts, max_count=max_recommendations)
    inserted = 0
    updated = 0
    for rec in recs:
        if _persist(rec):
            inserted += 1
        else:
            updated += 1
    repo.advance_state("social_recommend", "social_posts", watermark=datetime.now(timezone.utc), items=len(recs))
    stats = {
        "signals": len(signals),
        "features": len(feature_contexts),
        "recommendations": len(recs),
        "inserted": inserted,
        "updated": updated,
    }
    log.info("social recommendations: %s", stats)
    return stats

