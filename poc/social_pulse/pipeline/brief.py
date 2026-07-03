"""Render the daily 'rising topics' brief (terminal + JSON for storage)."""
from __future__ import annotations

import json
from datetime import datetime, timezone


def render_terminal(ranked: list[dict], stats: dict) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = []
    lines.append("=" * 72)
    lines.append(f"  SOCIAL PULSE — Rising Topics Brief — {today}")
    lines.append("=" * 72)
    lines.append(f"  ingested={stats['ingested']}  unique={stats['unique']}  "
                 f"relevant={stats['relevant']}  topics={len(ranked)}")
    lines.append("")
    if not ranked:
        lines.append("  (no rising topics today)")
        return "\n".join(lines)

    for i, r in enumerate(ranked, 1):
        srcs = "+".join(r["sources"])
        spread_tag = f"  ⚡cross-source x{r['spread']}" if r["spread"] > 1 else ""
        lines.append(f"  {i}. {r['topic']}   [score {r['score']}]{spread_tag}")
        lines.append(f"     audience={r['audience']}  sentiment={r['sentiment']}  "
                     f"mentions={r['mentions']}  sources={srcs}  engagement={r['engagement']}")
        for ex in r["examples"]:
            quote = ex["text"].replace("\n", " ")
            lines.append(f"       · \"{quote}\"  ({ex['source']})")
        # suggested angle = simple heuristic the social team can edit
        angle = _suggest_angle(r)
        lines.append(f"     → post angle: {angle}")
        lines.append("")
    lines.append("=" * 72)
    return "\n".join(lines)


def _suggest_angle(r: dict) -> str:
    if r["sentiment"] == "negative" and r["audience"] in ("dev", "algo"):
        return f"Acknowledge the pain ('{r['topic']}') and share how we handle it / a tip."
    if r["audience"] in ("dev", "algo"):
        return f"Technical thread on '{r['topic']}' — code/how-to, position us as builder-friendly."
    return f"Explainer / poll on '{r['topic']}' to spark replies."


def to_payload(ranked: list[dict], stats: dict) -> dict:
    return {"date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "stats": stats, "topics": ranked}


def save_brief(con, payload: dict) -> None:
    con.execute(
        "INSERT OR REPLACE INTO briefs (brief_date, payload, created_at) VALUES (?,?,?)",
        (payload["date"], json.dumps(payload), datetime.now(timezone.utc).isoformat()),
    )
    con.commit()
