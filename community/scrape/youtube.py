"""YouTube Data API collector.

Text-only by design: video metadata and comments. No thumbnails or media files.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Iterator

import httpx

from community.scrape.base import AuthorMeta, Engagement, SocialItem, unified_score

API = "https://www.googleapis.com/youtube/v3"


def _dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _int(value) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _engagement_rate(likes: int, comments: int, views: int) -> float:
    if views <= 0:
        return 0.0
    return round((likes + comments) / views, 6)


def _search(client: httpx.Client, key: str, query: str, max_results: int) -> list[str]:
    r = client.get(
        f"{API}/search",
        params={
            "key": key,
            "part": "snippet",
            "type": "video",
            "q": query,
            "maxResults": max_results,
            "order": "date",
            "relevanceLanguage": "en",
            "regionCode": "IN",
        },
    )
    r.raise_for_status()
    return [
        it.get("id", {}).get("videoId")
        for it in r.json().get("items") or []
        if it.get("id", {}).get("videoId")
    ]


def _video_rows(client: httpx.Client, key: str, ids: list[str]) -> list[dict]:
    if not ids:
        return []
    r = client.get(
        f"{API}/videos",
        params={"key": key, "part": "snippet,statistics", "id": ",".join(ids), "maxResults": len(ids)},
    )
    r.raise_for_status()
    return r.json().get("items") or []


def _comments(client: httpx.Client, key: str, video_id: str, limit: int) -> list[dict]:
    if limit <= 0:
        return []
    r = client.get(
        f"{API}/commentThreads",
        params={
            "key": key,
            "part": "snippet",
            "videoId": video_id,
            "maxResults": min(limit, 100),
            "order": "relevance",
            "textFormat": "plainText",
        },
    )
    if r.status_code in (403, 404):
        return []
    r.raise_for_status()
    return r.json().get("items") or []


def _video_item(row: dict, query: str, partition: str) -> SocialItem | None:
    vid = row.get("id")
    sn = row.get("snippet") or {}
    st = row.get("statistics") or {}
    title = (sn.get("title") or "").strip()
    desc = (sn.get("description") or "").strip()
    if not vid or not title:
        return None
    views = _int(st.get("viewCount"))
    likes = _int(st.get("likeCount"))
    comments = _int(st.get("commentCount"))
    return SocialItem(
        source="youtube",
        source_type="post",
        external_id=f"yt_video_{vid}",
        parent_id=None,
        thread_id=f"yt_video_{vid}",
        author=sn.get("channelTitle") or "[unknown]",
        author_meta=AuthorMeta(),
        text=" ".join(x for x in (title, desc) if x)[:8000],
        lang=None,
        url=f"https://www.youtube.com/watch?v={vid}",
        created_at=_dt(sn.get("publishedAt")),
        engagement=Engagement(
            score=unified_score(likes, 0, comments),
            native={"views": views, "likes": likes, "comments": comments},
        ),
        raw={
            "query": query,
            "partition": partition,
            "channel_id": sn.get("channelId"),
            "published_at": sn.get("publishedAt"),
            "engagement_rate": _engagement_rate(likes, comments, views),
            "source_method": "youtube_data_api",
        },
    )


def _comment_item(row: dict, video_id: str, query: str, partition: str, reg: dict) -> SocialItem | None:
    top = ((row.get("snippet") or {}).get("topLevelComment") or {})
    sn = top.get("snippet") or {}
    cid = top.get("id") or row.get("id")
    text = (sn.get("textDisplay") or sn.get("textOriginal") or "").strip()
    if not cid or not text:
        return None
    quality = reg.get("comment_quality") or {}
    min_chars = int(quality.get("min_chars", 8))
    deny_terms = [str(x).lower() for x in quality.get("deny_terms", [])]
    low = text.lower()
    if len(text) < min_chars:
        return None
    if any(term and term in low for term in deny_terms):
        return None
    likes = _int(sn.get("likeCount"))
    return SocialItem(
        source="youtube",
        source_type="comment",
        external_id=f"yt_comment_{cid}",
        parent_id=f"yt_video_{video_id}",
        thread_id=f"yt_video_{video_id}",
        author=sn.get("authorDisplayName") or "[unknown]",
        author_meta=AuthorMeta(),
        text=text[:8000],
        lang=None,
        url=f"https://www.youtube.com/watch?v={video_id}&lc={cid}",
        created_at=_dt(sn.get("publishedAt")),
        engagement=Engagement(score=unified_score(likes, 0, 0), native={"likes": likes}),
        raw={
            "query": query,
            "partition": partition,
            "video_id": video_id,
            "source_method": "youtube_comment_threads",
        },
    )


def _queries(reg: dict) -> list[tuple[str, str]]:
    """(partition, query) pairs. Source of truth = watch_sources
    (kind='youtube_query', UI-managed; category 'api_algo' maps to the api
    partition, anything else to retail). Registry is the seed/fallback."""
    try:
        from community.store import db
        rows = db.query("SELECT value, category FROM watch_sources "
                        "WHERE kind='youtube_query' AND active "
                        # daily-rotating deterministic order: with more queries
                        # than max_queries_per_run, every query gets coverage
                        # across days instead of the same alphabetical head
                        "ORDER BY md5(value || current_date::text)")
        if rows:
            out = [("api_algo" if (r["category"] or "") == "api_algo" else "retail",
                    r["value"]) for r in rows]
            return out[: int(reg.get("max_queries_per_run", 20))]
    except Exception:  # noqa: BLE001 — DB hiccup: fall through to registry
        pass
    raw = reg.get("queries") or {}
    out: list[tuple[str, str]] = []
    if isinstance(raw, dict):
        for partition, qs in raw.items():
            for q in qs or []:
                out.append((str(partition), str(q)))
    else:
        out = [("general", str(q)) for q in raw]
    return out[: int(reg.get("max_queries_per_run", 20))]


def fetch(reg: dict) -> Iterator[SocialItem]:
    key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not key:
        return
    max_videos = int(reg.get("max_videos_per_query", 5))
    max_comments = int(reg.get("max_comments_per_video", 20))
    from community.config.log import get_logger
    log = get_logger("scrape.youtube")
    errors = 0
    with httpx.Client(timeout=25.0) as client:
        for partition, query in _queries(reg):
            # Per-query isolation (2026-07-18 live incident: one connection
            # reset aborted the remaining queries) — mirror twitter.py.
            try:
                ids = _search(client, key, query, max_videos)
                rows = _video_rows(client, key, ids)
            except Exception as e:  # noqa: BLE001
                errors += 1
                log.warning("query %r failed (%s: %s) — continuing with next query",
                            query, type(e).__name__, str(e)[:120])
                continue
            for video in rows:
                vid = video.get("id")
                item = _video_item(video, query, partition)
                if item:
                    yield item
                if vid:
                    try:
                        comment_rows = _comments(client, key, vid, max_comments)
                    except Exception as e:  # noqa: BLE001
                        errors += 1
                        log.warning("comments for video %s failed (%s) — skipping",
                                    vid, type(e).__name__)
                        comment_rows = []
                    for comment in comment_rows:
                        citem = _comment_item(comment, vid, query, partition, reg)
                        if citem:
                            yield citem
                time.sleep(0.2)
            time.sleep(0.8)
    if errors:
        log.warning("youtube run finished with %d isolated fetch errors", errors)
