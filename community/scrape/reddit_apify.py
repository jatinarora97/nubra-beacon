"""Reddit collector via Apify (actor trudax/reddit-scraper-lite).

Replaces the vendored zanshash/Playwright transport, which stopped working when old.reddit began
requiring a login (user decision 2026-10-09). Same contract as every other Apify collector
(linkedin.py, instagram.py): config-gated by `sources.reddit_apify.enabled` (OFF by default),
DB-managed subreddits and keywords (watch_sources, Sources page) with the registry as seed, run
through extra_sources so a failure is recorded and never breaks the scrape stage.

One actor run covers every watched subreddit plus the active keyword searches. The actor does not
say which search a hit came from, so posts from subreddits that are NOT watched (search hits) must
pass the old market-term filter (keyword_search._MARKET_RE) — "Nubra Valley" travel posts stay out.
The actor input only uses fields from the input the Apify console accepted on 2026-10-09; the date
limits (postDateLimit / time) are deliberately not sent (that input was rejected).

Items are stored as source='reddit' with the same t3_<id> post ids the old scraper used, so they
dedupe against existing rows (insert-if-absent). Comments use their real t1_<id> ids and carry
parent links (depth / parentId), which the old DOM scraper could not provide.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from typing import Iterator

import httpx

from community.config.log import get_logger
from community.config.settings import settings
from community.scrape.base import AuthorMeta, Engagement, SocialItem, unified_score
from community.scrape.keyword_search import _MARKET_RE, _active_keywords
from community.store import db

log = get_logger("scrape.reddit_apify")

APIFY = "https://api.apify.com/v2"
DEFAULT_ACTOR = "trudax~reddit-scraper-lite"
_READ_MORE = re.compile(r"\s*Read more\s*$")
_URL_POST_ID = re.compile(r"/comments/([a-z0-9]+)/", re.I)
_URL_COMMENT_ID = re.compile(r"/comment/([a-z0-9]+)/", re.I)

run_costs_usd: float = 0.0   # per-process accumulator (surfaced by the probe script)
run_log: list[dict] = []     # one entry per actor run: id, status, items, cost, seconds, partial


def _token() -> str:
    return os.getenv("APIFY_TOKEN", "").strip()


def _actor(reg: dict) -> str:
    return str(reg.get("actor") or DEFAULT_ACTOR).replace("/", "~")


def _run_actor(actor: str, payload: dict, *, timeout_s: int = 900, memory_mb: int = 1024) -> list[dict]:
    """Start the actor, poll until it finishes, return the dataset items.

    A run that ends TIMED-OUT / FAILED / ABORTED still holds the results it collected (and was
    paid for): those are returned and the run is logged as partial. Only a run that ends badly
    with NOTHING raises."""
    global run_costs_usd
    started = time.monotonic()
    headers = {"Authorization": f"Bearer {_token()}"}
    with httpx.Client(timeout=60, headers=headers) as c:
        r = c.post(f"{APIFY}/acts/{actor}/runs",
                   params={"timeout": timeout_s, "memory": memory_mb}, json=payload)
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
        status = st["status"]
        if status in ("READY", "RUNNING"):          # still going past our own deadline: stop paying
            try:
                c.post(f"{APIFY}/actor-runs/{run_id}/abort")
            except Exception:  # noqa: BLE001 — best effort
                pass
        cost = float(st.get("usageTotalUsd") or 0.0)
        run_costs_usd += cost
        items = c.get(f"{APIFY}/datasets/{dataset_id}/items", params={"clean": "true"}).json()
        items = items if isinstance(items, list) else []
    run_log.append({"run_id": run_id, "status": status, "items": len(items), "cost_usd": cost,
                    "partial": status != "SUCCEEDED" and bool(items),
                    "seconds": round(time.monotonic() - started, 1)})
    log.info("reddit actor run %s: %s, %d items, cost $%.4f", run_id, status, len(items), cost)
    if status != "SUCCEEDED":
        if not items:
            raise RuntimeError(f"apify {actor} run {run_id}: {status}")
        log.warning("reddit actor run %s ended %s: keeping its %d partial items", run_id, status, len(items))
    return items


def _split(items: list, n: int) -> list[list]:
    """n contiguous slices of near-equal size (some may be empty when n > len(items))."""
    base, extra = divmod(len(items), n)
    out, i = [], 0
    for k in range(n):
        size = base + (1 if k < extra else 0)
        out.append(items[i:i + size])
        i += size
    return out


def plan_runs(reg: dict, subs: list[str], queries: list[str]) -> list[tuple[list[str], list[str]]]:
    """The actor runs one collection pass is split into: balanced (subreddits, searches) slices,
    each run carrying a few of both. Shared by collect() and the probe script."""
    per_subs = max(1, int(reg.get("subs_per_run", 5)))
    per_queries = max(1, int(reg.get("queries_per_run", 4)))
    n_runs = max(-(-len(subs) // per_subs) if subs else 0,
                 -(-len(queries) // per_queries) if queries else 0, 1)
    return list(zip(_split(subs, n_runs), _split(queries, n_runs)))


def _subreddits(reg: dict) -> dict[str, str]:
    """{sub: category}. DB-first (watch_sources, managed on the Sources page); the registry's
    `sources.reddit.subreddits` is the seed/fallback — same contract as the old collector."""
    try:
        rows = db.query("SELECT value, category FROM watch_sources "
                        "WHERE kind='subreddit' AND active ORDER BY value")
        if rows:
            return {r["value"]: (r["category"] or "custom") for r in rows}
    except Exception:  # noqa: BLE001 — DB hiccup: fall back to the registry seed
        pass
    seed = (settings.registry.get("sources", {}).get("reddit", {}) or {}).get("subreddits") or {}
    if isinstance(seed, list):
        return {s: "uncategorized" for s in seed}
    return {sub: cat for cat, lst in seed.items() for sub in lst}


def build_payload(reg: dict, subs: list[str], queries: list[str]) -> dict:
    posts = int(reg.get("max_posts_per_sub", 10))
    comments = int(reg.get("comments_per_post", 5))
    skip_community = bool(reg.get("skip_community", False))
    per_post = 1 + comments
    wanted = len(subs) * ((0 if skip_community else 1) + posts * per_post) + len(queries) * posts * per_post
    payload = {
        "startUrls": [{"url": f"https://www.reddit.com/r/{s}/"} for s in subs],
        "searches": list(queries),
        "searchPosts": True, "searchComments": False, "searchCommunities": False,
        "searchMedia": False, "searchUsers": False,
        "sort": str(reg.get("sort", "new")),
        "maxPostCount": posts,
        "maxComments": comments,
        "maxItems": min(wanted, int(reg.get("max_items_per_run", 1500))),
        "maxCommunitiesCount": 5, "maxUserCount": 2,
        "skipComments": False, "skipCommunity": skip_community, "skipUserPosts": False,
        "includeNSFW": False, "includeMediaLinks": bool(reg.get("include_media_links", True)),
        "ignoreStartUrls": False, "debugMode": False,
        "navigationTimeout": 60, "scrollTimeout": 40,
        "proxy": {"useApifyProxy": True,
                  "apifyProxyGroups": list(reg.get("proxy_groups") or ["RESIDENTIAL"])},
    }
    # the time window only means something for `top`; it is sent only when configured (the console
    # rejected an input that carried it, so it stays opt-in until verified)
    if payload["sort"] == "top" and reg.get("top_time"):
        payload["time"] = str(reg["top_time"])
    return payload


# ── mapping ───────────────────────────────────────────────────────────────

def _ts(value) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def _sub_name(row: dict) -> str:
    return str(row.get("parsedCommunityName") or str(row.get("communityName") or "").removeprefix("r/")).strip()


def _post_id(row: dict) -> str | None:
    """Post id in the t3_<id> form the old scraper stored: id, else parsedId, else the URL."""
    raw_id = str(row.get("id") or "")
    if raw_id.startswith("t3_"):
        return raw_id
    if row.get("parsedId"):
        return f"t3_{row['parsedId']}"
    m = _URL_POST_ID.search(str(row.get("url") or ""))
    return f"t3_{m.group(1)}" if m else None


def _comment_id(row: dict) -> str | None:
    raw_id = str(row.get("id") or "")
    if raw_id.startswith("t1_"):
        return raw_id
    if row.get("parsedId"):
        return f"t1_{row['parsedId']}"
    m = _URL_COMMENT_ID.search(str(row.get("url") or ""))
    return f"t1_{m.group(1)}" if m else None


def _reddit_url(row: dict) -> str:
    url = row.get("url") or row.get("link")
    if url:
        return str(url)
    permalink = str(row.get("permalink") or "")
    return f"https://www.reddit.com{permalink}" if permalink else "https://www.reddit.com/"


def post_item(row: dict, category: str) -> SocialItem:
    pid = _post_id(row)
    if not pid:
        raise ValueError("reddit post row has no usable id")
    title = str(row.get("title") or "").strip()
    body = _READ_MORE.sub("", str(row.get("body") or "")).strip()
    text = " ".join(x for x in (title, body) if x)[:8000]
    likes = int(row.get("upVotes") or 0)
    n_comments = int(row.get("numberOfComments") or 0)
    return SocialItem(
        source="reddit", source_type="post",
        external_id=pid, parent_id=None, thread_id=pid,
        author=str(row.get("username") or "[unknown]"), author_meta=AuthorMeta(),
        text=text, lang=None, url=_reddit_url(row),
        created_at=_ts(row.get("createdAt")),
        engagement=Engagement(score=unified_score(likes, 0, n_comments),
                              native={"upvotes": likes, "comments": n_comments}),
        raw={"subreddit": _sub_name(row), "category": category, "via": "apify_reddit_lite",
             "upvote_ratio": row.get("upVoteRatio"), "post_type": row.get("contentType"),
             "image_urls": list(row.get("imageUrls") or [])[:10]},
    )


def comment_item(row: dict, category: str) -> SocialItem:
    cid = _comment_id(row)
    if not cid:
        raise ValueError("reddit comment row has no usable id")
    post_id = str(row.get("postId") or "") or None
    depth = int(row.get("depth") or 0)
    likes = int(row.get("upVotes") or 0)
    return SocialItem(
        source="reddit", source_type="comment",
        external_id=cid,
        parent_id=row.get("parentId") or post_id,   # replies hang off their parent comment
        thread_id=post_id or cid,
        author=str(row.get("username") or "[unknown]"), author_meta=AuthorMeta(),
        text=str(row.get("body") or "").strip()[:8000], lang=None, url=_reddit_url(row),
        created_at=_ts(row.get("createdAt")),
        engagement=Engagement(score=unified_score(likes, 0, 0), native={"upvotes": likes}),
        raw={"subreddit": _sub_name(row), "category": category, "via": "apify_reddit_lite",
             "depth": depth, "nested_reply": depth > 0},
    )


def _keep_search_post(text: str, keywords: list[tuple]) -> bool:
    """Posts from subreddits we do not watch are search hits: they must mention a market term,
    unless a keyword that opted out of the gate (skip_context_gate) appears in the text."""
    if _MARKET_RE.search(text):
        return True
    low = text.lower()
    return any(skip and value.lower() in low for value, _query, skip in keywords)


# ── collection ────────────────────────────────────────────────────────────

def _skip(stats: dict, reason: str) -> None:
    stats["skipped"][reason] = stats["skipped"].get(reason, 0) + 1


def collect(reg: dict, *, only_subs: list[str] | None = None, with_keywords: bool = False,
            sorts: list[str] | None = None, since: datetime | None = None,
            max_posts: int | None = None, comments: int | None = None) -> tuple[list[SocialItem], dict]:
    """Run the actor and map its rows. Returns (items, stats); stats["skipped"] counts why rows
    were dropped. only_subs restricts the run to those subreddits (and drops the keyword
    searches unless with_keywords); since drops posts older than that moment (client-side).
    One actor run per sort (the old collector ran `new` every time plus top/hot/rising daily);
    a sort the actor rejects is recorded in stats["errors"] and the others still count — only if
    EVERY sort fails does this raise, so extra_sources records the failure."""
    stats: dict = {"rows": 0, "posts": 0, "comments": 0, "skipped": {}, "by_sort": {}, "errors": {},
                   "runs": []}
    if not _token():
        log.warning("APIFY_TOKEN not set — reddit collector skipped")
        return [], stats
    reg = {**reg}
    if max_posts is not None:
        reg["max_posts_per_sub"] = max_posts
    if comments is not None:
        reg["comments_per_post"] = comments

    cats = {s: "backfill" for s in only_subs} if only_subs else _subreddits(reg)
    keywords: list[tuple] = _active_keywords() if (not only_subs or with_keywords) else []
    queries = [q for _kw, q, _skip_gate in keywords]
    if not cats and not queries:
        return [], stats

    sort_list = list(sorts or reg.get("sorts") or [str(reg.get("sort", "new"))])
    # One giant run (20 subreddits + 16 searches) timed out at 15 min on 2026-10-09: split the work
    # into balanced runs, each carrying a few subreddits AND a few searches (the input shape the
    # console accepted).
    plan = plan_runs(reg, list(cats), queries)
    n_runs = len(plan)
    log_start = len(run_log)
    rows: list[dict] = []
    for sort in sort_list:
        for k, (chunk_subs, chunk_queries) in enumerate(plan, 1):
            label = sort if n_runs == 1 else f"{sort}: run {k}/{n_runs}"
            before = len(run_log)
            try:
                got = _run_actor(_actor(reg), build_payload({**reg, "sort": sort}, chunk_subs, chunk_queries),
                                 timeout_s=int(reg.get("timeout_s", 900)),
                                 memory_mb=int(reg.get("memory_mb", 1024)))
            except Exception as e:  # noqa: BLE001 — one failed run must not lose the others
                stats["errors"][label] = f"{type(e).__name__}: {str(e)[:200]}"
                log.warning("reddit apify [%s] failed: %s", label, stats["errors"][label])
                got = None
            if len(run_log) > before:
                run_log[-1]["label"] = label
            if got is None:
                continue
            log.info("reddit apify [%s]: %d rows", label, len(got))
            stats["by_sort"][sort] = stats["by_sort"].get(sort, 0) + len(got)
            rows.extend(got)
    stats["runs"] = run_log[log_start:]
    if not stats["by_sort"]:
        raise RuntimeError("reddit apify: every run failed: " + "; ".join(stats["errors"].values()))
    stats["rows"] = len(rows)
    cat_by_sub = {s.lower(): c for s, c in cats.items()}
    skip_authors = {a.lower() for a in (reg.get("skip_authors") or ["AutoModerator"])} | {"[deleted]"}

    items: list[SocialItem] = []
    accepted: dict[str, str] = {}   # post external_id -> category
    for row in rows:                # pass 1: posts (comments may arrive before their post)
        kind = row.get("dataType")
        if kind == "community":
            _skip(stats, "community")
            continue
        if kind != "post":
            continue
        if not _post_id(row):
            _skip(stats, "no_id")
            continue
        sub = _sub_name(row)
        watched = sub.lower() in cat_by_sub
        text = f"{row.get('title') or ''} {row.get('body') or ''}"
        if not watched and not _keep_search_post(text, keywords):
            _skip(stats, "off_topic_post")
            continue
        item = post_item(row, cat_by_sub.get(sub.lower(), "keyword"))
        if not item.text:
            _skip(stats, "empty_post")
            continue
        if since and item.created_at < since:
            _skip(stats, "older_than_since")
            continue
        if item.external_id in accepted:
            continue
        accepted[item.external_id] = item.raw["category"]
        items.append(item)
        stats["posts"] += 1

    seen_comments: set[str] = set()
    for row in rows:                # pass 2: comments of accepted posts only
        if row.get("dataType") != "comment":
            continue
        cid = _comment_id(row)
        if not cid:
            _skip(stats, "no_id")
            continue
        if cid in seen_comments:    # the same comment shows up under several sorts
            continue
        seen_comments.add(cid)
        post_id = str(row.get("postId") or "")
        if post_id not in accepted:
            _skip(stats, "orphan_comment")
            continue
        body = str(row.get("body") or "").strip()
        if not body or str(row.get("username") or "").lower() in skip_authors:
            _skip(stats, "bot_or_empty_comment")
            continue
        items.append(comment_item(row, accepted[post_id]))
        stats["comments"] += 1

    log.info("reddit apify: %s", stats)
    return items, stats


def summarize(items: list[SocialItem]) -> dict:
    """What a run would store, by subreddit and category (used by the dry-run probe)."""
    out: dict = {"posts": 0, "comments": 0, "nested_replies": 0, "keyword_posts": 0,
                 "by_subreddit": {}, "by_category": {}, "oldest": None, "newest": None}
    for item in items:
        kind = "posts" if item.source_type == "post" else "comments"
        out[kind] += 1
        if kind == "comments" and item.raw.get("nested_reply"):
            out["nested_replies"] += 1
        if kind == "posts" and item.raw.get("category") == "keyword":
            out["keyword_posts"] += 1
        for table, key in (("by_subreddit", item.raw.get("subreddit")),
                           ("by_category", item.raw.get("category"))):
            bucket = out[table].setdefault(key, {"posts": 0, "comments": 0})
            bucket[kind] += 1
        out["oldest"] = item.created_at if out["oldest"] is None else min(out["oldest"], item.created_at)
        out["newest"] = item.created_at if out["newest"] is None else max(out["newest"], item.created_at)
    return out


def fetch(reg: dict, **kw) -> Iterator[SocialItem]:
    """extra_sources contract: yield SocialItems."""
    items, _stats = collect(reg, **kw)
    yield from items
