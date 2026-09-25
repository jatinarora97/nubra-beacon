"""GitHub public search collector for API/algo/developer signals.

GitHub search can return noisy matches when a broad phrase appears in generated
issue text. This collector therefore applies a lightweight relevance gate before
emitting items. The gate is intentionally transparent and configurable from
registry.yaml.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from typing import Iterator

import httpx

from community.scrape.base import AuthorMeta, Engagement, SocialItem, unified_score

SEARCH_URL = "https://api.github.com/search/issues"

DEFAULT_ALLOW_TERMS = [
    "trading api",
    "broker api",
    "market data",
    "websocket",
    "order placement",
    "historical data",
    "algo trading",
    "automated trading",
    "kite connect",
    "smartapi",
    "upstox api",
    "dhanhq",
    "fyers api",
    "nse",
    "bse",
    "zerodha",
    "dhan",
    "upstox",
    "angel one",
    "fyers",
    "nubra",
]

DEFAULT_DENY_TERMS = [
    "casino",
    "betting",
    "porn",
    "sex",
    "crypto airdrop",
    "nft",
    "spam",
    "wealth builder empire",
]


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


def _norm_terms(values: list[str] | None, defaults: list[str]) -> list[str]:
    terms = [str(v).strip().lower() for v in (values or []) if str(v).strip()]
    return terms or defaults


def _term_hit(term: str, haystack: str) -> bool:
    # Multi-word phrases use substring match; single words use word boundaries.
    if " " in term:
        return term in haystack
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", haystack))


def _relevance(row: dict, query: str, reg: dict) -> tuple[int, list[str], list[str]]:
    title = (row.get("title") or "").lower()
    body = (row.get("body") or "").lower()
    repo_url = (row.get("repository_url") or "").lower()
    labels = " ".join(
        str(l.get("name") or "").lower() for l in row.get("labels") or [] if isinstance(l, dict)
    )
    haystack = " ".join([query.lower(), title, body[:4000], repo_url, labels])
    allow_terms = _norm_terms((reg.get("relevance") or {}).get("allow_terms"), DEFAULT_ALLOW_TERMS)
    deny_terms = _norm_terms((reg.get("relevance") or {}).get("deny_terms"), DEFAULT_DENY_TERMS)
    allow_hits = [t for t in allow_terms if _term_hit(t, haystack)]
    deny_hits = [t for t in deny_terms if _term_hit(t, haystack)]
    score = len(allow_hits) * 2 - len(deny_hits) * 4
    # Explicit known broker/API repo names are strong signals.
    if any(x in repo_url for x in ("zerodha", "kiteconnect", "dhanhq", "upstox", "smartapi", "fyers")):
        score += 3
    return score, allow_hits, deny_hits


def _item(row: dict, query: str, reg: dict) -> SocialItem | None:
    title = (row.get("title") or "").strip()
    body = (row.get("body") or "").strip()
    if not title and not body:
        return None
    relevance_score, allow_hits, deny_hits = _relevance(row, query, reg)
    min_score = int((reg.get("relevance") or {}).get("min_score", 2))
    if relevance_score < min_score:
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
            "relevance_score": relevance_score,
            "allow_hits": allow_hits,
            "deny_hits": deny_hits,
            "source_method": "github_search_issues",
        },
    )


def _watch_queries(reg: dict) -> list[str]:
    """Source of truth = watch_sources (kind='github_query', UI-managed);
    registry is the seed/fallback."""
    try:
        from community.store import db
        rows = db.query("SELECT value FROM watch_sources "
                        "WHERE kind='github_query' AND active ORDER BY value")
        if rows:
            return [r["value"] for r in rows]
    except Exception:  # noqa: BLE001
        pass
    return list(reg.get("queries") or [])


def fetch(reg: dict) -> Iterator[SocialItem]:
    queries = _watch_queries(reg)
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
                item = _item(row, query, reg)
                if item:
                    yield item
            time.sleep(1.0)
