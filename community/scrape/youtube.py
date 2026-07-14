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
            "source_method": "youtube_data_api",
        },
    )


def _comment_item(row: dict, video_id: str, query: str, partition: str) -> SocialItem | None:
    top = ((row.get("snippet") or {}).get("topLevelComment") or {})
    sn = top.get("snippet") or {}
    cid = top.get("id") or row.get("id")
    text = (sn.get("textDisplay") or sn.get("textOriginal") or "").strip()
    if not cid or not text:
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
        raw={"query": query, "partition": partition, "source_method": "youtube_comment_threads"},
    )


def _queries(reg: dict) -> list[tuple[str, str]]:
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
    with httpx.Client(timeout=25.0) as client:
        for partition, query in _queries(reg):
            ids = _search(client, key, query, max_videos)
            for video in _video_rows(client, key, ids):
                vid = video.get("id")
                item = _video_item(video, query, partition)
                if item:
                    yield item
                if vid:
                    for comment in _comments(client, key, vid, max_comments):
                        citem = _comment_item(comment, vid, query, partition)
                        if citem:
                            yield citem
                time.sleep(0.2)
            time.sleep(0.8)
