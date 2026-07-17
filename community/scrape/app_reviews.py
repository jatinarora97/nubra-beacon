"""Public App Store and Google Play review collector."""
from __future__ import annotations

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


def _aware(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _google_reviews(app: dict, country: str, limit: int) -> Iterator[SocialItem]:
    package = str(app.get("google_package") or "").strip()
    if not package:
        return
    # Imported lazily so a dependency or endpoint failure remains contained by
    # the add-on source boundary and cannot stop Reddit/X collection.
    from google_play_scraper import Sort, reviews

    rows, _ = reviews(
        package,
        lang="en",
        country=country,
        sort=Sort.NEWEST,
        count=min(max(limit, 1), 200),
        filter_score_with=None,
    )
    for row in rows[:limit]:
        review_id = str(row.get("reviewId") or "").strip()
        text = str(row.get("content") or "").strip()
        if not review_id or not text:
            continue
        rating = int(row.get("score") or 0)
        likes = int(row.get("thumbsUpCount") or 0)
        url = (
            "https://play.google.com/store/apps/details"
            f"?id={package}&reviewId={review_id}&hl=en_IN&gl={country.upper()}"
        )
        yield SocialItem(
            source="app_review",
            source_type="review",
            external_id=f"gplay_{package}_{review_id}",
            parent_id=None,
            thread_id=f"gplay_{package}_{review_id}",
            author=str(row.get("userName") or "[unknown]"),
            author_meta=AuthorMeta(),
            text=text[:8000],
            lang="en",
            url=url,
            created_at=_aware(row.get("at")),
            engagement=Engagement(
                score=unified_score(likes, 0, 0),
                native={"rating": rating, "likes": likes},
            ),
            raw={
                "store": "google_play",
                "app_name": app.get("name"),
                "broker": app.get("broker"),
                "package": package,
                "app_version": row.get("reviewCreatedVersion"),
                "developer_reply": row.get("replyContent"),
                "developer_reply_at": (
                    _aware(row.get("repliedAt")).isoformat()
                    if row.get("repliedAt")
                    else None
                ),
                "source_method": "google_play_public_reviews",
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
            yield from _google_reviews(app, country, limit)
