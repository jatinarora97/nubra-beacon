"""Public broker/community forum collector."""
from __future__ import annotations

import hashlib
import html
import re
import time
from datetime import datetime, timezone
from typing import Iterator
from urllib.parse import urljoin

import httpx

from community.scrape.base import AuthorMeta, Engagement, SocialItem, unified_score

_TAG_RE = re.compile(r"<[^>]+>")


def _clean_html(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", value)).strip()


def _dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def _row(
    source_cfg: dict,
    *,
    external_id: str,
    source_type: str,
    thread_id: str,
    parent_id: str | None,
    author: str,
    text: str,
    url: str,
    created_at: datetime,
    likes: int = 0,
    replies: int = 0,
    views: int = 0,
    raw: dict | None = None,
) -> SocialItem | None:
    if not external_id or not text:
        return None
    return SocialItem(
        source="community_forum",
        source_type=source_type,  # type: ignore[arg-type]
        external_id=f"{source_cfg.get('broker')}_{external_id}",
        parent_id=parent_id,
        thread_id=f"{source_cfg.get('broker')}_{thread_id}",
        author=author or "[unknown]",
        author_meta=AuthorMeta(),
        text=text[:8000],
        lang=None,
        url=url,
        created_at=created_at,
        engagement=Engagement(
            score=unified_score(likes, 0, replies),
            native={"likes": likes, "replies": replies, "views": views},
        ),
        raw={
            "broker": source_cfg.get("broker"),
            "community_name": source_cfg.get("name"),
            "platform": source_cfg.get("platform"),
            "source_method": f"community_{source_cfg.get('platform')}",
            **(raw or {}),
        },
    )


def _discourse(client: httpx.Client, source_cfg: dict, topic_cap: int, reply_cap: int) -> Iterator[SocialItem]:
    base = str(source_cfg.get("base_url") or "").rstrip("/")
    if not base:
        return
    r = client.get(f"{base}/latest.json")
    r.raise_for_status()
    topics = ((r.json().get("topic_list") or {}).get("topics") or [])[:topic_cap]
    for t in topics:
        tid = str(t.get("id"))
        slug = t.get("slug") or "topic"
        topic_url = f"{base}/t/{slug}/{tid}"
        title = t.get("title") or ""
        excerpt = _clean_html(t.get("excerpt"))
        item = _row(
            source_cfg,
            external_id=f"topic_{tid}",
            source_type="post",
            thread_id=f"topic_{tid}",
            parent_id=None,
            author=str(t.get("last_poster_username") or "[unknown]"),
            text=" ".join(x for x in (title, excerpt) if x),
            url=topic_url,
            created_at=_dt(t.get("created_at")),
            likes=int(t.get("like_count") or 0),
            replies=int(t.get("posts_count") or 0),
            views=int(t.get("views") or 0),
            raw={"category_id": t.get("category_id"), "tags": t.get("tags") or []},
        )
        if item:
            yield item
        if reply_cap <= 0:
            continue
        try:
            tr = client.get(f"{base}/t/{tid}.json")
            tr.raise_for_status()
            posts = ((tr.json().get("post_stream") or {}).get("posts") or [])[1:reply_cap + 1]
            for p in posts:
                body = _clean_html(p.get("cooked"))
                citem = _row(
                    source_cfg,
                    external_id=f"post_{p.get('id')}",
                    source_type="comment",
                    thread_id=f"topic_{tid}",
                    parent_id=f"{source_cfg.get('broker')}_topic_{tid}",
                    author=str(p.get("username") or "[unknown]"),
                    text=body,
                    url=f"{topic_url}/{p.get('post_number') or ''}",
                    created_at=_dt(p.get("created_at")),
                    likes=int(p.get("like_count") or 0),
                    raw={"post_number": p.get("post_number")},
                )
                if citem:
                    yield citem
        except Exception:
            pass
        time.sleep(0.4)


def _nodebb(client: httpx.Client, source_cfg: dict, topic_cap: int, _: int) -> Iterator[SocialItem]:
    base = str(source_cfg.get("base_url") or "").rstrip("/")
    if not base:
        return
    r = client.get(f"{base}/api/recent")
    r.raise_for_status()
    topics = (r.json().get("topics") or r.json().get("posts") or [])[:topic_cap]
    for t in topics:
        tid = str(t.get("tid") or t.get("topic", {}).get("tid") or t.get("pid"))
        title = t.get("title") or t.get("topic", {}).get("title") or ""
        content = _clean_html(t.get("content"))
        url = urljoin(base + "/", f"topic/{tid}")
        item = _row(
            source_cfg,
            external_id=f"topic_{tid}",
            source_type="post",
            thread_id=f"topic_{tid}",
            parent_id=None,
            author=str((t.get("user") or {}).get("username") or "[unknown]"),
            text=" ".join(x for x in (title, content) if x),
            url=url,
            created_at=_dt(t.get("timestampISO") or t.get("teaser", {}).get("timestampISO")),
            likes=int(t.get("votes") or 0),
            replies=int(t.get("postcount") or 0),
            views=int(t.get("viewcount") or 0),
        )
        if item:
            yield item


def _sitemap_html(client: httpx.Client, source_cfg: dict, topic_cap: int, _: int) -> Iterator[SocialItem]:
    sitemap = source_cfg.get("sitemap_url")
    if not sitemap:
        return
    r = client.get(str(sitemap))
    r.raise_for_status()
    urls = re.findall(r"<loc>(.*?)</loc>", r.text, flags=re.I)[:topic_cap]
    for url in urls:
        try:
            page = client.get(url)
            page.raise_for_status()
        except Exception:
            continue
        stable = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        title_match = re.search(r"<title[^>]*>(.*?)</title>", page.text, flags=re.I | re.S)
        desc_match = re.search(
            r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\'](.*?)["\']',
            page.text,
            flags=re.I | re.S,
        )
        title = _clean_html(html.unescape(title_match.group(1))) if title_match else ""
        desc = _clean_html(html.unescape(desc_match.group(1))) if desc_match else ""
        text = " ".join(x for x in (title, desc) if x).strip()
        if not text:
            continue
        item = _row(
            source_cfg,
            external_id=f"url_{stable}",
            source_type="post",
            thread_id=f"url_{stable}",
            parent_id=None,
            author=str(source_cfg.get("name") or "[unknown]"),
            text=text,
            url=url,
            created_at=datetime.now(timezone.utc),
            raw={"sitemap_url": sitemap, "page_type": "public_broker_content"},
        )
        if item:
            yield item
        time.sleep(0.2)


def fetch(reg: dict) -> Iterator[SocialItem]:
    topic_cap = int(reg.get("max_topics_per_source", 20))
    reply_cap = int(reg.get("max_replies_per_topic", 10))
    sources = list(reg.get("sources") or [])
    handlers = {"discourse": _discourse, "nodebb": _nodebb, "sitemap_html": _sitemap_html}
    with httpx.Client(
        timeout=25.0,
        follow_redirects=True,
        headers={"User-Agent": "nubra-beacon-community-collector/1.0"},
    ) as client:
        for source_cfg in sources:
            handler = handlers.get(str(source_cfg.get("platform")))
            if not handler:
                continue
            try:
                yield from handler(client, source_cfg, topic_cap, reply_cap)
            except Exception:
                continue
            time.sleep(0.8)
