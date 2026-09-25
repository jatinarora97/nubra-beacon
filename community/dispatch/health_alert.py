"""Health digest — full-pipeline status pushed to Slack once a day.

Reuses the exact same per-source computation the /source-health API endpoint
and webapp page use (community.api.read_api.source_health) — one source of
truth for "is this collector working," two surfaces (pull: webapp page,
push: this digest). live=True adds a real reachability/auth probe per
source (~10-15s each, serial) — worth the cost once a day, not every hour.
"""
from __future__ import annotations

from datetime import datetime, timezone

from community.dispatch import slack

_LABELS = {
    "error": "ERROR",
    "needs_key": "NEEDS KEY",
    "enabled_not_run": "enabled, not run yet",
    "working": "working",
    "disabled": "disabled",
}
# needs-attention states first, healthy/disabled last
_ORDER = ["error", "needs_key", "enabled_not_run", "working", "disabled"]
_NEEDS_ATTENTION = {"error", "needs_key"}


def _ago(ts: datetime | None) -> str:
    if not ts:
        return "never"
    hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
    if hours < 1:
        return f"{max(int(hours * 60), 1)}m ago"
    if hours < 48:
        return f"{hours:.0f}h ago"
    return f"{hours / 24:.0f}d ago"


def _render(sources: list[dict], live_checked: bool) -> str:
    by_health: dict[str, list[dict]] = {}
    for s in sources:
        by_health.setdefault(s["health"], []).append(s)

    total = len(sources)
    attention = [s["name"] for h in _NEEDS_ATTENTION for s in by_health.get(h, [])]
    lines = [f"{total - len(attention)}/{total} sources healthy"
             + (f" — needs attention: {', '.join(attention)}" if attention else "")]
    if live_checked:
        lines.append("(live reachability probe included)")
    lines.append("")

    for health in _ORDER:
        rows = by_health.get(health, [])
        if not rows:
            continue
        lines.append(f"*{_LABELS[health]}*")
        for s in rows:
            bits = [f"last run {_ago(s['last_success_at'])}"]
            if s.get("items_last_run") is not None:
                bits.append(f"{s['items_last_run']} items last run")
            bits.append(f"{s['stored_items']} stored total")
            live = s.get("live")
            if live and live != "ok":
                bits.append(f"live probe: {live}")
            detail = ", ".join(bits)
            if health in _NEEDS_ATTENTION and s.get("last_error"):
                detail += f" — {s['last_error'][:150]}"
            lines.append(f"- {s['name']}: {detail}")
        lines.append("")

    return "\n".join(lines).rstrip()


def run(live: bool = True) -> dict:
    from community.api.read_api import source_health

    payload = source_health(live=live)
    sources = payload["sources"]
    markdown = _render(sources, payload["live_checked"])
    dispatch_result = slack.send(markdown, "Beacon pipeline health")
    return {
        "sources_checked": len(sources),
        "needs_attention": [s["name"] for s in sources if s["health"] in _NEEDS_ATTENTION],
        "dispatch": dispatch_result,
    }
