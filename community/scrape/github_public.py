"""GitHub public search collector for API/algo/developer signals."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Iterator

import httpx

from community.scrape.base import AuthorMeta, Engagement, SocialItem, unified_score

SEARCH_URL = "https://api.github.com/search/issues"


def _dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _headers() -> dict[str, str]:
    h = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "nubra-beacon-github-collector/1.0",
    }
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _item(row: dict, query: str) -> SocialItem | None:
    title = (row.get("title") or "").strip()
    body = (row.get("body") or "").strip()
    if not title and not body:
        return None
    user = row.get("user") or {}
    repo_url = row.get("repository_url") or ""
    repo_parts = repo_url.rsplit("/", 2)[-2:] if repo_url else []
    repo_name = "/".join(repo_parts) if repo_parts else ""
    comments = int(row.get("comments") or 0)
    reactions = row.get("reactions") or {}
    likes = int(reactions.get("+1") or 0)
    shares = int(reactions.get("heart") or 0)
    return SocialItem(
        source="github",
        source_type="issue",
        external_id=f"gh_{row.get('id')}",
        parent_id=None,
        thread_id=f"gh_{row.get('id')}",
        author=(user.get("login") or repo_name or "[unknown]"),
        author_meta=AuthorMeta(),
        text=" ".join(x for x in (title, body) if x)[:8000],
        lang=None,
        url=row.get("html_url") or "",
        created_at=_dt(row.get("created_at")),
        engagement=Engagement(
            score=unified_score(likes, shares, comments),
            native={"comments": comments, "reactions_plus_one": likes, "reactions_heart": shares},
        ),
        raw={
            "query": query,
            "repo": repo_name,
            "state": row.get("state"),
            "labels": [l.get("name") for l in row.get("labels") or [] if isinstance(l, dict)],
            "source_method": "github_search_issues",
        },
    )


def fetch(reg: dict) -> Iterator[SocialItem]:
    queries = list(reg.get("queries") or [])
    max_queries = int(reg.get("max_queries_per_run", 20))
    max_items = int(reg.get("max_items_per_query", 20))
    if not queries:
        return

    with httpx.Client(timeout=20.0, headers=_headers(), follow_redirects=True) as client:
        for query in queries[:max_queries]:
            q = f"{query} in:title,body type:issue"
            r = client.get(
                SEARCH_URL,
                params={"q": q, "sort": "updated", "order": "desc", "per_page": max_items},
            )
            if r.status_code in (403, 429):
                break
            r.raise_for_status()
            for row in (r.json().get("items") or [])[:max_items]:
                item = _item(row, query)
                if item:
                    yield item
            time.sleep(1.0)
