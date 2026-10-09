# tests/test_health_digest.py
from __future__ import annotations

import json
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import runner
from community.health import config, digest, engine, icons
from community.health.model import CRIT, OK, WARN, Result
from community.health.state import Row

NOW = datetime(2026, 10, 5, 2, 35, tzinfo=timezone.utc)  # 08:05 IST
CFG = config.load({})
CTX = {
    "jobs": [{"job": "run-local", "status": "ok", "started_at": NOW - timedelta(minutes=40),
              "finished_at": NOW - timedelta(minutes=30)}],
    "llm": {"day": date(2026, 10, 4), "calls": 143, "cost": 0.82},
    "resources": {"disk_used_pct": 63.2, "disk_free_gb": 41.0, "mem_available_pct": 54.0,
                  "load_per_core": 0.3, "db_size_gb": 2.14, "cron_log_mb": 12.0},
    "top_tables": [("social_items_y2026m09", 1_200_000_000)],
    "live": {"twitter": {"live": "ok"}},
}


class RenderTests(unittest.TestCase):
    def test_all_healthy_headline_mentions_muted_sources(self):
        text = digest.render([Result("a", OK, "fine"), Result("b", OK, "fine")], CTX, CFG, NOW)
        self.assertEqual(text.splitlines()[0],
                         f"{icons.HEALTHY} Overall: HEALTHY - all 2 checks healthy (muted, known broken: reddit)")

    def test_problems_come_first_with_counts_and_hints(self):
        results = [Result("ok1", OK, "fine"),
                   Result("partitions:social_items", WARN, "27 days left"),
                   Result("disk", CRIT, "93% used", "free space on the VM")]
        text = digest.render(results, CTX, CFG, NOW)
        self.assertEqual(text.splitlines()[0],
                         f"{icons.CRITICAL_STATUS} Overall: CRITICAL - 3 checks, 1 critical, 1 warnings (muted, known broken: reddit)")
        self.assertLess(text.index("*Critical*"), text.index("*Warnings*"))
        self.assertLess(text.index("*Warnings*"), text.index("*Jobs*"))
        self.assertIn("- disk: 93% used", text)
        self.assertIn("What to check: free space on the VM", text)

    def test_sections_show_jobs_llm_resources_and_sources(self):
        results = [Result("source:twitter", OK, "last success 1 h ago"),
                   Result("source_items:twitter", OK, "newest item arrived 1 h ago")]
        text = digest.render(results, CTX, CFG, NOW)
        self.assertIn(f"- {icons.OK} run-local: ok, last run 40 min ago", text)
        self.assertIn(f"- {icons.NONE} morning-build: no run recorded yet", text)
        self.assertIn("143 calls", text)
        self.assertIn("$0.82", text)
        self.assertIn("disk 63% used (41 GB free)", text)
        self.assertIn("database 2.1 GB", text)
        self.assertIn("social_items_y2026m09", text)
        self.assertIn(f"- {icons.OK} twitter: last success 1 h ago", text)
        self.assertIn("live probe ok", text)

    def test_section_headers_carry_their_icons(self):
        results = [Result("disk", CRIT, "93% used", "free space"), Result("backup", WARN, "27 h")]
        text = digest.render(results, {**CTX, "changes": {"new": [], "resolved": [], "unchanged": 0}},
                             CFG, NOW)
        for icon, header in ((icons.ACTIONS, "*Top actions*"), (icons.CRITICAL, "*Critical*"),
                             (icons.WARNING, "*Warnings*"), (icons.CHANGES, "*Changes since yesterday*"),
                             (icons.JOBS, "*Jobs*"), (icons.LLM, "*LLM*"), (icons.RESOURCES, "*Resources*")):
            self.assertIn(f"{icon} {header}", text)

    def test_job_and_source_lines_show_their_state_with_an_icon(self):
        ctx = {**CTX, "jobs": [
            {"job": "run-local", "status": "degraded", "started_at": NOW - timedelta(minutes=5), "finished_at": None},
            {"job": "morning-build", "status": "failed", "started_at": NOW - timedelta(hours=2), "finished_at": None},
            {"job": "source:instagram", "status": "running", "started_at": NOW - timedelta(minutes=1), "finished_at": None}]}
        results = [Result("source:youtube", WARN, "last successful run 40 h ago"),
                   Result("source:twitter", OK, "last success 1 h ago")]
        text = digest.render(results, ctx, CFG, NOW)
        self.assertIn(f"- {icons.WARNING} run-local: degraded", text)
        self.assertIn(f"- {icons.CRITICAL} morning-build: failed", text)
        self.assertIn(f"- {icons.RUNNING} source:instagram: running", text)
        self.assertIn(f"- {icons.WARNING} youtube: last successful run 40 h ago", text)
        self.assertIn(f"- {icons.OK} twitter: last success 1 h ago", text)

    def test_missing_context_pieces_do_not_crash(self):
        empty = {"jobs": [], "llm": {"day": date(2026, 10, 4), "calls": 0, "cost": 0.0},
                 "resources": {}, "top_tables": [], "live": {}}
        self.assertIn("Overall: HEALTHY", digest.render([], empty, CFG, NOW))


def snap(**levels):
    return dict(levels)


class OverallAndTopActionsTests(unittest.TestCase):
    def test_overall_status_follows_the_worst_check(self):
        self.assertEqual(digest.overall([Result("a", OK, "")]), "HEALTHY")
        self.assertEqual(digest.overall([Result("a", OK, ""), Result("b", WARN, "")]), "DEGRADED")
        self.assertEqual(digest.overall([Result("b", WARN, ""), Result("c", CRIT, "")]), "CRITICAL")

    def test_degraded_headline_when_there_are_only_warnings(self):
        text = digest.render([Result("backup", WARN, "26 h")], CTX, CFG, NOW)
        self.assertTrue(text.startswith(f"{icons.DEGRADED} Overall: DEGRADED - 1 checks, 0 critical, 1 warnings"))

    def test_top_actions_are_critical_first_then_warnings_by_priority_capped_at_three(self):
        results = [Result("swap", WARN, "69%"),
                   Result("partitions:social_items", WARN, "24 days left"),
                   Result("disk", CRIT, "93% used"),
                   Result("stage_recent:scrape", WARN, "10 failure(s)"),
                   Result("backup", WARN, "27 h"),
                   Result("fine", OK, "")]
        self.assertEqual([r.key for r in digest.top_actions(results)],
                         ["disk", "stage_recent:scrape", "partitions:social_items"])
        text = digest.render(results, CTX, CFG, NOW)
        block = text.split("*Top actions*")[1].split("*Critical*")[0]
        self.assertIn("1. disk: 93% used", block)
        self.assertIn("2. stage_recent:scrape: 10 failure(s)", block)
        self.assertIn("3. partitions:social_items: 24 days left", block)
        self.assertNotIn("swap", block)

    def test_no_top_actions_section_when_everything_is_healthy(self):
        self.assertNotIn("*Top actions*", digest.render([Result("a", OK, "")], CTX, CFG, NOW))


class ChangesSinceYesterdayTests(unittest.TestCase):
    def test_snapshot_keeps_only_open_issues(self):
        results = [Result("a", OK, ""), Result("b", WARN, ""), Result("c", CRIT, "")]
        self.assertEqual(digest.snapshot(results), {"b": "warn", "c": "crit"})

    def test_diff_reports_new_resolved_and_unchanged(self):
        prev = {"scrape": "warn", "swap": "warn", "disk": "warn"}
        results = [Result("scrape", WARN, ""), Result("disk", CRIT, ""), Result("backup", WARN, "")]
        diff = digest.diff_snapshot(prev, results)
        self.assertEqual(diff["new"], ["backup (warn)", "disk (crit)"])  # disk got worse
        self.assertEqual(diff["resolved"], ["swap"])
        self.assertEqual(diff["unchanged"], 1)

    def test_no_comparison_without_a_previous_snapshot(self):
        self.assertIsNone(digest.diff_snapshot(None, [Result("a", WARN, "")]))

    def test_snapshot_text_round_trips_and_tolerates_garbage(self):
        self.assertEqual(digest.parse_snapshot(json.dumps({"a": "warn"})), {"a": "warn"})
        for bad in (None, "", "not json", "[1, 2]"):
            self.assertIsNone(digest.parse_snapshot(bad))

    def test_changes_section_is_rendered_when_there_is_something_to_compare(self):
        ctx = {**CTX, "changes": {"new": ["scrape (warn)"], "resolved": ["swap"], "unchanged": 3}}
        text = digest.render([Result("scrape", WARN, "x")], ctx, CFG, NOW)
        block = text.split("*Changes since yesterday*")[1].split("*Jobs*")[0]
        self.assertIn("- New: scrape (warn)", block)
        self.assertIn("- Resolved: swap", block)
        self.assertIn("- Unchanged: 3 open issues", block)

    def test_no_changes_message_and_no_section_on_the_first_digest(self):
        quiet = {**CTX, "changes": {"new": [], "resolved": [], "unchanged": 2}}
        self.assertIn("- No changes (2 open issues)", digest.render([], quiet, CFG, NOW))
        self.assertNotIn("Changes since yesterday", digest.render([], CTX, CFG, NOW))


class TrendTests(unittest.TestCase):
    def test_resource_lines_say_how_each_value_moved_since_yesterday(self):
        ctx = {**CTX, "resources_prev": {"disk_used_pct": 61.0, "mem_available_pct": 60.0,
                                         "db_size_gb": 2.0, "swap_used_pct": 69.0},
               "resources": {**CTX["resources"], "swap_used_pct": 69.4}}
        text = digest.render([], ctx, CFG, NOW)
        self.assertIn("disk 63% used (41 GB free), up from 61% yesterday", text)
        self.assertIn("memory 54% available, down from 60% yesterday", text)
        self.assertIn("swap 69% in use, steady since yesterday", text)
        self.assertIn("database 2.1 GB, up 7% since yesterday", text)

    def test_no_trend_text_without_a_value_from_yesterday(self):
        text = digest.render([], CTX, CFG, NOW)
        self.assertIn("disk 63% used (41 GB free)", text)
        self.assertNotIn("yesterday", text.split("*Resources*")[1])

    def test_nearest_sample_to_24_hours_ago(self):
        hist = [(NOW - timedelta(hours=26), 1.0), (NOW - timedelta(hours=23.5), 2.0),
                (NOW - timedelta(hours=1), 3.0)]
        self.assertEqual(digest.nearest_previous(hist, NOW), 2.0)
        self.assertIsNone(digest.nearest_previous([(NOW - timedelta(hours=1), 3.0)], NOW))  # nothing near 24 h
        self.assertIsNone(digest.nearest_previous([], NOW))

    def test_llm_line_compares_with_the_seven_day_average(self):
        ctx = {**CTX, "llm": {"day": date(2026, 10, 4), "calls": 143, "cost": 0.82, "avg7": 0.64}}
        self.assertIn("143 calls, $0.82 (7-day average $0.64)", digest.render([], ctx, CFG, NOW))

    def test_llm_summary_takes_yesterday_and_averages_the_week_before(self):
        rows = [{"d": date(2026, 9, 27) + timedelta(days=i), "calls": 10, "cost": 2.0} for i in range(7)]
        rows += [{"d": date(2026, 10, 4), "calls": 143, "cost": 0.82}, {"d": date(2026, 10, 5), "calls": 1, "cost": 9.0}]
        out = digest.llm_summary(rows, date(2026, 10, 4))
        self.assertEqual((out["calls"], round(out["cost"], 2), out["avg7"]), (143, 0.82, 2.0))
        none = digest.llm_summary([], date(2026, 10, 4))
        self.assertEqual((none["calls"], none["cost"], none["avg7"]), (0, 0.0, None))


class PreviousDigestTests(unittest.TestCase):
    def test_footer_shows_when_the_last_digest_ran_and_whether_it_was_posted(self):
        ctx = {**CTX, "prev_digest": {"last_seen": NOW - timedelta(hours=24), "detail": "posted=sent"}}
        text = digest.render([], ctx, CFG, NOW)
        self.assertIn("Previous digest: 04 Oct 08:05 IST (posted=sent)", text)

    def test_footer_says_so_on_the_first_digest(self):
        self.assertIn("Previous digest: none recorded", digest.render([], CTX, CFG, NOW))


class LiveResultsTests(unittest.TestCase):
    def test_only_real_probe_problems_become_warnings(self):
        ctx = {"live": {"twitter": {"live": "ok"}, "youtube": {"live": "http_403"},
                        "instagram": {"live": "no_key"}, "reddit": {"live": "blocked_or_down"},
                        "app_reviews": {"live": "no_probe"}}}
        res = {r.key: r for r in digest.live_results(ctx)}
        self.assertEqual(sorted(res), ["live_probe:instagram", "live_probe:reddit",
                                       "live_probe:youtube"])
        self.assertTrue(all(r.level == WARN for r in res.values()))
        self.assertIn("API key is not set", res["live_probe:instagram"].detail)
        self.assertIn("http_403", res["live_probe:youtube"].detail)


class RunDigestTests(unittest.TestCase):
    def setUp(self):
        self.saved: list[Row] = []
        self.seen_cfg: dict = {}

        def capture_cfg(cfg, now):
            self.seen_cfg.update(cfg)
            return []
        capture_cfg.PREFIXES = ()
        self.capture_cfg = capture_cfg
        for p in (patch.object(engine, "_db_up", return_value=True),
                  patch.object(engine.state, "load_states", return_value={}),
                  patch.object(engine.state, "save", side_effect=self.saved.append),
                  patch.object(engine.digest, "collect_context", return_value=CTX),
                  patch.object(engine, "CRITICAL_CHECKS", [engine.checks_jobs.check_watchdog_heartbeat]),
                  patch.object(engine, "DIGEST_ONLY_CHECKS", [])):
            p.start()
            self.addCleanup(p.stop)

    def test_posts_the_rendered_message_and_saves_its_heartbeat_and_snapshot(self):
        with patch.object(engine.notify, "post", return_value="sent") as post:
            summary = engine.run_digest(now=NOW)
        post.assert_called_once()
        self.assertTrue(post.call_args.args[0].startswith(f"{icons.DEGRADED} Overall:"))
        self.assertTrue(post.call_args.args[1].startswith(icons.DIGEST))  # the Slack subject line
        self.assertEqual(summary["posted"], "sent")
        self.assertEqual(sorted(r.key for r in self.saved), ["digest_heartbeat", "digest_snapshot"])

    def test_heartbeat_records_what_happened_and_the_snapshot_records_open_issues(self):
        with patch.object(engine.notify, "post", return_value="sent"):
            engine.run_digest(now=NOW)
        rows = {r.key: r for r in self.saved}
        self.assertEqual(rows["digest_heartbeat"].detail, "posted=sent; critical=0; warnings=1")
        self.assertEqual(json.loads(rows["digest_snapshot"].detail), {"watchdog_heartbeat": "warn"})

    def test_changes_are_computed_against_the_previous_snapshot(self):
        prev = {"digest_snapshot": Row("digest_snapshot", "ok", json.dumps({"old_issue": "warn"}), NOW, NOW),
                "digest_heartbeat": Row("digest_heartbeat", "ok", "posted=sent", NOW, NOW - timedelta(hours=24))}
        engine.state.load_states.return_value = prev
        with patch.object(engine.notify, "post", return_value="sent") as post:
            engine.run_digest(now=NOW)
        text = post.call_args.args[0]
        self.assertIn("- New: watchdog_heartbeat (warn)", text)
        self.assertIn("- Resolved: old_issue", text)
        self.assertIn("Previous digest: 04 Oct 08:05 IST (posted=sent)", text)

    def test_first_digest_has_no_changes_section(self):
        with patch.object(engine.notify, "post", return_value="sent") as post:
            engine.run_digest(now=NOW)
        self.assertNotIn("Changes since yesterday", post.call_args.args[0])
        self.assertIn("Previous digest: none recorded", post.call_args.args[0])

    def test_dry_run_returns_the_text_and_saves_nothing(self):
        summary = engine.run_digest(dry_run=True, now=NOW)
        self.assertEqual(summary["posted"], "dry-run")
        self.assertIn("Overall:", summary["text"])
        self.assertEqual(self.saved, [])

    def test_probes_are_forced_so_the_hourly_gate_is_bypassed(self):
        with patch.object(engine, "CRITICAL_CHECKS", [self.capture_cfg]), \
             patch.object(engine.notify, "post", return_value="sent"):
            engine.run_digest(now=NOW)
        self.assertTrue(self.seen_cfg["_force"])

    def test_live_probe_failures_appear_as_warnings(self):
        ctx = {**CTX, "live": {"youtube": {"live": "http_403"}}}
        with patch.object(engine.digest, "collect_context", return_value=ctx), \
             patch.object(engine.notify, "post", return_value="sent") as post:
            engine.run_digest(now=NOW)
        self.assertIn("live_probe:youtube", post.call_args.args[0])

    def test_database_down_sends_a_short_critical_instead_of_crashing(self):
        engine._db_up.return_value = False
        with patch.object(engine.notify, "post", return_value="sent") as post:
            summary = engine.run_digest(now=NOW)
        self.assertTrue(summary["db_unreachable"])
        self.assertIn("could not run", post.call_args.args[0])


class DigestCommandTests(unittest.TestCase):
    def test_dry_run_prints_the_text_then_a_summary(self):
        summary = {"checks": 3, "critical": [], "warnings": [], "posted": "dry-run", "text": "Beacon health: ok"}
        with patch("community.health.engine.run_digest", return_value=summary) as run, \
             patch.object(runner.typer, "echo") as echo:
            runner.health_digest(dry_run=True, no_live=True)
        run.assert_called_once_with(dry_run=True, live=False)
        self.assertEqual(echo.call_args_list[0].args[0], "Beacon health: ok")
        self.assertNotIn("Beacon health: ok", echo.call_args_list[1].args[0])

    def test_dry_run_survives_a_console_that_cannot_print_emoji(self):
        # a legacy Windows console (cp1252) raises UnicodeEncodeError on emoji
        summary = {"checks": 1, "critical": [], "warnings": [], "posted": "dry-run",
                   "text": f"{icons.DEGRADED} Overall: DEGRADED"}
        boom = UnicodeEncodeError("charmap", "x", 0, 1, "cannot encode")
        with patch("community.health.engine.run_digest", return_value=summary), \
             patch.object(runner.typer, "echo", side_effect=[boom, None, None]) as echo:
            runner.health_digest(dry_run=True, no_live=True)
        fallback = echo.call_args_list[1].args[0]
        self.assertTrue(fallback.isascii())
        self.assertIn("Overall: DEGRADED", fallback)

    def test_unexpected_exception_exits_one(self):
        with patch("community.health.engine.run_digest", side_effect=RuntimeError("x")):
            with self.assertRaises(SystemExit) as ctx:
                runner.health_digest(dry_run=False, no_live=False)
        self.assertEqual(ctx.exception.code, 1)
