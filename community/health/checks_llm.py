# community/health/checks_llm.py
"""LLM key/credit checks and LLM usage sanity.

The Anthropic probe is the free count_tokens call (same as `./cm doctor`) and
the Apify probe is the free limits endpoint, both run at most hourly (the
watchdog fires every 20 minutes; the probe slot is minutes 0-19) — or on every
run while already critical so recovery is noticed. X exhaustion cannot be read from pipeline_state (ingest degrades every X
failure, 402 included, to a note and still stamps last_success_at), so it is
detected by its symptom: no new twitter item for hours while the scraper ran;
the watchdog never spends twitterapi.io credits. llm_usage only records calls that returned, so LLM
outages show up as failed stages / missing rows, not as error rows.
"""
from __future__ import annotations

import os
import statistics
from datetime import datetime, timedelta

import httpx

from community.config.log import IST
from community.config.settings import settings
from community.health.model import CRIT, OK, WARN, Result, owns
from community.store import db


def probe_due(cfg: dict, now: datetime, prev_level: str | None) -> bool:
    return bool(cfg.get("_force")) or prev_level == CRIT or now.astimezone(IST).minute < 20


def _count_tokens_probe() -> None:
    from community.llm.client import client
    # SDK defaults (600 s, 2 retries) could hang the watchdog for ~30 min while the API
    # is down and overlap the next */20 run: bound it hard.
    client().with_options(timeout=15.0, max_retries=0).messages.count_tokens(
        model=settings.enrich_model, messages=[{"role": "user", "content": "ping"}])


def _classify_llm_error(exc: Exception) -> Result:
    name, msg = type(exc).__name__, str(exc)
    if name in ("AuthenticationError", "PermissionDeniedError") or "credit balance" in msg.lower():
        return Result("anthropic_key", CRIT, f"{name}: {msg[:150]}",
                      "check the key and the credit balance in the Anthropic console")
    return Result("anthropic_key", WARN, f"probe failed ({name}: {msg[:100]}), treated as transient")


@owns("anthropic_key")
def check_anthropic_key(cfg: dict, now: datetime) -> list[Result]:
    prev = cfg.get("_prev", {}).get("anthropic_key")
    if not probe_due(cfg, now, prev.level if prev else None):
        return []
    if not settings.anthropic_api_key:
        return [Result("anthropic_key", CRIT, "ANTHROPIC_API_KEY is not set",
                       "enrichment and drafts cannot run without it")]
    try:
        _count_tokens_probe()
    except Exception as exc:  # noqa: BLE001 — classify instead of crashing the watchdog
        res = _classify_llm_error(exc)
        if res.level == WARN and prev is not None and prev.level == CRIT:
            # a flaky probe must not count toward resolving an open critical: carry it forward
            return [Result("anthropic_key", CRIT, prev.detail,
                           "the probe could not reach the API this run, so the earlier failure stands")]
        return [res]
    return [Result("anthropic_key", OK, "key valid")]


def _apify_usage() -> tuple[float, float] | None:
    token = os.getenv("APIFY_TOKEN")
    if not token:
        return None
    r = httpx.get("https://api.apify.com/v2/users/me/limits",
                  headers={"Authorization": f"Bearer {token}"}, timeout=12)
    r.raise_for_status()
    data = r.json().get("data", {})
    used = (data.get("current") or {}).get("monthlyUsageUsd")
    cap = (data.get("limits") or {}).get("maxMonthlyUsageUsd")
    return (float(used), float(cap)) if used is not None and cap else None


def _x_ingest_result(cfg: dict, now: datetime) -> Result:
    """credits:x: critical when the X scraper keeps running but no new tweet has arrived
    for `x_stalled_hours` (credits exhausted / 402, key invalid, or the API is down)."""
    row = db.one(
        "SELECT (SELECT last_success_at FROM pipeline_state "
        "        WHERE stage = 'ingest' AND source = 'twitter') AS ran, "
        "       (SELECT max(ingested_at) FROM social_items WHERE source = 'twitter' "
        "        AND ingested_at > now() - interval '3 days') AS newest")
    ran, newest = (row or {}).get("ran"), (row or {}).get("newest")
    if ran is None or (now - ran) > timedelta(hours=3):
        return Result("credits:x", OK, "scraper not running recently (see the job checks)")
    limit = cfg["credits"]["x_stalled_hours"]
    idle_h = None if newest is None else (now - newest).total_seconds() / 3600
    if idle_h is None or idle_h > limit:
        since = "in the last 3 days" if idle_h is None else f"for {idle_h:.0f} h"
        return Result("credits:x", CRIT, f"no new X items {since} although the scraper is running",
                      "twitterapi.io credits exhausted (402), key invalid or API down: "
                      "see the 'X live' lines in out/cron.log")
    return Result("credits:x", OK, f"newest X item arrived {idle_h:.0f} h ago")


@owns("credits:")
def check_credits(cfg: dict, now: datetime) -> list[Result]:
    results: list[Result] = []
    if "twitter" not in cfg["muted"]:
        results.append(_x_ingest_result(cfg, now))
    prev = cfg.get("_prev", {}).get("credits:apify")
    if probe_due(cfg, now, prev.level if prev else None):
        usage = _apify_usage()
        if usage:
            used, cap = usage
            pct = 100.0 * used / cap
            c = cfg["credits"]
            level = CRIT if pct >= c["apify_crit_pct"] else WARN if pct >= c["apify_warn_pct"] else OK
            results.append(Result("credits:apify", level,
                                  f"${used:.2f} of ${cap:.0f} Apify credits used this cycle ({pct:.0f}%)",
                                  "top up or raise the Apify monthly cap" if level != OK else ""))
    return results


@owns("llm:")
def check_llm_usage(cfg: dict, now: datetime) -> list[Result]:
    c = cfg["llm"]
    results: list[Result] = []
    calls = db.one("SELECT count(*) AS n FROM llm_usage WHERE ts > now() - (%s * interval '1 hour')",
                   (c["no_calls_hours"],))["n"]
    results.append(Result("llm:calls", OK if calls else WARN,
                          f"{calls} LLM calls in the last {c['no_calls_hours']} h" if calls
                          else f"no LLM calls recorded in the last {c['no_calls_hours']} h",
                          "" if calls else "enrichment/drafts may be down: check the anthropic_key check and out/cron.log"))
    daily = db.query(
        "SELECT (ts AT TIME ZONE 'Asia/Kolkata')::date AS d, coalesce(sum(cost_usd), 0) AS cost "
        "FROM llm_usage WHERE ts > now() - interval '10 days' GROUP BY 1 ORDER BY 1")
    spend = {r["d"]: float(r["cost"]) for r in daily}
    yesterday = now.astimezone(IST).date() - timedelta(days=1)
    prior = [spend[yesterday - timedelta(days=i)] for i in range(1, 8)
             if (yesterday - timedelta(days=i)) in spend]
    if yesterday in spend and prior:
        median = statistics.median(prior)
        limit = max(c["spend_floor_usd"], c["spend_multiple"] * median)
        results.append(Result("llm:spend", WARN if spend[yesterday] > limit else OK,
                              f"yesterday ${spend[yesterday]:.2f} vs typical ${median:.2f}"
                              f" (alert above ${limit:.2f})"))
    unpriced = db.one("SELECT count(*) AS n FROM llm_usage WHERE cost_usd IS NULL "
                      "AND ts > now() - interval '7 days'")["n"]
    results.append(Result("llm:unpriced", WARN if unpriced else OK,
                          f"{unpriced} calls in 7 days used a model missing from the price table"
                          if unpriced else "all recent calls were priced"))
    return results
