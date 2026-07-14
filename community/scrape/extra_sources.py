"""Optional add-on source collectors.

This module is intentionally separate from the existing Reddit/X collectors.
Every source is config-gated and failure-isolated: one new collector must never
break the core Beacon scrape stage.
"""
from __future__ import annotations

from collections.abc import Iterable

from community.clean.normalize import norm
from community.config.log import get_logger
from community.config.settings import settings
from community.scrape.base import SocialItem
from community.store import repositories as repo

log = get_logger("extra_sources")


def _store(item: SocialItem, counters: dict) -> None:
    author_id = repo.upsert_author(
        item.source,
        item.author or "[unknown]",
        followers=item.author_meta.followers,
        verified=item.author_meta.verified,
        meta=item.author_meta.model_dump(exclude_none=True, mode="json"),
    )
    item_id = repo.insert_item_if_absent({
        "source": item.source,
        "source_type": item.source_type,
        "external_id": item.external_id,
        "parent_id": item.parent_id,
        "thread_id": item.thread_id,
        "author_id": author_id,
        "text": item.text,
        "lang": item.lang,
        "url": item.url,
        "content_hash": repo.content_hash(norm(item.text)),
        "engagement": item.engagement.model_dump(mode="json"),
        "raw": item.raw,
        "created_at": item.created_at,
    })
    counters["inserted" if item_id else "skipped_existing"] += 1


def _run_source(name: str, fetcher, reg: dict) -> dict:
    if not reg.get("enabled", False):
        return {"enabled": False, "fetched": 0, "inserted": 0, "skipped_existing": 0}

    counters = {"enabled": True, "fetched": 0, "inserted": 0, "skipped_existing": 0}
    try:
        items: Iterable[SocialItem] = fetcher(reg)
        for item in items:
            counters["fetched"] += 1
            _store(item, counters)
        repo.advance_state("ingest", name, watermark=repo.now_utc(), items=counters["fetched"])
    except Exception as exc:  # noqa: BLE001 - source isolation by design
        log.exception("%s collector failed; continuing", name)
        counters["error"] = f"{type(exc).__name__}: {str(exc)[:180]}"
        try:
            repo.advance_state("ingest", name, error=counters["error"], items=counters["fetched"])
        except Exception:
            log.exception("%s state update failed", name)
    return counters


def run(**_) -> dict:
    sources = settings.registry.get("sources", {})
    out: dict[str, dict] = {}

    from community.scrape import app_reviews, broker_communities, github_public, youtube

    out["youtube"] = _run_source("youtube", youtube.fetch, sources.get("youtube", {}))
    out["github"] = _run_source("github", github_public.fetch, sources.get("github", {}))
    out["broker_communities"] = _run_source(
        "community_forum", broker_communities.fetch, sources.get("broker_communities", {})
    )
    out["app_reviews"] = _run_source("app_review", app_reviews.fetch, sources.get("app_reviews", {}))
    return out
