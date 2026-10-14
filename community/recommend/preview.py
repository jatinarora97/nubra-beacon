"""Preview reply drafts on real threads WITHOUT saving anything.

Runs a prompt (the one the real draft stage would use for that source, or a prompt file you are trying) on a few
real suggested opportunities and shows the drafts together with what the real checks say about them: the
validator, the offline regex layer (L1) and, optionally, the LLM judge (L2). Nothing is written to
`opportunities` or `compliance_audit`; the only database write is the normal LLM-usage meter row that every
model call makes. See scripts/preview_reddit_drafts.py and docs/reply-drafting-context-2026-10-14.md.
"""
from __future__ import annotations

import json
import pathlib

from community.compose.render import strip_feature_refs
from community.config.settings import settings
from community.llm.client import complete
from community.recommend import compliance, draft
from community.store import db

DEFAULT_COUNT = 10      # what one hourly draft run handles (recommend.max_drafted); `--n` overrides it

_PICK = """
SELECT o.id, o.source, o.thread_id, o.priority, o.matched_insight, si.url, left(si.text, 160) AS title
FROM opportunities o
LEFT JOIN conversations c ON (c.source, c.thread_id) = (o.source, o.thread_id)
LEFT JOIN social_items si ON si.item_id = c.root_item_id
WHERE o.source = %s AND o.status = 'suggested' {extra}
ORDER BY o.day DESC, o.priority DESC LIMIT %s
"""


def pick(source: str = "reddit", limit: int = DEFAULT_COUNT, opp_id: int | None = None) -> list[dict]:
    if opp_id is None:
        return db.query(_PICK.format(extra=""), (source, limit))
    return db.query(_PICK.format(extra="AND o.id = %s"), (source, opp_id, limit))


def system_prompt(source: str, prompt_file: str | None = None) -> str:
    """The prompt the real stage uses for this source, or the text of a file being tried instead."""
    if prompt_file:
        text = pathlib.Path(prompt_file).read_text(encoding="utf-8")
        return text.replace("{DISCLOSURE}", draft.DISCLOSURE)
    return draft._system_for(source)


def preview_one(opp: dict, catalog: list[dict], system: str, judge: bool = False) -> dict:
    """One model call (no regeneration loop) plus the checks the real stage would apply."""
    valid_ids = {c["id"] for c in catalog}
    user = draft._user_message(opp, catalog)
    raw, _usage = complete(settings.draft_model, system, user, max_tokens=1200)
    try:
        data = draft._parse_json(raw)
    except (ValueError, json.JSONDecodeError):
        return {"opp": opp, "error": "the model's output was not valid JSON", "raw": raw[:400]}
    if data.get("skip_reason"):
        return {"opp": opp, "skipped": data["skip_reason"]}
    texts = {voice: (data.get(voice) or {}).get("text", "") for voice in ("brand", "rep")}
    result = {"opp": opp, "drafts": texts, "problems": draft._validate_drafts(data, valid_ids, opp["source"]),
              "l1": {voice: compliance.l1_check(text) for voice, text in texts.items() if text}}
    for voice in texts:
        result["l1"].setdefault(voice, [])
    if judge:
        result["l2"] = {voice: compliance.l2_check(text, f"{voice}_reply") for voice, text in texts.items() if text}
    return result


def render(results: list[dict], prompt_label: str) -> str:
    out = [f"PREVIEW ONLY - nothing was saved. Prompt: {prompt_label}", "=" * 72]
    for r in results:
        o = r["opp"]
        out.append(f"\n--- opportunity {o['id']} | priority {o['priority']} | {o.get('url') or 'no url'}")
        out.append(f"thread: {(o.get('title') or '').strip()}")
        if "error" in r:
            out.append(f"ERROR: {r['error']}\n{r.get('raw', '')}")
            continue
        if "skipped" in r:
            out.append(f"skipped: {r['skipped']}")
            continue
        out.append(f"\nBRAND:\n{strip_feature_refs(r['drafts']['brand'])}\n\n"
                   f"REP:\n{strip_feature_refs(r['drafts']['rep'])}\n")
        out.append("validator: " + ("OK" if not r["problems"] else "; ".join(r["problems"])))
        for voice in ("brand", "rep"):
            hits = r["l1"].get(voice) or []
            out.append(f"regex rules ({voice}): " + ("OK" if not hits else "; ".join(hits)))
        for voice, (ok, reasons) in (r.get("l2") or {}).items():
            out.append(f"judge ({voice}): " + ("pass" if ok else "FAIL - " + "; ".join(reasons)))
    return "\n".join(out)
