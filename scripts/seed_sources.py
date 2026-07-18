"""Seed watch_sources from registry.yaml (idempotent). After seeding, the DB is
the source of truth for collection sources; the registry lists remain only as
the seed + fallback when the table is empty."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from community.config.settings import settings
from community.store import db


def main() -> None:
    reg = settings.registry["sources"]
    rows: list[tuple[str, str, str | None]] = []
    subs = reg["reddit"]["subreddits"]
    if isinstance(subs, dict):
        for cat, lst in subs.items():
            rows += [("subreddit", s, cat) for s in lst]
    else:
        rows += [("subreddit", s, None) for s in subs]
    rows += [("x_query", q, None) for q in reg["twitter"].get("queries", [])]
    tw = reg["twitter"]
    for kind_key, kind in (("hashtags", "x_hashtag"), ("handles", "x_handle")):
        for cat, values in (tw.get(kind_key) or {}).items():
            rows += [(kind, v, cat) for v in values]
    n = 0
    for kind, value, cat in rows:
        n += db.execute(
            "INSERT INTO watch_sources (kind, value, category, added_by) "
            "VALUES (%s, %s, %s, 'seed') ON CONFLICT (kind, value) DO NOTHING",
            (kind, value, cat),
        )
    for kw in reg["twitter"].get("keywords", []):
        n += db.execute(
            "INSERT INTO watch_sources (kind, value, category, added_by, note, config) "
            "VALUES ('keyword', %s, 'brand', 'seed', %s, %s) "
            "ON CONFLICT (kind, value) DO NOTHING",
            (kw["value"], kw.get("note"),
             db.jsonb({"x": bool(kw.get("x", True)), "reddit": bool(kw.get("reddit", True))})),
        )
        rows.append(("keyword", kw["value"], "brand"))
    # add-on collector targets (2026-07-18): youtube/github queries, forums, apps
    for partition, qs in (reg.get("youtube", {}).get("queries") or {}).items():
        for q in qs or []:
            n += db.execute(
                "INSERT INTO watch_sources (kind, value, category, added_by) "
                "VALUES ('youtube_query', %s, %s, 'seed') ON CONFLICT (kind, value) DO NOTHING",
                (q, partition))
            rows.append(("youtube_query", q, partition))
    for q in reg.get("github", {}).get("queries") or []:
        n += db.execute(
            "INSERT INTO watch_sources (kind, value, category, added_by) "
            "VALUES ('github_query', %s, 'api', 'seed') ON CONFLICT (kind, value) DO NOTHING",
            (q,))
        rows.append(("github_query", q, "api"))
    for f in reg.get("broker_communities", {}).get("sources") or []:
        url = f.get("base_url") or f.get("sitemap_url")
        if not url:
            continue
        n += db.execute(
            "INSERT INTO watch_sources (kind, value, category, added_by, note, config) "
            "VALUES ('forum', %s, %s, 'seed', %s, %s) ON CONFLICT (kind, value) DO NOTHING",
            (url, f.get("broker"), f.get("name"), db.jsonb(f)))
        rows.append(("forum", url, f.get("broker")))
    for a in reg.get("app_reviews", {}).get("apps") or []:
        if not (a.get("apple_id") or a.get("google_package")):
            continue
        n += db.execute(
            "INSERT INTO watch_sources (kind, value, category, added_by, config) "
            "VALUES ('app', %s, %s, 'seed', %s) ON CONFLICT (kind, value) DO NOTHING",
            (a["name"], a.get("broker"), db.jsonb({k: v for k, v in a.items()
                                                   if k != "name" and v})))
        rows.append(("app", a["name"], a.get("broker")))
    print(f"seeded {n} new watch_sources ({len(rows)} candidates)")


if __name__ == "__main__":
    main()
