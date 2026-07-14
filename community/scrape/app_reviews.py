"""App Store / Play Store review collector.

Apple reviews use the public RSS JSON endpoint. Google Play is intentionally a
best-effort listing snapshot for now unless review access is added later; no
browser automation is used here.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterator

import httpx

from community.scrape.base import AuthorMeta, Engagement, SocialItem, unified_score


def _dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def _apple_reviews(client: httpx.Client, app: dict, country: str, limit: int) -> Iterator[SocialItem]:
    app_id = str(app.get("apple_id") or "").strip()
    if not app_id:
        return
    url = f"https://itunes.apple.com/{country}/rss/customerreviews/page=1/id={app_id}/sortby=mostrecent/json"
    r = client.get(url)
    r.raise_for_status()
    entries = (r.json().get("feed") or {}).get("entry") or []
    if entries and "im:name" in entries[0]:  # first entry can be app metadata
        entries = entries[1:]
    for e in entries[:limit]:
        rid = ((e.get("id") or {}).get("label") or "").strip()
        text = ((e.get("content") or {}).get("label") or "").strip()
        title = ((e.get("title") or {}).get("label") or "").strip()
        if not rid or not (text or title):
            continue
        rating = int(((e.get("im:rating") or {}).get("label") or 0) or 0)
        author = (((e.get("author") or {}).get("name") or {}).get("label") or "[unknown]")
        yield SocialItem(
            source="app_review",
            source_type="review",
            external_id=f"apple_{app_id}_{rid}",
            parent_id=None,
            thread_id=f"apple_{app_id}_{rid}",
            author=author,
            author_meta=AuthorMeta(),
            text=" ".join(x for x in (title, text) if x)[:8000],
            lang=None,
            url=((e.get("link") or {}).get("attributes") or {}).get("href") or url,
            created_at=_dt(((e.get("updated") or {}).get("label"))),
            engagement=Engagement(score=unified_score(rating, 0, 0), native={"rating": rating}),
            raw={
                "store": "apple_app_store",
                "app_name": app.get("name"),
                "broker": app.get("broker"),
                "app_id": app_id,
                "source_method": "apple_reviews_rss",
            },
        )


def _google_listing_snapshot(client: httpx.Client, app: dict, country: str) -> Iterator[SocialItem]:
    package = str(app.get("google_package") or "").strip()
    if not package:
        return
    url = f"https://play.google.com/store/apps/details?id={package}&hl=en_IN&gl={country.upper()}"
    r = client.get(url)
    if r.status_code >= 400:
        return
    title = app.get("name") or package
    desc = ""
    m = re.search(r'<meta name="description" content="([^"]+)"', r.text)
    if m:
        desc = m.group(1)
    text = f"{title} Google Play listing. {desc}".strip()
    yield SocialItem(
        source="app_review",
        source_type="review",
        external_id=f"gplay_listing_{package}",
        parent_id=None,
        thread_id=f"gplay_listing_{package}",
        author="Google Play",
        author_meta=AuthorMeta(),
        text=text[:8000],
        lang=None,
        url=url,
        created_at=datetime.now(timezone.utc),
        engagement=Engagement(score=0, native={}),
        raw={
            "store": "google_play",
            "app_name": app.get("name"),
            "broker": app.get("broker"),
            "package": package,
            "source_method": "google_play_listing_snapshot",
            "note": "listing snapshot only; full Google Play review extraction not enabled",
        },
    )


def fetch(reg: dict) -> Iterator[SocialItem]:
    apps = list(reg.get("apps") or [])
    country = str(reg.get("country") or "in").lower()
    limit = int(reg.get("max_reviews_per_app", 100))
    if not apps:
        return
    with httpx.Client(
        timeout=25.0,
        follow_redirects=True,
        headers={"User-Agent": "nubra-beacon-app-review-collector/1.0"},
    ) as client:
        for app in apps:
            yield from _apple_reviews(client, app, country, limit)
            yield from _google_listing_snapshot(client, app, country)
