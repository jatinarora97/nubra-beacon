"""Core repositories (LLD-01 §11) — the shared surface stages build on.

Stage-specific queries may live in the stage modules; anything reused twice
belongs here.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from community.store import db


# ── pipeline_state ────────────────────────────────────────────────────────

def get_state(stage: str, source: str = "") -> dict | None:
    return db.one(
        "SELECT * FROM pipeline_state WHERE stage=%s AND source=%s", (stage, source)
    )


def advance_state(stage: str, source: str, *, watermark: datetime | None = None,
                  cursor: dict | None = None, items: int | None = None,
                  error: str | None = None) -> None:
    db.execute(
        """
        INSERT INTO pipeline_state (stage, source, watermark, cursor, last_success_at,
                                    last_error, last_error_at, items_last_run)
        VALUES (%(stage)s, %(source)s, %(wm)s, %(cursor)s,
                CASE WHEN %(error)s::text IS NULL THEN now() END,
                %(error)s::text, CASE WHEN %(error)s::text IS NOT NULL THEN now() END, %(items)s)
        ON CONFLICT (stage, source) DO UPDATE SET
            watermark       = COALESCE(EXCLUDED.watermark, pipeline_state.watermark),
            cursor          = COALESCE(EXCLUDED.cursor, pipeline_state.cursor),
            last_success_at = COALESCE(EXCLUDED.last_success_at, pipeline_state.last_success_at),
            last_error      = EXCLUDED.last_error,
            last_error_at   = COALESCE(EXCLUDED.last_error_at, pipeline_state.last_error_at),
            items_last_run  = COALESCE(EXCLUDED.items_last_run, pipeline_state.items_last_run)
        """,
        {"stage": stage, "source": source, "wm": watermark,
         "cursor": db.jsonb(cursor) if cursor is not None else None,
         "items": items, "error": error},
    )


# ── authors / social_items ────────────────────────────────────────────────

def upsert_author(source: str, handle: str, *, followers: int | None = None,
                  verified: bool | None = None, meta: dict | None = None) -> int:
    row = db.one(
        """
        INSERT INTO authors (source, handle, followers, verified, author_meta, last_seen)
        VALUES (%s, %s, %s, %s, %s, now())
        ON CONFLICT (source, handle) DO UPDATE SET
            followers   = COALESCE(EXCLUDED.followers, authors.followers),
            verified    = COALESCE(EXCLUDED.verified, authors.verified),
            author_meta = authors.author_meta || EXCLUDED.author_meta,
            last_seen   = now()
        RETURNING author_id
        """,
        (source, handle, followers, verified, db.jsonb(meta or {})),
    )
    return row["author_id"]


def content_hash(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode()).hexdigest()


def insert_item_if_absent(item: dict[str, Any]) -> int | None:
    """Insert-if-absent on (source, external_id) — LLD-01 D1. Returns item_id
    for genuinely new rows, None if already present."""
    row = db.one(
        """
        INSERT INTO social_items (source, source_type, external_id, parent_id, thread_id,
                                  author_id, text, lang, url, content_hash, engagement,
                                  raw, created_at)
        SELECT %(source)s, %(source_type)s, %(external_id)s, %(parent_id)s, %(thread_id)s,
               %(author_id)s, %(text)s, %(lang)s, %(url)s, %(content_hash)s,
               %(engagement)s, %(raw)s, %(created_at)s
        WHERE NOT EXISTS (SELECT 1 FROM social_items
                          WHERE source=%(source)s AND external_id=%(external_id)s)
        RETURNING item_id
        """,
        {**item, "engagement": db.jsonb(item.get("engagement") or {}),
         "raw": db.jsonb(item.get("raw") or {})},
    )
    return row["item_id"] if row else None


def update_engagement(source: str, external_id: str, engagement: dict, raw: dict) -> None:
    db.execute(
        "UPDATE social_items SET engagement=%s, raw=%s WHERE source=%s AND external_id=%s",
        (db.jsonb(engagement), db.jsonb(raw), source, external_id),
    )


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
