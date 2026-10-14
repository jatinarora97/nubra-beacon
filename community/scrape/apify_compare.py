"""Compare Reddit actors on Apify with one small standard job each (tooling, writes no DB rows).

Why: trudax/reddit-scraper-lite bills $0.004 per result and is slow; the Store lists cheaper
Reddit actors but their output formats are unverified. This runs a tiny listing job (a few
subreddits, a few posts, a few comments, recent dates) and a tiny keyword-search job on each
candidate and prints what comes back — cost, time, fields, dates, threading, sample items — so a
replacement can be chosen on evidence. Every run carries a hard spend cap (maxTotalChargeUsd).

    docker compose exec -T api python scripts/apify_actor_compare.py            # show the plan
    docker compose exec -T api python scripts/apify_actor_compare.py --yes
    docker compose exec -T api python scripts/apify_actor_compare.py --yes --only harshmaur

Input fields come from each actor's public input schema (read 2026-10-11). NOTE: the Store entry
microworlds/reddit-scraper-lite copies trudax's description but its input schema is an Apollo.io
scraper — it is deliberately not a candidate.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone

from community.scrape import reddit_apify

ACTORS = {
    "harshmaur": "harshmaur~reddit-scraper-pro",        # $0.0015 per result; date filters, many search terms
    "automation-lab": "automation-lab~reddit-scraper",  # $0.00115 per post, $0.000575 per comment
    "epctex": "epctex~reddit-scraper",                  # $0.001 per item + $0.025 per listing page
}
KEYWORD = "nubra"
_DATE_KEYS = ("createdAt", "created_at", "createdUtc", "created_utc", "created", "postedAt", "timestamp", "date")
_THREAD_KEYS = ("parentId", "parent_id", "parentCommentId", "depth", "replyDepth", "level", "replies")


def _urls(subs: list[str]) -> list[str]:
    return [f"https://www.reddit.com/r/{s}/" for s in subs]


def build_input(actor: str, job: str, subs: list[str], posts: int, comments: int, days: int) -> dict:
    """The standard small job for one actor: 'listing' (subreddit pages with comments) or 'search'."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    builders = {
        ("harshmaur", "listing"): lambda: {
            "subredditUrls": _urls(subs), "crawlCommentsPerPost": True,
            "maxPostsCount": posts * len(subs), "maxCommentsPerPost": comments,
            "postedAfter": since, "commentedAfter": since, "fastMode": True, "includeNSFW": False},
        ("harshmaur", "search"): lambda: {
            "searchTerms": [KEYWORD], "searchPosts": True, "searchComments": False,
            "searchSort": "new", "searchTime": "week", "postedAfter": since,
            "crawlCommentsPerPost": False, "maxPostsCount": posts, "includeNSFW": False},
        ("automation-lab", "listing"): lambda: {
            "urls": _urls(subs), "sort": "new", "maxPostsPerSource": posts,
            "includeComments": True, "maxCommentsPerPost": comments, "commentDepth": 3},
        ("automation-lab", "search"): lambda: {
            "searchQuery": KEYWORD, "sort": "new", "timeFilter": "week",
            "maxPostsPerSource": posts, "includeComments": False},
        ("epctex", "listing"): lambda: {
            "startUrls": _urls(subs), "sort": "new", "includeComments": True,
            "maxItems": len(subs) * posts * (1 + comments)},
        ("epctex", "search"): lambda: {
            "search": KEYWORD, "searchMode": "link", "sort": "new", "time": "week",
            "includeComments": False, "maxItems": posts},
    }
    return builders[(actor, job)]()


def _parse(value):
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, tz=timezone.utc)
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _kind(item: dict) -> str | None:
    for key in ("dataType", "type", "kind"):
        v = item.get(key)
        if isinstance(v, str):
            low = v.lower()
            if "comment" in low:
                return "comment"
            if "post" in low or "submission" in low or low == "link":
                return "post"
    if any(k in item for k in ("parentId", "parent_id", "commentId", "depth")):
        return "comment"
    return "post" if "title" in item else None


def inspect_items(items: list[dict]) -> dict:
    """What an actor's output looks like: fields, date field and range, threading, samples."""
    fields: set[str] = set()
    for it in items[:20]:
        fields.update(it)
    date_field = next((k for k in _DATE_KEYS if any(k in it for it in items)), None)
    dated = []
    if date_field:
        for it in items:
            if date_field in it and _parse(it[date_field]):
                dated.append((_parse(it[date_field]), it[date_field]))
    return {
        "count": len(items),
        "fields": sorted(fields),
        "date_field": date_field,
        "oldest": min(dated)[1] if dated else None,
        "newest": max(dated)[1] if dated else None,
        "has_threading": any(k in it for it in items for k in _THREAD_KEYS),
        "sample_post": next((i for i in items if _kind(i) == "post"), None),
        "sample_comment": next((i for i in items if _kind(i) == "comment"), None),
    }


def run_job(actor: str, job: str, subs: list[str], *, posts: int, comments: int, days: int,
            cap_usd: float, timeout_s: int) -> dict:
    """Run one standard job with a hard spend cap; never raises (the error is the result)."""
    payload = build_input(actor, job, subs, posts, comments, days)
    started = time.monotonic()
    before = len(reddit_apify.run_log)
    try:
        items = reddit_apify._run_actor(ACTORS[actor], payload, timeout_s=timeout_s,
                                        memory_mb=1024, max_charge_usd=cap_usd)
        error = None
    except Exception as e:  # noqa: BLE001 — a rejected input is exactly what this tool must report
        items, error = [], f"{type(e).__name__}: {str(e)[:300]}"
        body = getattr(getattr(e, "response", None), "text", "")   # Apify names the bad field here
        if body:
            error += f" | {body[:400]}"
    run = reddit_apify.run_log[-1] if len(reddit_apify.run_log) > before else {}
    return {"actor": actor, "job": job, "payload": payload, "error": error, "info": inspect_items(items),
            "status": run.get("status", "ERROR" if error else "?"), "cost_usd": run.get("cost_usd", 0.0),
            "events": run.get("events", {}),
            "seconds": run.get("seconds", round(time.monotonic() - started, 1))}


def _short(item: dict | None, limit: int = 700) -> str:
    return "(none)" if item is None else json.dumps(item, default=str, ensure_ascii=False)[:limit]


def report(results: list[dict], sample_chars: int = 700) -> None:
    print("\n=== COMPARISON (nothing was written to the database) ===")
    print(f"{'actor / job':<26} {'status':<10} {'items':>5} {'sec':>6} {'cost':>8} {'items/min':>9} "
          f"{'date field':<11} thread")
    for r in results:
        info = r["info"]
        per_min = f"{info['count'] / r['seconds'] * 60:.1f}" if r["seconds"] and info["count"] else "-"
        print(f"{r['actor'] + ' / ' + r['job']:<26} {r['status']:<10} {info['count']:>5} {r['seconds']:>6.0f} "
              f"${r['cost_usd']:>6.3f} {per_min:>9} {str(info['date_field']):<11} {info['has_threading']}")
    for r in results:
        info = r["info"]
        print(f"\n--- {r['actor']} / {r['job']} ---")
        if r["error"]:
            print("ERROR:", r["error"])
            print("input sent:", json.dumps(r["payload"]))
            continue
        print("fields:", ", ".join(info["fields"][:45]))
        print(f"dates: {info['oldest']}  ->  {info['newest']}")
        print("billed events:", r.get("events") or "(not reported)")
        print("sample post   :", _short(info["sample_post"], sample_chars))
        print("sample comment:", _short(info["sample_comment"], sample_chars))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--only", default=",".join(ACTORS), help="comma-separated: " + ", ".join(ACTORS))
    ap.add_argument("--subs", default="IndianStockMarket,Zerodha", help="subreddits for the listing job")
    ap.add_argument("--posts", type=int, default=5, help="posts per subreddit")
    ap.add_argument("--comments", type=int, default=3, help="comments per post")
    ap.add_argument("--days", type=int, default=3, help="only posts/comments newer than this (where supported)")
    ap.add_argument("--cap-usd", type=float, default=0.15, help="hard spend cap PER RUN")
    ap.add_argument("--timeout", type=int, default=600, help="seconds each run may take")
    ap.add_argument("--no-search", action="store_true", help="skip the keyword-search job")
    ap.add_argument("--sample-chars", type=int, default=700, help="print this much of each sample item")
    ap.add_argument("--yes", action="store_true", help="actually run (spends up to the caps)")
    args = ap.parse_args(argv)

    if not reddit_apify._token():
        print("APIFY_TOKEN is not set in this environment — nothing to do.")
        return 1
    actors = [a.strip() for a in args.only.split(",") if a.strip()]
    unknown = [a for a in actors if a not in ACTORS]
    if unknown:
        print(f"unknown actor(s) {unknown}; choose from {list(ACTORS)}")
        return 2
    subs = [s.strip() for s in args.subs.split(",") if s.strip()]
    jobs = ["listing"] + ([] if args.no_search else ["search"])
    print(f"plan: {len(actors)} actors x {len(jobs)} jobs = {len(actors) * len(jobs)} runs, "
          f"each capped at ${args.cap_usd:.2f} (worst case ${len(actors) * len(jobs) * args.cap_usd:.2f})")
    for a in actors:
        print(f"  {a}: {ACTORS[a]}")
    print(f"listing job: r/{', r/'.join(subs)}, {args.posts} posts each, {args.comments} comments per post, "
          f"last {args.days} days; search job: '{KEYWORD}'")
    if not args.yes:
        print("\nPlan only. Add --yes to run it.")
        return 0
    results = []
    for a in actors:
        for job in jobs:
            print(f"\nrunning {a} / {job} ...", flush=True)
            results.append(run_job(a, job, subs, posts=args.posts, comments=args.comments,
                                   days=args.days, cap_usd=args.cap_usd, timeout_s=args.timeout))
    report(results, args.sample_chars)
    print(f"\ntotal Apify cost of this comparison: ${reddit_apify.run_costs_usd:.4f}")
    return 0
