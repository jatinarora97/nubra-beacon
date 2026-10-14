"""Production hardening of the Reddit-via-Apify path: spend cap default, India filter for keyword hits,
ingest cutover from the vendored scraper, Apify-backed engagement refresh, probes and the backfill flag."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from community.scrape import reddit_apify
from tests.test_reddit_apify_pro import ACTOR, CATS, COMMENT, POST, run

KEYWORDS = [("trading api", "trading api", False)]


def hit(post_id, sub, title, body=""):
    return {**POST, "id": f"t3_{post_id}", "parsedId": post_id, "title": title, "body": body,
            "communityName": f"r/{sub}", "parsedCommunityName": sub, "contentUrl": "",
            "postUrl": f"https://www.reddit.com/r/{sub}/comments/{post_id}/x/", "createdAt": "2026-10-11T07:00:00.000Z"}


class SpendCapDefaultTests(unittest.TestCase):
    ROWS = {"listing": [POST, COMMENT], "search": []}

    def test_a_safe_per_run_cap_is_sent_when_the_registry_says_nothing(self):
        # the VM's registry.yaml is hand-managed and may lack the key: the default must protect it
        _, _, calls = run(self.ROWS)
        self.assertEqual(calls[0][2]["max_charge_usd"], reddit_apify.DEFAULT_MAX_CHARGE_USD)
        self.assertEqual(reddit_apify.DEFAULT_MAX_CHARGE_USD, 2.0)

    def test_the_registry_can_change_the_cap(self):
        _, _, calls = run(self.ROWS, reg_extra={"max_charge_usd": 0.5})
        self.assertEqual(calls[0][2]["max_charge_usd"], 0.5)

    def test_an_explicit_null_removes_the_cap(self):
        _, _, calls = run(self.ROWS, reg_extra={"max_charge_usd": None})
        self.assertNotIn("max_charge_usd", calls[0][2])


class IndiaKeywordFilterTests(unittest.TestCase):
    """Probe 2026-10-11: 187 keyword hits, mostly crypto/forex/spam/trading-card posts, because the market
    gate accepts generic words ('trading', 'stock', 'share', 'option'). Keyword hits must be India-relevant."""

    def kept(self, sub, title, body="", **reg):
        rows = {"listing": [], "search": [hit("h1", sub, title, body)]}
        items, stats, _ = run(rows, subs={}, keywords=KEYWORDS, reg_extra=reg)
        return bool(items)

    def test_generic_trading_posts_without_an_india_signal_are_dropped(self):
        self.assertFalse(self.kept("yugioh", "Trading cards: selling my stock and shares of rare cards"))
        self.assertFalse(self.kept("KCEX", "Three stories that move perpetual futures trading books"))
        self.assertFalse(self.kept("ai_trading", "Rebuilt my XAUUSD EA volume layer, option to trade futures"))

    def test_posts_with_an_india_market_signal_are_kept(self):
        self.assertTrue(self.kept("StockMarketIndia", "Zerodha Kite API rate limits for trading bots"))
        self.assertTrue(self.kept("x", "Nubra broker review: brokerage and F&O charges"))
        self.assertTrue(self.kept("x", "Nifty option chain trading on expiry day, SEBI new rules"))

    def test_an_indian_subreddit_name_counts_as_the_signal(self):
        # watched subs are never filtered; unwatched Indian subs (typos in the seed list!) still get through
        self.assertTrue(self.kept("IndiaOptionSelling", "Option Selling Series: Max Drawdown Duration in backtests"))

    def test_the_filter_can_be_switched_off(self):
        self.assertTrue(self.kept("yugioh", "Trading cards: selling my stock and shares", keyword_india_only=False))

    def test_a_brand_keyword_that_opted_out_of_the_gate_is_still_kept(self):
        rows = {"listing": [], "search": [hit("h2", "x", "my nubra account got blocked")]}
        items, _, _ = run(rows, subs={}, keywords=[("nubra", "nubra", True)])
        self.assertEqual(len(items), 1)

    def test_watched_subreddits_are_never_filtered(self):
        rows = {"listing": [hit("w1", "Zerodha", "Console is down again"), COMMENT], "search": []}
        items, _, _ = run(rows)
        self.assertTrue(any(i.external_id == "t3_w1" for i in items))

    def test_skipped_hits_are_counted_as_off_topic(self):
        rows = {"listing": [], "search": [hit("h3", "yugioh", "Trading cards: stock and shares")]}
        _, stats, _ = run(rows, subs={}, keywords=KEYWORDS)
        self.assertEqual(stats["skipped"], {"off_topic_post": 1})


# ── ingest cutover ────────────────────────────────────────────────────────

from datetime import datetime, timezone  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

from community.scrape import ingest, refresh  # noqa: E402

NOW = datetime(2026, 10, 12, 5, 30, tzinfo=timezone.utc)


def ingest_registry(apify_enabled):
    return {"sources": {"twitter": {"csv_backfill": None},
                        "reddit": {"fetch_every_hours": 1, "sort_types_hourly": ["new"]},
                        "reddit_apify": {"enabled": apify_enabled}}}


def run_ingest(apify_enabled, daily=False):
    fake_repo = MagicMock()
    fake_repo.now_utc.return_value = NOW
    fake_repo.get_state.return_value = None
    with patch.object(ingest, "settings", SimpleNamespace(registry=ingest_registry(apify_enabled))), \
         patch.object(ingest, "repo", fake_repo), \
         patch.object(ingest.twitter, "fetch_live_capped", return_value=([], "note")), \
         patch.object(ingest.reddit, "fetch_live", return_value=([], ["ok"])) as fetch, \
         patch("community.scrape.refresh.run", return_value={}) as refresh_run, \
         patch("community.scrape.keyword_search.run", return_value={"x": 1}) as keyword_run, \
         patch("community.scrape.extra_sources.run", return_value={}):
        stats = ingest.run(daily=daily)
    return stats, SimpleNamespace(fetch=fetch, refresh=refresh_run, keyword=keyword_run, repo=fake_repo)


class IngestCutoverTests(unittest.TestCase):
    def test_with_apify_on_the_vendored_scraper_and_old_keyword_search_are_retired(self):
        stats, m = run_ingest(True)
        m.fetch.assert_not_called()
        m.keyword.assert_not_called()
        self.assertEqual(stats["reddit_health"], ["superseded by reddit_apify"])
        self.assertEqual(stats["keyword_search"], {"skipped": "superseded by reddit_apify"})
        self.assertEqual(stats["reddit_sorts"], [])

    def test_the_retired_reddit_source_does_not_stamp_a_fresh_success(self):
        _, m = run_ingest(True)
        stamped = [c.args[1] for c in m.repo.advance_state.call_args_list]
        self.assertEqual(stamped, ["twitter"])      # ingest/reddit stays as it was

    def test_the_engagement_refresh_is_told_whether_this_is_the_morning_build(self):
        _, m = run_ingest(True, daily=True)
        m.refresh.assert_called_once_with(daily=True)
        _, m = run_ingest(True, daily=False)
        m.refresh.assert_called_once_with(daily=False)

    def test_with_apify_off_nothing_changes(self):
        stats, m = run_ingest(False)
        m.fetch.assert_called_once()
        m.keyword.assert_called_once()
        self.assertEqual(stats["keyword_search"], {"x": 1})


# ── engagement refresh via Apify ──────────────────────────────────────────

U1 = "https://www.reddit.com/r/IndianStockMarket/comments/1wzqkgr/anyone_going_through_this/"
U2 = "https://www.reddit.com/r/Zerodha/comments/1x0aaaa/console_down/"
ROWS = [{"item_id": 1, "url": U1, "engagement": {"native": {"upvotes": 3, "comments": 1}}, "priority": 9},
        {"item_id": 2, "url": U2, "engagement": None, "priority": 5}]


class ApifyRefreshTests(unittest.TestCase):
    def run_refresh(self, *, daily, apify=None, rows=ROWS, items=()):
        reg = {"sources": {"reddit": {}, "reddit_apify": {"enabled": True, "actor": ACTOR, **(apify or {})}}}
        with patch.object(refresh, "settings", SimpleNamespace(registry=reg)), \
             patch.object(refresh, "_candidates", return_value=rows) as cand, \
             patch.object(reddit_apify, "_run_actor", return_value=list(items)) as actor, \
             patch.object(refresh, "db") as db:
            db.jsonb.side_effect = lambda x: x
            out = refresh.run(daily=daily)
        return out, cand, actor, db

    def test_it_only_runs_in_the_morning_build(self):
        out, cand, actor, _ = self.run_refresh(daily=False)
        self.assertIn("morning build", out["note"])
        cand.assert_not_called()
        actor.assert_not_called()

    def test_one_actor_run_reads_all_the_threads_without_their_comments(self):
        _, _, actor, _ = self.run_refresh(daily=True, items=[])
        self.assertEqual(actor.call_count, 1)
        name, payload = actor.call_args.args
        self.assertEqual(name, ACTOR)
        self.assertEqual(payload["startUrls"], [{"url": U1}, {"url": U2}])
        self.assertFalse(payload["crawlCommentsPerPost"])
        self.assertEqual(payload["maxPostsCount"], 2)
        self.assertEqual(actor.call_args.kwargs["max_charge_usd"], reddit_apify.DEFAULT_MAX_CHARGE_USD)

    def test_fresh_counts_replace_the_stale_engagement(self):
        items = [{**POST, "id": "t3_1wzqkgr", "upVotes": 4463, "commentsCount": 72}]
        out, _, _, db = self.run_refresh(daily=True, items=items)
        self.assertEqual((out["candidates"], out["refreshed"], out["unreadable"]), (2, 1, 1))
        sql, (engagement, item_id) = db.execute.call_args.args
        self.assertIn("UPDATE social_items SET engagement", sql)
        self.assertEqual(item_id, 1)
        self.assertEqual(engagement["native"], {"upvotes": 4463, "comments": 72})
        self.assertGreater(engagement["score"], 0)
        self.assertIn("refreshed_at", engagement)

    def test_score_is_used_when_upvotes_is_missing_and_ids_without_a_prefix_match(self):
        items = [{"dataType": "post", "id": "1x0aaaa", "score": 12, "commentsCount": 3}]
        out, _, _, db = self.run_refresh(daily=True, items=items)
        self.assertEqual(out["refreshed"], 1)
        self.assertEqual(db.execute.call_args.args[1][0]["native"]["upvotes"], 12)

    def test_no_candidates_means_no_actor_run(self):
        out, _, actor, _ = self.run_refresh(daily=True, rows=[])
        self.assertIn("no suggested", out["note"])
        actor.assert_not_called()

    def test_the_batch_size_can_be_set_or_switched_off(self):
        _, cand, _, _ = self.run_refresh(daily=True, apify={"refresh_max_threads": 5})
        cand.assert_called_once_with(5)
        out, cand, _, _ = self.run_refresh(daily=True, apify={"refresh_max_threads": 0})
        self.assertIn("disabled", out["note"])
        cand.assert_not_called()

    def test_only_the_harshmaur_actor_is_supported(self):
        out, cand, actor, _ = self.run_refresh(daily=True, apify={"actor": "trudax~reddit-scraper-lite"})
        self.assertIn("harshmaur", out["note"])
        actor.assert_not_called()

    def test_with_apify_off_the_original_path_is_used(self):
        reg = {"sources": {"reddit": {"refresh_max_threads": 20}, "reddit_apify": {"enabled": False}}}
        with patch.object(refresh, "settings", SimpleNamespace(registry=reg)), \
             patch.object(refresh, "_candidates", return_value=[]) as cand, \
             patch.object(reddit_apify, "_run_actor") as actor:
            out = refresh.run(daily=True)
        cand.assert_called_once_with(20)
        actor.assert_not_called()
        self.assertEqual(out, {"note": "no suggested reddit opportunities to refresh"})


# ── doctor / live probe / health digest ───────────────────────────────────

import os  # noqa: E402

from community import diagnostics  # noqa: E402
from community.health import digest  # noqa: E402


def apify_registry(enabled=True, actor=ACTOR):
    return SimpleNamespace(registry={"sources": {"reddit_apify": {"enabled": enabled, "actor": actor}}})


class LiveProbeTests(unittest.TestCase):
    def probe(self, *, token="tok", status=200):
        env = {"APIFY_TOKEN": token} if token else {}
        resp = SimpleNamespace(status_code=status, json=lambda: {"data": {"name": "reddit-scraper-pro"}})
        with patch.dict(os.environ, env, clear=False), \
             patch("community.config.settings.settings", apify_registry()), \
             patch("httpx.get", return_value=resp) as get:
            if not token:
                os.environ.pop("APIFY_TOKEN", None)
            return diagnostics._live_probe("reddit_apify"), get

    def test_it_checks_the_configured_actor_with_the_token_and_starts_no_run(self):
        out, get = self.probe()
        self.assertEqual(out["live"], "ok")
        url = get.call_args.args[0]
        self.assertTrue(url.endswith("/acts/" + ACTOR), url)         # a GET on the actor, not a run
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer tok")

    def test_a_missing_token_is_reported_not_raised(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("APIFY_TOKEN", None)
            self.assertEqual(diagnostics._live_probe("reddit_apify"), {"live": "no_key"})

    def test_an_unknown_actor_is_a_failure(self):
        out, _ = self.probe(status=404)
        self.assertEqual(out["live"], "http_404")

    def test_the_daily_health_digest_probes_it_once_enabled(self):
        self.assertIn("reddit_apify", digest._PROBE_NAMES)


class DoctorTests(unittest.TestCase):
    def last(self, check):
        del diagnostics._RESULTS[:]
        check()
        return diagnostics._RESULTS[-1]

    def test_the_old_reddit_check_steps_aside_when_apify_is_on(self):
        with patch("community.config.settings.settings", apify_registry(True)):
            status, _, detail = self.last(diagnostics._reddit)
        self.assertEqual(status, "SKIP")
        self.assertIn("reddit_apify", detail)

    def test_the_apify_check_is_skipped_while_the_source_is_off(self):
        with patch("community.config.settings.settings", apify_registry(False)):
            status, _, detail = self.last(diagnostics._reddit_apify)
        self.assertEqual(status, "SKIP")
        self.assertIn("not enabled", detail)

    def test_the_apify_check_passes_or_fails_with_the_probe(self):
        with patch("community.config.settings.settings", apify_registry(True)), \
             patch.object(diagnostics, "_live_probe", return_value={"live": "ok", "detail": "x"}):
            self.assertEqual(self.last(diagnostics._reddit_apify)[0], "PASS")
        with patch("community.config.settings.settings", apify_registry(True)), \
             patch.object(diagnostics, "_live_probe", return_value={"live": "http_404"}):
            self.assertEqual(self.last(diagnostics._reddit_apify)[0], "FAIL")
        with patch("community.config.settings.settings", apify_registry(True)), \
             patch.object(diagnostics, "_live_probe", return_value={"live": "no_key"}):
            status, _, detail = self.last(diagnostics._reddit_apify)
        self.assertEqual(status, "FAIL")                     # enabled but no APIFY_TOKEN is a real gap here
        self.assertIn("APIFY_TOKEN", detail)

    def test_doctor_runs_the_new_check(self):
        import inspect
        self.assertIn("_reddit_apify", inspect.getsource(diagnostics.run_doctor))


# ── ./cm source reddit_apify --days N (backfill) ──────────────────────────

import runner  # noqa: E402


class SourceDaysFlagTests(unittest.TestCase):
    def run_source(self, registry, **kw):
        seen = {}

        def fake_lock(label, fn, job=None):
            fn()

        def fake_run(daily=False, only=None, **_):
            seen["window"] = (registry["sources"].get("reddit_apify") or {}).get("date_limit_days")
            return {"reddit_apify": {"enabled": True}}

        with patch.object(runner, "settings", SimpleNamespace(registry=registry)), \
             patch.object(runner, "_with_pipeline_lock", side_effect=fake_lock), \
             patch("community.scrape.extra_sources.run", side_effect=fake_run):
            runner.source("reddit_apify", **kw)
        return seen

    def test_days_widens_the_date_window_for_that_one_run_only(self):
        reg = {"sources": {"reddit_apify": {"enabled": True, "date_limit_days": 2}}}
        self.assertEqual(self.run_source(reg, days=14)["window"], 14)
        self.assertEqual(reg["sources"]["reddit_apify"]["date_limit_days"], 2)     # restored afterwards

    def test_without_days_the_registry_value_is_untouched(self):
        reg = {"sources": {"reddit_apify": {"enabled": True, "date_limit_days": 2}}}
        self.assertEqual(self.run_source(reg)["window"], 2)

    def test_a_missing_value_is_removed_again_after_the_run(self):
        reg = {"sources": {"reddit_apify": {"enabled": True}}}
        self.assertEqual(self.run_source(reg, days=7)["window"], 7)
        self.assertNotIn("date_limit_days", reg["sources"]["reddit_apify"])

    def test_the_registry_is_restored_even_if_the_run_blows_up(self):
        reg = {"sources": {"reddit_apify": {"enabled": True, "date_limit_days": 2}}}

        def boom(label, fn, job=None):
            fn()

        with patch.object(runner, "settings", SimpleNamespace(registry=reg)), \
             patch.object(runner, "_with_pipeline_lock", side_effect=boom), \
             patch("community.scrape.extra_sources.run", side_effect=RuntimeError("apify down")):
            with self.assertRaises(RuntimeError):
                runner.source("reddit_apify", days=30)
        self.assertEqual(reg["sources"]["reddit_apify"]["date_limit_days"], 2)

    def test_it_is_a_real_cli_option(self):
        from typer.testing import CliRunner
        with patch.object(runner, "source") as _:        # only the option parsing is under test
            pass
        out = CliRunner().invoke(runner.app, ["source", "--help"])
        self.assertIn("--days", out.output)


# ── per-subreddit post budgets and --posts ────────────────────────────────

class PostOverrideTests(unittest.TestCase):
    """One run per subreddit makes a per-subreddit post budget possible. Nightly 10-posts-per-sub captures
    only a slice of a very busy subreddit (the probe's busiest four all hit the cap)."""

    def total(self, subs, **reg):
        runs = reddit_apify.build_payloads({"actor": ACTOR, "max_posts_per_sub": 10, "comments_per_post": 5, **reg},
                                           subs, [])
        return runs[0][1]["maxPostsCount"]

    def test_a_busy_subreddit_gets_a_larger_budget(self):
        self.assertEqual(self.total(["IndianStockMarket"], post_overrides={"IndianStockMarket": 25}), 25)

    def test_names_match_without_regard_to_case(self):
        self.assertEqual(self.total(["IndianStockMarket"], post_overrides={"indianstockmarket": 25}), 25)

    def test_other_subreddits_keep_the_default(self):
        self.assertEqual(self.total(["Zerodha"], post_overrides={"IndianStockMarket": 25}), 10)

    def test_an_override_only_ever_raises_the_budget(self):
        self.assertEqual(self.total(["Zerodha"], post_overrides={"Zerodha": 5}), 10)
        self.assertEqual(self.total(["Zerodha"], max_posts_per_sub=100, post_overrides={"Zerodha": 25}), 100)

    def test_subreddits_sharing_a_run_add_up(self):
        self.assertEqual(self.total(["IndianStockMarket", "Zerodha"], post_overrides={"IndianStockMarket": 25}), 35)

    def test_the_worst_case_estimate_follows_the_budget(self):
        [(_, p)] = reddit_apify.build_payloads({"actor": ACTOR, "max_posts_per_sub": 10, "comments_per_post": 5,
                                                "post_overrides": {"IndianStockMarket": 25}}, ["IndianStockMarket"], [])
        self.assertEqual(reddit_apify.worst_case_items(p), 25 * 6)


class SourcePostsFlagTests(unittest.TestCase):
    def run_source(self, registry, **kw):
        seen = {}

        def fake_lock(label, fn, job=None):
            fn()

        def fake_run(daily=False, only=None, **_):
            block = registry["sources"].get("reddit_apify") or {}
            seen.update(days=block.get("date_limit_days"), posts=block.get("max_posts_per_sub"))
            return {"reddit_apify": {"enabled": True}}

        with patch.object(runner, "settings", SimpleNamespace(registry=registry)), \
             patch.object(runner, "_with_pipeline_lock", side_effect=fake_lock), \
             patch("community.scrape.extra_sources.run", side_effect=fake_run):
            runner.source("reddit_apify", **kw)
        return seen

    def test_posts_and_days_together_make_a_real_backfill_and_are_restored(self):
        reg = {"sources": {"reddit_apify": {"enabled": True, "date_limit_days": 2, "max_posts_per_sub": 10}}}
        seen = self.run_source(reg, days=14, posts=100)
        self.assertEqual((seen["days"], seen["posts"]), (14, 100))
        block = reg["sources"]["reddit_apify"]
        self.assertEqual((block["date_limit_days"], block["max_posts_per_sub"]), (2, 10))

    def test_posts_alone_leaves_the_window_alone(self):
        reg = {"sources": {"reddit_apify": {"enabled": True, "date_limit_days": 2}}}
        seen = self.run_source(reg, posts=50)
        self.assertEqual((seen["days"], seen["posts"]), (2, 50))
        self.assertNotIn("max_posts_per_sub", reg["sources"]["reddit_apify"])      # removed again

    def test_it_is_a_real_cli_option(self):
        from typer.testing import CliRunner
        out = CliRunner().invoke(runner.app, ["source", "--help"])
        self.assertIn("--posts", out.output)


# ── end to end: actor rows -> collector -> extra_sources storage -> state stamp ──

from community.scrape import extra_sources  # noqa: E402
from tests.test_reddit_apify_pro import AUTOMOD, REPLY  # noqa: E402


class EndToEndTests(unittest.TestCase):
    def nightly(self, rows, reg_extra=None, subs=CATS):
        fake_repo = MagicMock()
        fake_repo.upsert_author.return_value = 7
        fake_repo.insert_item_if_absent.return_value = 1
        fake_repo.content_hash.return_value = "h"
        reg = {"enabled": True, "actor": ACTOR, "cadence": "nightly", **(reg_extra or {})}
        with patch.object(reddit_apify, "_run_actor", side_effect=lambda *a, **k: list(rows)), \
             patch.object(reddit_apify, "_token", return_value="tok"), \
             patch.object(reddit_apify, "_subreddits", return_value=subs), \
             patch.object(reddit_apify, "_active_keywords", return_value=[]), \
             patch.object(extra_sources, "repo", fake_repo):
            counters = extra_sources._run_source("reddit_apify", reddit_apify.fetch, reg)
        return counters, fake_repo

    def test_rows_become_stored_items_and_the_source_state_is_stamped(self):
        counters, repo = self.nightly([POST, AUTOMOD, COMMENT, REPLY])
        stored = [c.args[0] for c in repo.insert_item_if_absent.call_args_list]
        # 2 subs -> 2 listing runs, each returning the same rows: the duplicates collapse before storage
        self.assertEqual(sorted((i["source"], i["source_type"], i["external_id"]) for i in stored),
                         [("reddit", "comment", "t1_pedy111"), ("reddit", "comment", "t1_pedy222"),
                          ("reddit", "post", "t3_1wzqkgr")])
        reply = next(i for i in stored if i["external_id"] == "t1_pedy222")
        self.assertEqual((reply["parent_id"], reply["thread_id"]), ("t1_pedy111", "t3_1wzqkgr"))
        self.assertEqual(reply["raw"]["via"], "apify_reddit_pro")
        self.assertEqual((counters["fetched"], counters["inserted"]), (3, 3))
        repo.advance_state.assert_called_once()
        self.assertEqual(repo.advance_state.call_args.args[:2], ("ingest", "reddit_apify"))
        self.assertNotIn("error", counters)

    def test_a_dead_actor_is_recorded_as_an_error_and_never_raises(self):
        fake_repo = MagicMock()
        with patch.object(reddit_apify, "_run_actor", side_effect=RuntimeError("apify down")), \
             patch.object(reddit_apify, "_token", return_value="tok"), \
             patch.object(reddit_apify, "_subreddits", return_value=CATS), \
             patch.object(reddit_apify, "_active_keywords", return_value=[]), \
             patch.object(extra_sources, "repo", fake_repo):
            counters = extra_sources._run_source("reddit_apify", reddit_apify.fetch, {"enabled": True, "actor": ACTOR})
        self.assertIn("every run failed", counters["error"])
        self.assertEqual(fake_repo.advance_state.call_args.args[:2], ("ingest", "reddit_apify"))
        self.assertIn("error", fake_repo.advance_state.call_args.kwargs)     # health/Source page see the failure

    def test_the_nightly_cadence_keeps_it_out_of_the_hourly_and_morning_runs(self):
        reg = {"sources": {"reddit_apify": {"enabled": True, "cadence": "nightly"}}}
        with patch.object(extra_sources, "settings", SimpleNamespace(registry=reg)),              patch("community.enrich.landscape_monitor.run_weekly", return_value={}):   # would touch the DB
            hourly = extra_sources.run(daily=False)
            morning = extra_sources.run(daily=True)
        self.assertIn("nightly", hourly["reddit_apify"]["skipped"])
        self.assertIn("nightly", morning["reddit_apify"]["skipped"])
