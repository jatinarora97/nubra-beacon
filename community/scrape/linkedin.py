"""LinkedIn public-post collector (Apify harvestapi/linkedin-post-search).

No-cookie actor: keyword search over PUBLIC posts — no Nubra LinkedIn account
or session involved, same APIFY_TOKEN as the Instagram collector. Text-only.
Cost ~USD 2 per 1k posts (verified 2026-09-09: 32 items = $0.064); daily
cadence + per-query caps keep it pennies. Queries are DB-managed
(watch_sources kind='linkedin_query', Sources page) with the registry list
as seed/fallback — same contract as every other collector.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Iterator

import httpx

from community.config.log import get_logger
from community.scrape.base import AuthorMeta, Engagement, SocialItem, unified_score
from community.store import db

log = get_logger("scrape.linkedin")

APIFY = "https://api.apify.com/v2"
ACTOR = "harvestapi~linkedin-post-search"


def _queries(reg: dict) -> list[str]:
    try:
        rows = db.query("SELECT value FROM watch_sources "
                        "WHERE kind='linkedin_query' AND active ORDER BY value")
        if rows:
            return [r["value"] for r in rows]
    except Exception:  # noqa: BLE001 — registry fallback by design
        pass
    return list(reg.get("queries") or [])


def _run_actor(payload: dict, timeout_s: int = 300) -> list[dict]:
    headers = {"Authorization": f"Bearer {os.getenv('APIFY_TOKEN', '').strip()}"}
    with httpx.Client(timeout=60, headers=headers) as c:
        r = c.post(f"{APIFY}/acts/{ACTOR}/runs",
                   params={"timeout": timeout_s, "memory": 512}, json=payload)
        r.raise_for_status()
        data = r.json()["data"]
        run_id, dataset_id = data["id"], data["defaultDatasetId"]
        deadline = time.monotonic() + timeout_s + 60
        st = data
        while time.monotonic() < deadline:
            time.sleep(10)
            st = c.get(f"{APIFY}/actor-runs/{run_id}").json()["data"]
            if st["status"] not in ("READY", "RUNNING"):
                break
        if st["status"] != "SUCCEEDED":
            raise RuntimeError(f"apify {ACTOR} run {run_id}: {st['status']}")
        log.info("linkedin actor run cost: $%s", st.get("usageTotalUsd"))
        items = c.get(f"{APIFY}/datasets/{dataset_id}/items",
                      params={"clean": "true"}).json()
        return items if isinstance(items, list) else []


def fetch(reg: dict) -> Iterator[SocialItem]:
    if not os.getenv("APIFY_TOKEN", "").strip():
        log.warning("APIFY_TOKEN not set — linkedin collector skipped")
        return
    queries = _queries(reg)
    if not queries:
        return
    # one actor run for ALL queries (the actor accepts a list) — one startup fee
    max_items = int(reg.get("max_posts_per_query", 25)) * len(queries)
    items = _run_actor({
        "searchQueries": queries,
        "maxItems": max_items,
        "postedLimit": str(reg.get("posted_limit", "week")),
        "sortBy": "date",
    })
    for it in items:
        post_id = str(it.get("id") or "").strip()
        text = (it.get("content") or "").strip()
        if not post_id or not text:
            continue
        author = it.get("author") or {}
        handle = (author.get("publicIdentifier") or author.get("universalName")
                  or author.get("name") or "[unknown]")
        eng = it.get("engagement") or {}
        likes = int(eng.get("likes") or 0)
        comments = int(eng.get("comments") or 0)
        shares = int(eng.get("shares") or 0)
        posted = (it.get("postedAt") or {}).get("date")
        try:
            created = datetime.fromisoformat(str(posted).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            created = datetime.now(timezone.utc)
        yield SocialItem(
            source="linkedin", source_type="post",
            external_id=post_id, parent_id=None, thread_id=post_id,
            author=str(handle)[:200], author_meta=AuthorMeta(),
            text=text[:8000], lang=None,
            url=it.get("linkedinUrl") or it.get("shareLinkedinUrl"),
            engagement=Engagement(
                score=unified_score(likes=likes, shares=shares, replies=comments),
                native={"likes": likes, "comments": comments, "shares": shares},
            ),
            raw={"query": (it.get("query") or {}).get("search")
                 if isinstance(it.get("query"), dict) else it.get("query"),
                 "post_type": it.get("type"), "via": "apify_harvestapi"},
            created_at=created,
        )
