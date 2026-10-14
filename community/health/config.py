# community/health/config.py
"""Health settings: in-code DEFAULTS deep-merged with registry.yaml `health:`.

registry.yaml is bind-mounted from the prod VM and shadows the image copy, so a
release cannot rely on a new block being present there — everything the checks
need has a default here; the registry only overrides.
"""
from __future__ import annotations

import copy

from community.config.settings import settings

DEFAULTS: dict = {
    "remind_hours": 6,
    "resolve_after_ok": 2,
    "slack_webhook_env": "SLACK_ALERTS_WEBHOOK_URL",
    "fallback_to_default_webhook": False,   # SLACK_WEBHOOK_URL carries SSO approvals
    "muted": ["reddit"],                    # known broken (parked) — digest line only
    "lock_exempt_minutes": 180,             # a lock holder younger than this excuses a skipped slot
    "job_failing_runs": 2,
    "stage_failing_runs": 3,
    "digest_stale_hours": 26,               # daily digest not seen for this long => critical
    # Mirrors deploy/crontab.prod (IST). weekdays: Mon=0 .. Sun=6 (Saturday=5).
    # start_window_min: how late after the slot a run may START and still count
    #   (cron fires on the minute; keep it far below the slot interval).
    # grace_min: how long after the slot before "never started" is declared.
    # crit_after_missed: consecutive missed slots that make it critical.
    # max_run_min: a run still `running` longer than this is critical (job_slow).
    "jobs": {
        "run-local": {"hours": [0] + list(range(7, 24)), "minute": 0,
                      "start_window_min": 10, "grace_min": 15,
                      "crit_after_missed": 3, "max_run_min": 180},
        "morning-build": {"hours": [6], "minute": 0,   # must finish by ~07:30
                          "start_window_min": 10, "grace_min": 20,
                          "crit_after_missed": 1, "max_run_min": 90},
        "source:instagram": {"hours": [2], "minute": 0,
                             "start_window_min": 10, "grace_min": 20,
                             "crit_after_missed": 1, "max_run_min": 180},
        # Reddit via Apify: 01:00 IST (19:30 UTC). Expected only while sources.reddit_apify is
        # enabled, and only from its first run (see checks_jobs.check_jobs).
        "source:reddit_apify": {"hours": [1], "minute": 0,
                                "enabled_by": "reddit_apify", "since_first_run": True,
                                "start_window_min": 10, "grace_min": 20,
                                "crit_after_missed": 1, "max_run_min": 90},
        "stage:compose": {"hours": [10], "minute": 0, "weekdays": [5],
                          "start_window_min": 10, "grace_min": 15,
                          "crit_after_missed": 1, "max_run_min": 45},
        # dispatch is chained after compose with && in the crontab, so it starts
        # whenever compose finishes — give it a wide start window
        "stage:dispatch": {"hours": [10], "minute": 0, "weekdays": [5],
                           "start_window_min": 60, "grace_min": 65,
                           "crit_after_missed": 1, "max_run_min": 45},
    },
    "partitions": {
        "tables": ["social_items", "item_enrichment", "item_embeddings"],
        "crit_days": 10,
        "warn_days": 35,
    },
    "sources": {
        # registry source name -> pipeline_state.source (stage='ingest')
        "map": {"twitter": "twitter", "reddit": "reddit", "youtube": "youtube",
                "github": "github", "broker_communities": "community_forum",
                "app_reviews": "app_review", "instagram": "instagram",
                "linkedin": "linkedin", "reddit_apify": "reddit_apify"},
        "max_age_hours": {"twitter": 10, "reddit": 12, "default": 30},
        "volume_sources": ["twitter"],
        "volume_max_age_hours": 10,
    },
    "freshness": {
        "topics_after_ist": 8.0,          # hours, IST
        "daily_roundup_after_ist": 7.75,  # 07:45
        "weekly_roundup_after_ist": 11.0, # Saturday only
    },
    "enrichment_backlog_warn": 200,
    "llm": {"spend_multiple": 3.0, "spend_floor_usd": 1.0, "no_calls_hours": 24},
    "credits": {"apify_warn_pct": 80, "apify_crit_pct": 98,
                "x_stalled_hours": 12},   # no new X item this long while the scraper runs
    "resources": {
        "disk_warn_pct": 80, "disk_crit_pct": 90,
        "disk_eta_warn_days": 21, "disk_eta_crit_days": 7,
        "mem_warn_pct": 20, "mem_crit_pct": 10, "mem_crit_samples": 3,
        "load_warn_per_core": 2.0,
        # swap is judged with swap-in/out activity (pages/min), not by percentage alone
        "swap_active_warn_pct": 50, "swap_idle_warn_pct": 75, "swap_crit_pct": 90,
        "swap_active_pages_per_min": 1000,
        "cron_log_warn_mb": 500, "backup_warn_hours": 26, "backup_crit_hours": 36,
        "restart_crit_count": 2,
    },
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for key, value in (over or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            out[key] = _merge(base[key], value)
        else:
            out[key] = value
    return out


def load(registry: dict | None = None) -> dict:
    reg = settings.registry if registry is None else registry
    return copy.deepcopy(_merge(DEFAULTS, reg.get("health") or {}))
