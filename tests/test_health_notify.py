# tests/test_health_notify.py
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from community.dispatch import slack
from community.health import notify
from community.health.model import CRIT, Result

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
CFG = {"slack_webhook_env": "SLACK_ALERTS_WEBHOOK_URL", "fallback_to_default_webhook": False}


def _settings(mode="prod"):
    return SimpleNamespace(mode=mode, registry={"delivery": {}})


class FormatTests(unittest.TestCase):
    def test_alert_has_tag_key_detail_and_hint(self):
        text = notify.fmt_alert(Result("disk", CRIT, "93% used", "free space on the VM"))
        self.assertTrue(text.startswith("[CRITICAL] disk: 93% used"))
        self.assertIn("What to check: free space on the VM", text)

    def test_alert_without_hint_is_one_line(self):
        self.assertNotIn("\n", notify.fmt_alert(Result("disk", CRIT, "93% used")))

    def test_messages_are_emoji_free_ascii(self):
        for text in (notify.fmt_alert(Result("a", CRIT, "d", "h")),
                     notify.fmt_remind(Result("a", CRIT, "d"), NOW - timedelta(hours=7), NOW),
                     notify.fmt_resolved("a", NOW - timedelta(minutes=45), NOW)):
            self.assertTrue(all(ord(c) < 128 for c in text), text)

    def test_remind_says_still_failing_with_duration(self):
        text = notify.fmt_remind(Result("a", CRIT, "d"), NOW - timedelta(hours=7), NOW)
        self.assertIn("still failing", text)
        self.assertIn("7 h", text)

    def test_resolved_reports_how_long(self):
        self.assertEqual(notify.fmt_resolved("a", NOW - timedelta(minutes=45), NOW),
                         "[RESOLVED] a (was critical for 45 min)")


class PostTests(unittest.TestCase):
    def test_alerts_webhook_is_used_when_configured(self):
        with patch.dict(os.environ, {"SLACK_ALERTS_WEBHOOK_URL": "https://x"}), \
             patch("community.health.notify.slack.send", return_value="sent") as send:
            self.assertEqual(notify.post("t", "s", CFG), "sent")
        send.assert_called_once_with("t", "s", webhook_env="SLACK_ALERTS_WEBHOOK_URL")

    def test_no_alerts_webhook_and_no_fallback_skips_without_touching_slack(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch("community.health.notify.slack.send") as send:
            self.assertEqual(notify.post("t", "s", CFG), "skipped (no alerts webhook)")
        send.assert_not_called()

    def test_fallback_uses_the_default_webhook_only_when_enabled(self):
        cfg = {**CFG, "fallback_to_default_webhook": True}
        with patch.dict(os.environ, {}, clear=True), \
             patch("community.health.notify.slack.send", return_value="sent") as send:
            notify.post("t", "s", cfg)
        send.assert_called_once_with("t", "s")

    def test_dry_run_never_sends(self):
        with patch.dict(os.environ, {"SLACK_ALERTS_WEBHOOK_URL": "https://x"}), \
             patch("community.health.notify.slack.send") as send:
            self.assertEqual(notify.post("t", "s", CFG, dry_run=True), "dry-run")
        send.assert_not_called()


class SlackSendWebhookTests(unittest.TestCase):
    def _send(self, env, **kw):
        with patch.dict(os.environ, env, clear=True), \
             patch("community.config.settings.settings", _settings()), \
             patch.object(slack, "settings", _settings()), \
             patch.object(slack.httpx, "post") as post:
            result = slack.send("hello", "Subject", **kw)
        return result, post

    def test_default_webhook_behaviour_is_unchanged(self):
        result, post = self._send({"SLACK_WEBHOOK_URL": "https://hooks.test/default"})
        self.assertEqual(result, "sent")
        self.assertEqual(post.call_args.args[0], "https://hooks.test/default")

    def test_override_env_selects_the_alternate_webhook(self):
        result, post = self._send({"SLACK_WEBHOOK_URL": "https://hooks.test/default",
                                   "SLACK_ALERTS_WEBHOOK_URL": "https://hooks.test/alerts"},
                                  webhook_env="SLACK_ALERTS_WEBHOOK_URL")
        self.assertEqual(result, "sent")
        self.assertEqual(post.call_args.args[0], "https://hooks.test/alerts")

    def test_override_env_that_is_unset_skips_and_never_falls_back(self):
        result, post = self._send({"SLACK_WEBHOOK_URL": "https://hooks.test/default"},
                                  webhook_env="SLACK_ALERTS_WEBHOOK_URL")
        self.assertEqual(result, "skipped (no creds)")
        post.assert_not_called()

    def test_a_failed_post_never_leaks_the_webhook_url_into_the_result(self):
        # httpx puts the full request URL in HTTPStatusError's message, and the
        # watchdog/digest print this status into out/cron.log
        url = "https://hooks.slack.com/services/T000/B000/SECRETTOKEN"
        with patch.dict(os.environ, {"SLACK_ALERTS_WEBHOOK_URL": url}, clear=True),              patch("community.config.settings.settings", _settings()),              patch.object(slack, "settings", _settings()),              patch.object(slack.httpx, "post",
                          return_value=slack.httpx.Response(404, request=slack.httpx.Request("POST", url))):
            result = slack.send("hello", "S", webhook_env="SLACK_ALERTS_WEBHOOK_URL")
        self.assertTrue(result.startswith("error: HTTPStatusError"), result)
        self.assertNotIn("SECRETTOKEN", result)
        self.assertNotIn("hooks.slack.com", result)

    def test_local_mode_still_never_posts(self):
        with patch.dict(os.environ, {"SLACK_ALERTS_WEBHOOK_URL": "https://x"}, clear=True), \
             patch("community.config.settings.settings", _settings("local")), \
             patch.object(slack.httpx, "post") as post:
            result = slack.send("hello", "S", webhook_env="SLACK_ALERTS_WEBHOOK_URL")
        self.assertIn("skipped (local mode", result)
        post.assert_not_called()
