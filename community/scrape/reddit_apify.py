"""Reddit collector via Apify (actors trudax/reddit-scraper-lite or harshmaur/reddit-scraper-pro).

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

The actor is chosen by `sources.reddit_apify.actor`. trudax bills ~$0.004 per result and takes
~10 items/min; harshmaur (compared on 2026-10-11) is ~10x faster with native date filters and bills a
$0.01 start event plus about $0.0014 per result (measured: $2.75 for 2,332 rows; a few small runs
billed nothing, pattern unexplained - budget at the full rate). Each actor differs in two places only: its input
(build_payloads) and its row field names (normalize_harshmaur rewrites them into the trudax shape the
mapping below reads) - filters, threading and dedupe are shared.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Iterator

import httpx

from community.config.log import get_logger
from community.config.settings import settings
from community.scrape.base import AuthorMeta, Engagement, SocialItem, unified_score
from community.scrape.keyword_search import _MARKET_RE, _active_keywords
from community.store import db

log = get_logger("scrape.reddit_apify")

APIFY = "https://api.apify.com/v2"
DEFAULT_ACTOR = "harshmaur~reddit-scraper-pro"     # was trudax (~3x the price per row, ~10x slower)
DEFAULT_MAX_CHARGE_USD = 2.0    # per actor run; the VM's registry.yaml is hand-managed and may lack the key
# Reddit shares ONE Apify account (and its monthly usage limit) with Instagram and LinkedIn. On 2026-10-11
# `./cm doctor` showed $21.27 of $29 used with nothing but Reddit's tests added, so Reddit stops on its own:
DEFAULT_ACCOUNT_STOP_PCT = 85       # never start a run once the account is this far into its monthly limit
# ... and never spend more than this in one job. A full night (24 runs, ~1,000 billed rows at ~$0.0015 plus
# $0.01 per run) measured about $1.7-2.0 on 2026-10-14, so the earlier $1.50 cut every night short.
DEFAULT_NIGHTLY_BUDGET_USD = 2.5
# Keyword hits come from ALL of Reddit and must be India-relevant: the market gate alone accepts generic
# words ('trading', 'stock', 'share', 'option') and let crypto, forex, spam and trading-card posts through
# (probe 2026-10-11: 187 keyword hits, most off-target). Switch off with keyword_india_only: false.
_INDIA_TERMS = ("nifty", "banknifty", "sensex", "nse", "bse", "mcx", "f&o", "fno", "sebi", "demat",
                "zerodha", "kite", "groww", "upstox", "dhan", "angel one", "fyers", "5paisa", "icici direct",
                "tradetron", "algotest", "openalgo", "nubra", "india", "indian", "rupee", "inr", "\u20b9",
                "lakh", "crore")
_INDIA_RE = re.compile(r"(?<![a-z])(" + "|".join(re.escape(t) for t in _INDIA_TERMS) + r")(?![a-z])", re.I)
_INDIA_SUB = re.compile(r"india|indian|nse|bse|dalal|desi", re.I)
_READ_MORE = re.compile(r"\s*Read more\s*$")
_URL_POST_ID = re.compile(r"/comments/([a-z0-9]+)/", re.I)
_URL_COMMENT_ID = re.compile(r"/comment/([a-z0-9]+)/", re.I)

run_costs_usd: float = 0.0   # per-process accumulator (surfaced by the probe script)
run_log: list[dict] = []     # one entry per actor run: id, status, items, cost, seconds, partial


def _token() -> str:
    return os.getenv("APIFY_TOKEN", "").strip()


def _account_usage_real() -> tuple[float, float] | None:
    """(used, limit) in USD of the Apify account this cycle - the same fields `./cm doctor` shows for
    Instagram - or None when unreadable (a guard that cannot see must not block the run)."""
    try:
        r = httpx.get(f"{APIFY}/users/me/limits", headers={"Authorization": f"Bearer {_token()}"}, timeout=8)
        if r.status_code != 200:
            return None
        d = r.json().get("data", {})
        used = (d.get("current") or {}).get("monthlyUsageUsd")
        limit = (d.get("limits") or {}).get("maxMonthlyUsageUsd")
        return (float(used), float(limit)) if used is not None and limit else None
    except Exception:  # noqa: BLE001 - informational
        return None


def _account_usage() -> tuple[float, float] | None:
    return _account_usage_real()       # one indirection so tests can stub it without touching the network


class Budget:
    """Decides, before each actor run, whether Reddit may spend more: not once this job has spent its own
    budget, and not once the shared Apify account is `account_stop_pct` into its monthly limit (the rest
    is for Instagram and LinkedIn). Both limits take null in the registry to switch them off."""

    def __init__(self, reg: dict):
        nightly = reg.get("nightly_budget_usd", DEFAULT_NIGHTLY_BUDGET_USD)
        stop = reg.get("account_stop_pct", DEFAULT_ACCOUNT_STOP_PCT)
        self.nightly = None if nightly is None else float(nightly)
        self.stop_pct = None if stop is None else float(stop)
        self.start = run_costs_usd
        usage = _account_usage() if self.stop_pct is not None else None
        self.used0, self.limit = usage if usage else (None, None)
        self.live_used = self.used0

    def refresh(self) -> None:
        """Re-read the account's real usage. A run's own `usageTotalUsd` can read $0.00 for a run that
        returned 119 results (2026-10-11), so the account figure is the authority when it is higher."""
        if self.stop_pct is None or self.used0 is None:
            return
        usage = _account_usage()
        if usage:
            self.live_used, self.limit = usage

    def spent(self) -> float:
        local = run_costs_usd - self.start
        if self.live_used is not None and self.used0 is not None:
            return max(local, self.live_used - self.used0)
        return local

    def account_pct(self) -> float | None:
        return None if not self.limit else (self.used0 + self.spent()) / self.limit * 100

    def why_stop(self) -> str | None:
        self.refresh()
        if self.nightly is not None and self.spent() >= self.nightly:
            return f"this job's budget of ${self.nightly:.2f} is spent (${self.spent():.2f})"
        pct = self.account_pct()
        if pct is not None and self.stop_pct is not None and pct >= self.stop_pct:
            # short on purpose: the digest shows only ~120 characters of last_error, remedy included
            return (f"account at {pct:.0f}% of its ${self.limit:.0f} monthly limit; "
                    f"raise it (Apify Billing > Limits)")
        return None

    def summary(self) -> dict:
        self.refresh()
        pct = self.account_pct()
        return {"spent_usd": round(self.spent(), 4), "account_used_pct": None if pct is None else round(pct, 1)}


def _actor(reg: dict) -> str:
    return str(reg.get("actor") or DEFAULT_ACTOR).replace("/", "~")


def _profile(actor: str) -> str:
    """Which input/field dialect an actor speaks; unknown actors keep the original (trudax) one."""
    return "harshmaur" if actor.startswith("harshmaur~") else "trudax"


def _run_actor(actor: str, payload: dict, *, timeout_s: int = 900, memory_mb: int = 1024,
               max_charge_usd: float | None = None) -> list[dict]:
    """Start the actor, poll until it finishes, return the dataset items.

    A run that ends TIMED-OUT / FAILED / ABORTED still holds the results it collected (and was
    paid for): those are returned and the run is logged as partial. Only a run that ends badly
    with NOTHING raises."""
    global run_costs_usd
    started = time.monotonic()
    headers = {"Authorization": f"Bearer {_token()}"}
    params: dict = {"timeout": timeout_s, "memory": memory_mb}
    if max_charge_usd is not None:   # hard spend cap (pay-per-event actors stop when it is reached)
        params["maxTotalChargeUsd"] = max_charge_usd
    with httpx.Client(timeout=60, headers=headers) as c:
        r = c.post(f"{APIFY}/acts/{actor}/runs", params=params, json=payload)
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
                    "events": st.get("chargedEventCounts") or {},   # what Apify billed, per event type
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


DEFAULT_PRIORITY_CATEGORIES = ("brokers", "fno_algo")


def plan_harshmaur_runs(reg: dict, subs: list[str], queries: list[str],
                        cats: dict | None = None) -> list[tuple[list[str], list[str]]]:
    """harshmaur's maxPostsCount is ONE total for everything in a run (documented by the actor), so a
    busy subreddit used up the whole budget and 16 of 20 watched subreddits came back empty on
    2026-10-11. Listings therefore go one subreddit per run (each keeps its own post budget) and
    searches get their own runs. `subs_per_run` is deliberately not read: it is the trudax knob and
    the VM's registry still carries 5.

    Order matters because a spend budget can stop the job part-way: keyword searches first (a few cheap
    runs, and the brand search is the most valuable), then the subreddits of `priority_categories`
    (default brokers, then fno_algo), then the rest, each group keeping its given order."""
    per_sub = max(1, int(reg.get("listing_subs_per_run", 1)))
    per_query = max(1, int(reg.get("queries_per_run", 4)))
    if cats:
        order = [str(c).lower() for c in (reg.get("priority_categories") or DEFAULT_PRIORITY_CATEGORIES)]
        rank = {c: i for i, c in enumerate(order)}
        subs = sorted(subs, key=lambda s: rank.get(str(cats.get(s, "")).lower(), len(order)))   # stable
    return ([([], queries[i:i + per_query]) for i in range(0, len(queries), per_query)]
            + [(subs[i:i + per_sub], []) for i in range(0, len(subs), per_sub)])


def make_plan(reg: dict, subs: list[str], queries: list[str],
              cats: dict | None = None) -> list[tuple[list[str], list[str]]]:
    """The (subreddits, searches) chunks one collection pass is split into, for the configured actor.
    `cats` ({subreddit: category}) lets harshmaur order them by value."""
    if _profile(_actor(reg)) == "harshmaur":
        return plan_harshmaur_runs(reg, subs, queries, cats)
    return plan_runs(reg, subs, queries)


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
    # Billing is per item (~$0.004): stop the actor at a date so only fresh posts/comments are paid for.
    # Opt-in until verified (the console once rejected an input that carried date limits).
    if reg.get("date_limit_days"):
        limit = (datetime.now(timezone.utc) - timedelta(days=int(reg["date_limit_days"]))).strftime("%Y-%m-%d")
        payload["postDateLimit"] = limit
        payload["commentDateLimit"] = limit
    return payload


def _window_days(reg: dict) -> int:
    # nightly run + the next night re-reads each post once (comments that arrived after the first read);
    # every extra day is paid for again every night
    return int(reg.get("date_limit_days") or 2)


def _since(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


def _search_time(days: int) -> str:
    return "week" if days <= 7 else "month" if days <= 31 else "year"


def _post_budget(reg: dict, sub: str) -> int:
    """Posts to read from one subreddit: max_posts_per_sub, raised (never lowered) by post_overrides for
    the very busy ones - a nightly 10 would capture only a slice of them."""
    over = {str(k).lower(): int(v) for k, v in (reg.get("post_overrides") or {}).items()}
    return max(int(reg.get("max_posts_per_sub", 10)), over.get(sub.lower(), 0))


def build_harshmaur_payloads(reg: dict, subs: list[str], queries: list[str]) -> list[tuple[str, dict]]:
    """harshmaur takes a listing input and a search input; both shapes are the ones that ran
    successfully on 2026-10-11. Billing is not per result, so the date window is what limits volume."""
    posts = int(reg.get("max_posts_per_sub", 10))
    comments = int(reg.get("comments_per_post", 5))
    days = _window_days(reg)
    since = _since(days)
    runs: list[tuple[str, dict]] = []
    if subs:
        runs.append(("", {
            "subredditUrls": [f"https://www.reddit.com/r/{s}/" for s in subs],
            "crawlCommentsPerPost": comments > 0, "maxCommentsPerPost": comments,
            "maxPostsCount": sum(_post_budget(reg, s) for s in subs),   # a TOTAL across this run's subreddits
            "postedAfter": since, "commentedAfter": since,
            "fastMode": True, "includeNSFW": False}))
    if queries:
        runs.append((" search", {
            "searchTerms": list(queries), "searchPosts": True, "searchComments": False,
            "searchSort": "new", "searchTime": _search_time(days), "postedAfter": since,
            "crawlCommentsPerPost": False, "maxPostsCount": posts * len(queries),
            "includeNSFW": False}))
    return runs


def build_payloads(reg: dict, subs: list[str], queries: list[str]) -> list[tuple[str, dict]]:
    """The actor runs for one chunk of work, as (label suffix, input). trudax takes subreddits and
    searches in a single input; harshmaur needs one run for each."""
    if _profile(_actor(reg)) == "harshmaur":
        return build_harshmaur_payloads(reg, subs, queries)
    return [("", build_payload(reg, subs, queries))]


def worst_case_items(payload: dict) -> int:
    """Upper bound of rows one actor input can return (the probe's dry-scope estimate)."""
    if "maxItems" in payload:                                   # trudax
        return int(payload["maxItems"])
    posts = int(payload.get("maxPostsCount") or 0)              # harshmaur
    comments = int(payload.get("maxCommentsPerPost") or 0) if payload.get("crawlCommentsPerPost") else 0
    return posts * (1 + comments)


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


_REDDIT_IMAGE = re.compile(r"^https?://(i|preview)\.redd\.it/", re.I)


def _comment_parent(row: dict) -> str | None:
    parent = str(row.get("parentId") or "")
    if not parent:
        return None                                  # top level: comment_item falls back to the post id
    return parent if parent[:3] in ("t1_", "t3_") else f"t1_{parent}"


def normalize_harshmaur(row: dict) -> dict:
    """Rewrite a harshmaur/reddit-scraper-pro row into the field names the mapping reads.

    Quirks seen on 2026-10-11: a comment's `id` is the bare id (no t1_) and its `authorId` repeats the
    COMMENT's own id, so the author is only `authorName`; comment date and score are
    commentCreatedAt / commentUpVotes."""
    out = {**row, "_via": "apify_reddit_pro"}
    kind = row.get("dataType")
    if kind == "post":
        content = str(row.get("contentUrl") or "")
        out.update(
            username=row.get("authorName"),
            numberOfComments=row.get("commentsCount"),
            url=row.get("postUrl") or row.get("url"),
            upVoteRatio=row.get("upvoteRatio"),
            contentType=row.get("postType"),
            upVotes=row["upVotes"] if row.get("upVotes") is not None else row.get("score"),
            imageUrls=[content] if _REDDIT_IMAGE.match(content) else [])
    elif kind == "comment":
        cid = str(row.get("id") or "")
        out.update(
            id=(cid if cid.startswith("t1_") else f"t1_{cid}") if cid else "",
            username=row.get("authorName"),
            upVotes=row.get("commentUpVotes"),
            createdAt=row.get("commentCreatedAt"),
            parentId=_comment_parent(row))
        if row.get("subredditName"):
            out["parsedCommunityName"] = row["subredditName"]
    return out


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
        raw={"subreddit": _sub_name(row), "category": category, "via": row.get("_via") or "apify_reddit_lite",
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
        raw={"subreddit": _sub_name(row), "category": category, "via": row.get("_via") or "apify_reddit_lite",
             "depth": depth, "nested_reply": depth > 0},
    )


def _keep_search_post(text: str, keywords: list[tuple], sub: str = "", india_only: bool = False) -> bool:
    """Posts from subreddits we do not watch are search hits: they must mention a market term
    (and, with india_only, an India signal in the text or the subreddit name), unless a keyword that
    opted out of the gate (skip_context_gate) appears in the text."""
    low = text.lower()
    if any(skip and value.lower() in low for value, _query, skip in keywords):
        return True
    if not _MARKET_RE.search(text):
        return False
    return not india_only or bool(_INDIA_RE.search(text) or _INDIA_SUB.search(sub))


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

    profile = _profile(_actor(reg))
    sort_list = list(sorts or reg.get("sorts") or [str(reg.get("sort", "new"))])
    if profile == "harshmaur":      # its listings have no sort: one pass covers the whole date window
        sort_list = ["new"]
    run_kw = {"timeout_s": int(reg.get("timeout_s", 900)), "memory_mb": int(reg.get("memory_mb", 1024))}
    cap = reg.get("max_charge_usd", DEFAULT_MAX_CHARGE_USD)     # hard per-run spend cap; null = no cap
    if cap is not None:
        run_kw["max_charge_usd"] = float(cap)
    india_only = bool(reg.get("keyword_india_only", True))
    # One giant run (20 subreddits + 16 searches) timed out at 15 min on 2026-10-09: split the work
    # into balanced runs, each carrying a few subreddits AND a few searches (the input shape the
    # console accepted).
    plan = make_plan(reg, list(cats), queries, cats)
    n_runs = len(plan)
    log_start = len(run_log)
    rows: list[dict] = []
    budget = Budget(reg)
    for sort in sort_list:
        if "budget_stopped" in stats:
            break
        for k, (chunk_subs, chunk_queries) in enumerate(plan, 1):
            if "budget_stopped" in stats:
                break
            base = sort if n_runs == 1 else f"{sort}: run {k}/{n_runs}"
            for suffix, payload in build_payloads({**reg, "sort": sort}, chunk_subs, chunk_queries):
                label = base + suffix
                why = budget.why_stop()
                if why:
                    stats["budget_stopped"] = why
                    log.warning("reddit apify stopped before [%s]: %s", label, why)
                    break
                before = len(run_log)
                try:
                    got = _run_actor(_actor(reg), payload, **run_kw)
                except Exception as e:  # noqa: BLE001 — one failed run must not lose the others
                    stats["errors"][label] = f"{type(e).__name__}: {str(e)[:200]}"
                    log.warning("reddit apify [%s] failed: %s", label, stats["errors"][label])
                    got = None
                if len(run_log) > before:
                    run_log[-1]["label"] = label
                    run_log[-1]["subs"] = list(chunk_subs)
                if got is None:
                    continue
                log.info("reddit apify [%s]: %d rows", label, len(got))
                stats["by_sort"][sort] = stats["by_sort"].get(sort, 0) + len(got)
                rows.extend(normalize_harshmaur(r) if profile == "harshmaur" else r for r in got)
    stats["runs"] = run_log[log_start:]
    stats["budget"] = budget.summary()
    if not stats["by_sort"]:
        if stats.get("budget_stopped") and not stats["errors"]:
            raise RuntimeError("reddit apify: not run - " + stats["budget_stopped"])
        raise RuntimeError("reddit apify: every run failed: " + "; ".join(stats["errors"].values()))
    stats["rows"] = len(rows)
    if since is None and reg.get("max_post_age_days"):
        # a `new` listing also returns pinned/sticky posts of any age (a 2019 post came back on 2026-10-11)
        since = datetime.now(timezone.utc) - timedelta(days=int(reg["max_post_age_days"]))
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
        if not watched and not _keep_search_post(text, keywords, sub, india_only):
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

    posting = {i.raw.get("subreddit", "").lower() for i in items if i.source_type == "post"}
    silent = sorted((s for s in cats if s.lower() not in posting), key=str.lower)
    if silent and not stats.get("budget_stopped"):      # a budget stop explains missing subreddits by itself
        stats["silent_subs"] = silent
        log.warning("reddit apify: no posts from %d watched subreddit(s): %s", len(silent), ", ".join(silent))
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
    items, stats = collect(reg, **kw)
    yield from items
    if stats.get("budget_stopped"):
        # raised AFTER the items are stored: extra_sources records the run as an error (so health and the
        # Source page show it, and last_success_at is not advanced) without losing what was fetched
        raise RuntimeError("reddit apify stopped early: " + stats["budget_stopped"])
