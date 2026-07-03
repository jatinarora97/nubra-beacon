"""Stage ③ ENRICH (LLD-02 §6) — local mode: sync Haiku calls.

Prod difference (cost plan §2.1): batches go через the Anthropic Batch API at −50%,
except the 06:00 morning-build pass which stays sync. Local runs everything sync.

Flow: canonical items past the 'enrich' watermark (ingested_at, arrival clock) →
deterministic prefilter (rule + vendored guardrails, no LLM) → Haiku batches of 20,
schema-validated with ≤2 retries → keyword fallback per failed batch. Watermark
advances only past batches whose writes committed.
"""
from __future__ import annotations

from community.config.settings import settings
from community.llm import client as llm
from community.pipeline import prefilter
from community.reference.taxonomy import resolve_broker, seed_taxonomy
from community.store import db, repositories as repo

BATCH_SIZE = 20
LOCAL_MAX_ITEMS = 600  # local-mode spend cap; noted in ops stats when it bites

_INSERT = """
INSERT INTO item_enrichment (item_id, ingested_at, audience, intent, topic_key,
                             sentiment, entities, is_noise, model)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (item_id, ingested_at) DO NOTHING
"""


def _pending(limit: int) -> list[dict]:
    return db.query(
        """
        SELECT si.item_id, si.ingested_at, si.source, si.text, si.thread_id,
               a.handle AS author
        FROM social_items si
        JOIN authors a USING (author_id)
        LEFT JOIN item_enrichment ie ON ie.item_id = si.item_id
        WHERE si.duplicate_of IS NULL
          AND ie.item_id IS NULL
        ORDER BY si.ingested_at DESC
        LIMIT %s
        """,
        (limit,),
    )


_KW_COMPLAINT = ("not working", "down again", "issue", "problem", "stuck", "worst",
                 "refund", "loot", "pathetic", "hang ho", "band ho", "kharab")
_KW_FEATURE = ("wish", "should add", "please add", "why can't", "feature request",
               "would be great if", "add support")


def _kw_fallback(text: str) -> dict:
    low = (text or "").lower()
    if any(k in low for k in _KW_COMPLAINT):
        intent = "complaint"
    elif any(k in low for k in _KW_FEATURE):
        intent = "feature_request"
    elif "?" in low:
        intent = "question"
    else:
        intent = "news_opinion"
    return {"audience": None, "intent": intent, "topic_key": "other:unclassified",
            "sentiment": None, "entities": {}, "is_noise": False, "model": "kw-fallback"}


def run() -> dict:
    seed_taxonomy()
    pending = _pending(LOCAL_MAX_ITEMS + 1)
    capped = len(pending) > LOCAL_MAX_ITEMS
    pending = pending[:LOCAL_MAX_ITEMS]
    if not pending:
        return {"pending": 0, "note": "nothing to enrich"}
    # process oldest→newest so the watermark story stays sane
    pending.reverse()

    stats = {"pending": len(pending), "prefiltered_noise": 0, "llm_enriched": 0,
             "llm_calls": 0, "fallback_batches": 0,
             "tokens_in": 0, "tokens_out": 0}
    if capped:
        stats["note"] = f"local cap: only newest {LOCAL_MAX_ITEMS} enriched this run"

    to_llm: list[dict] = []
    for it in pending:
        noisy, tag, reason = prefilter.check(it["text"], it["author"])
        if noisy:
            db.execute(_INSERT, (it["item_id"], it["ingested_at"], None, "spam",
                                 "other:noise", None,
                                 db.jsonb({"noise_reason": reason}), True, tag))
            stats["prefiltered_noise"] += 1
        else:
            to_llm.append(it)

    for i in range(0, len(to_llm), BATCH_SIZE):
        batch = to_llm[i:i + BATCH_SIZE]
        payload = [{"id": str(b["item_id"]), "source": b["source"],
                    "text": b["text"][:1500], "thread_hint": b["thread_id"]}
                   for b in batch]
        by_id = {str(b["item_id"]): b for b in batch}
        try:
            result, usage = llm.enrich_batch(payload)
            stats["llm_calls"] += usage["calls"]
            stats["tokens_in"] += usage["input_tokens"]
            stats["tokens_out"] += usage["output_tokens"]
            rows = []
            for e in result.items:
                src = by_id[e.id]
                ents = e.entities.model_dump(exclude_none=True)
                if ents.get("broker"):
                    ents["broker"] = resolve_broker(ents["broker"]) or None
                    if ents["broker"] is None:
                        ents.pop("broker")
                rows.append((src["item_id"], src["ingested_at"], e.audience, e.intent,
                             e.topic_key, e.sentiment, db.jsonb(ents), e.is_noise,
                             settings.enrich_model))
            db.executemany(_INSERT, rows)
            stats["llm_enriched"] += len(rows)
        except llm.EnrichError as err:
            print(f"[enrich] batch failed → kw-fallback: {err}")
            stats["fallback_batches"] += 1
            rows = []
            for b in batch:
                f = _kw_fallback(b["text"])
                rows.append((b["item_id"], b["ingested_at"], f["audience"], f["intent"],
                             f["topic_key"], f["sentiment"], db.jsonb(f["entities"]),
                             f["is_noise"], f["model"]))
            db.executemany(_INSERT, rows)

    wm = max(p["ingested_at"] for p in pending)
    repo.advance_state("enrich", "", watermark=wm, items=len(pending))
    stats["watermark"] = wm.isoformat()
    est = stats["tokens_in"] / 1e6 * 1.0 + stats["tokens_out"] / 1e6 * 5.0
    stats["est_llm_usd"] = round(est, 3)
    print(f"[enrich] tokens in={stats['tokens_in']} out={stats['tokens_out']} "
          f"est ${stats['est_llm_usd']}")
    return stats
