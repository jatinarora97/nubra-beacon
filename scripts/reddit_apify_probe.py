"""Dry run of the Apify Reddit collector — writes NOTHING to the database.

Quick check (a few cents): 2 subreddits, 3 posts each, 3 comments per post.

    docker compose exec -T api python scripts/reddit_apify_probe.py
    docker compose exec -T api python scripts/reddit_apify_probe.py --proxy DATACENTER   # compare cost

FULL real-scope test: everything the old Reddit collector did — every watched subreddit
(watch_sources), the old limits (10 posts / 15 comments), the active keyword searches with the
market-term filter, nested replies, categories — and optionally the extra sorts it ran daily.
This can cost real money, so it prints the scope and the worst-case item count first and only
runs with --yes:

    docker compose exec -T api python scripts/reddit_apify_probe.py --full
    docker compose exec -T api python scripts/reddit_apify_probe.py --full --yes
    docker compose exec -T api python scripts/reddit_apify_probe.py --full --yes --sorts new,hot,rising,top --top-time day

Each sort is a separate actor run; a sort the actor rejects is reported, not fatal.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

# the DB is only read for information (existing posts, watched subreddits/keywords): never hang on it
os.environ.setdefault("PGCONNECT_TIMEOUT", "5")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from community.config.settings import settings
from community.scrape import reddit_apify


def _existing_post_ids(ids: list[str]) -> set[str] | None:
    """Read-only: which of these posts are already stored (proves the dedupe); None if unknown."""
    try:
        from community.store import db
        rows = db.query("SELECT external_id FROM social_items "
                        "WHERE source='reddit' AND external_id = ANY(%s)", (ids,))
        return {r["external_id"] for r in rows}
    except Exception as e:  # noqa: BLE001 — informational only
        print(f"(could not check the database for existing posts: {type(e).__name__})")
        return None


def _print_report(items, stats) -> None:
    summary = reddit_apify.summarize(items)
    print("\n=== RESULT (nothing was written to the database) ===")
    print(f"rows returned by the actor, per sort: {json.dumps(stats['by_sort'])}")
    if stats["runs"]:
        print("\nactor runs:")
        for r in stats["runs"]:
            note = "  (PARTIAL: kept what it collected)" if r.get("partial") else ""
            print(f"  {r.get('label', '?'):<18} {r['status']:<10} {r['items']:>5} items  "
                  f"{r['seconds']:>6.0f}s  ${r['cost_usd']:.4f}{note}")
    if stats["errors"]:
        print(f"RUNS THAT FAILED: {json.dumps(stats['errors'], indent=1)}")
    print(f"would store: {summary['posts']} posts, {summary['comments']} comments "
          f"({summary['nested_replies']} nested replies, {summary['keyword_posts']} keyword-search posts)")
    print(f"dropped: {json.dumps(stats['skipped'])}")
    if summary["oldest"]:
        print(f"post/comment dates: {summary['oldest']:%Y-%m-%d %H:%M} -> {summary['newest']:%Y-%m-%d %H:%M} UTC")
    print("\nby category (posts / comments):")
    for cat, n in sorted(summary["by_category"].items(), key=lambda kv: -kv[1]["posts"]):
        print(f"  {cat:<18} {n['posts']:>4} / {n['comments']:<5}")
    print("\nby subreddit (posts / comments):")
    for sub, n in sorted(summary["by_subreddit"].items(), key=lambda kv: -kv[1]["posts"]):
        print(f"  r/{sub:<24} {n['posts']:>4} / {n['comments']:<5}")
    post_ids = [i.external_id for i in items if i.source_type == "post"]
    if post_ids:
        known = _existing_post_ids(post_ids)
        if known is None:
            print("\nalready in the database: not checked (database unreachable from here)")
        else:
            print(f"\nalready in the database: {len(known)} of {len(post_ids)} posts "
                  f"(duplicates are skipped on insert); {len(post_ids) - len(known)} would be new")
    kw = [i for i in items if i.source_type == "post" and i.raw.get("category") == "keyword"][:8]
    if kw:
        print("\nkeyword-search posts (check these are on-topic):")
        for i in kw:
            print(f"  r/{i.raw.get('subreddit')}: {i.text[:100]!r}")
    print(f"\nApify cost of this run: ${reddit_apify.run_costs_usd:.4f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--subs", default="IndianStockMarket,IndiaInvestments",
                    help="quick mode: comma-separated subreddits")
    ap.add_argument("--max-posts", type=int, default=3, help="quick mode: posts per subreddit")
    ap.add_argument("--comments", type=int, default=3, help="quick mode: comments per post")
    ap.add_argument("--keywords", action="store_true", help="quick mode: also run keyword searches")
    ap.add_argument("--proxy", default=None, help="Apify proxy group instead of the registry's")
    ap.add_argument("--full", action="store_true",
                    help="real scope: all watched subreddits + keyword searches + the old limits")
    ap.add_argument("--yes", action="store_true", help="--full: actually run (this costs money)")
    ap.add_argument("--sorts", default="new", help="--full: comma-separated sorts, e.g. new,hot,rising,top")
    ap.add_argument("--top-time", default=None, help="--full: time window sent with the top sort, e.g. day")
    ap.add_argument("--max-items", type=int, default=2000, help="--full: item cap per actor run")
    ap.add_argument("--subs-per-run", type=int, default=None, help="--full: subreddits per actor run")
    ap.add_argument("--queries-per-run", type=int, default=None, help="--full: keyword searches per actor run")
    ap.add_argument("--timeout", type=int, default=None, help="--full: seconds each actor run may take")
    ap.add_argument("--price-per-1000", type=float, default=None,
                    help="--full: the actor's price per 1,000 results (from its Apify page) for an estimate")
    args = ap.parse_args()

    if not reddit_apify._token():
        print("APIFY_TOKEN is not set in this environment — nothing to do.")
        return 1

    reg = {**(settings.registry.get("sources", {}).get("reddit_apify") or {}), "enabled": True}
    if args.proxy:
        reg["proxy_groups"] = [args.proxy]
    print("Actor:", reddit_apify._actor(reg))

    if args.full:
        old = settings.registry.get("sources", {}).get("reddit", {}) or {}
        reg.update(max_posts_per_sub=int(old.get("max_posts_per_sub", 10)),
                   comments_per_post=int(old.get("comments_per_post", 15)),
                   max_items_per_run=args.max_items)
        if args.top_time:
            reg["top_time"] = args.top_time
        if args.subs_per_run:
            reg["subs_per_run"] = args.subs_per_run
        if args.queries_per_run:
            reg["queries_per_run"] = args.queries_per_run
        if args.timeout:
            reg["timeout_s"] = args.timeout
        sorts = [s.strip() for s in args.sorts.split(",") if s.strip()]
        subs = reddit_apify._subreddits(reg)
        keywords = reddit_apify._active_keywords()
        queries = [q for _kw, q, _gate in keywords]
        plan = reddit_apify.plan_runs(reg, list(subs), queries)
        per_run_items = [reddit_apify.build_payload(reg, a, b)["maxItems"] for a, b in plan]
        print(f"\nFULL SCOPE: {len(subs)} subreddits, {len(queries)} keyword searches, "
              f"{reg['max_posts_per_sub']} posts each, {reg['comments_per_post']} comments per post")
        for cat in sorted(set(subs.values())):
            print(f"  {cat}: {', '.join(sorted(s for s, c in subs.items() if c == cat))}")
        print(f"  keywords: {', '.join(kw for kw, _q, _g in keywords) or '(none)'}")
        worst = sum(per_run_items) * len(sorts)
        print(f"sorts: {sorts}; each sort = {len(plan)} actor runs of about "
              f"{max(len(a) for a, _ in plan)} subreddits + {max(len(b) for _, b in plan)} searches "
              f"(each run may take up to {reg.get('timeout_s', 900)} s)")
        print(f"worst case: {worst} items over {len(plan) * len(sorts)} actor runs")
        if args.price_per_1000 is not None:
            print(f"estimated worst-case cost: ${worst / 1000 * args.price_per_1000:.2f}")
        else:
            print("(multiply the item count by the actor's price per 1,000 results, or pass --price-per-1000)")
        if not args.yes:
            print("\nDry scope only. Add --yes to run it for real.")
            return 0
        print("\nRunning (this can take 10-30+ minutes)...", flush=True)
        items, stats = reddit_apify.collect(reg, sorts=sorts)
        _print_report(items, stats)
        return 0

    subs = [s.strip() for s in args.subs.split(",") if s.strip()]
    queries = ["<active keyword searches from watch_sources>"] if args.keywords else []
    print("Input sent (searches shown as a placeholder):")
    print(json.dumps(reddit_apify.build_payload(
        {**reg, "max_posts_per_sub": args.max_posts, "comments_per_post": args.comments}, subs, queries),
        indent=2))
    print("\nRunning the actor (usually 1-5 minutes)...", flush=True)
    items, stats = reddit_apify.collect(reg, only_subs=subs, with_keywords=args.keywords,
                                        max_posts=args.max_posts, comments=args.comments)
    _print_report(items, stats)
    for kind in ("post", "comment"):
        sample = [i for i in items if i.source_type == kind][:3]
        print(f"\n--- first {len(sample)} {kind}s ---")
        for i in sample:
            print(f"{i.external_id}  r/{i.raw.get('subreddit')}  by {i.author}  {i.created_at:%Y-%m-%d %H:%M} UTC"
                  f"  parent={i.parent_id}\n    {i.text[:110]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
