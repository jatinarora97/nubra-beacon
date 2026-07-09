"""Stage ③ ENRICH (LLD-02 §6) — tag topic/intent/entities + embeddings.

Transport (cost plan §2.1): chunks of 20 go through the Anthropic **Batch API**
at −50% with an SLA (registry enrich.batch_sla_minutes) → chunks the batch
didn't resolve fall back to the sync path (which carries the ≤2 validation
retries); `run(sync=True)` bypasses the Batch API entirely — used by the 06:00
morning build so the chain closes on time.

Flow: canonical items lacking enrichment → deterministic prefilter (rule +
vendored guardrails, no LLM) → Haiku chunks → schema-validated → keyword
fallback per failed chunk → embeddings (multilingual-e5-small) for everything
enriched non-noise. Watermark advances only after writes committed.
"""
from __future__ import annotations

from community.config.settings import settings
from community.llm import client as llm
from community.clean import prefilter
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


def _write_enriched(result, by_id: dict[str, dict]) -> int:
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
    return len(rows)


def _write_kw_fallback(batch: list[dict]) -> None:
    rows = []
    for b in batch:
        f = _kw_fallback(b["text"])
        rows.append((b["item_id"], b["ingested_at"], f["audience"], f["intent"],
                     f["topic_key"], f["sentiment"], db.jsonb(f["entities"]),
                     f["is_noise"], f["model"]))
    db.executemany(_INSERT, rows)


def _sync_chunk(chunk: list[dict], stats: dict) -> None:
    payload = [{"id": str(b["item_id"]), "source": b["source"],
                "text": b["text"][:1500], "thread_hint": b["thread_id"]}
               for b in chunk]
    by_id = {str(b["item_id"]): b for b in chunk}
    try:
        result, usage = llm.enrich_batch(payload)
        stats["llm_calls"] += usage["calls"]
        stats["tokens_in"] += usage["input_tokens"]
        stats["tokens_out"] += usage["output_tokens"]
        stats["llm_enriched"] += _write_enriched(result, by_id)
    except llm.EnrichError as err:
        print(f"[enrich] chunk failed → kw-fallback: {err}")
        stats["fallback_batches"] += 1
        _write_kw_fallback(chunk)


def run(sync: bool = False) -> dict:
    """sync=True bypasses the Batch API (morning build / manual runs that need
    immediate results at full price)."""
    seed_taxonomy()
    pending = _pending(LOCAL_MAX_ITEMS + 1)
    capped = len(pending) > LOCAL_MAX_ITEMS
    pending = pending[:LOCAL_MAX_ITEMS]
    if not pending:
        from community.enrich import embeddings
        healed = embeddings.embed_pending()  # self-heal any embedding backlog
        return {"pending": 0, "embedded": healed, "note": "nothing to enrich"}
    # process oldest→newest so the watermark story stays sane
    pending.reverse()

    stats = {"pending": len(pending), "prefiltered_noise": 0, "llm_enriched": 0,
             "llm_calls": 0, "fallback_batches": 0, "tokens_in": 0, "tokens_out": 0,
             "transport": "sync" if sync else "batch_api", "embedded": 0}
    if capped:
        stats["note"] = f"spend cap: only newest {LOCAL_MAX_ITEMS} enriched this run"

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

    chunks = [to_llm[i:i + BATCH_SIZE] for i in range(0, len(to_llm), BATCH_SIZE)]

    if sync or not chunks:
        for chunk in chunks:
            _sync_chunk(chunk, stats)
    else:
        cfg = settings.registry.get("enrich", {})
        payload_chunks = [
            [{"id": str(b["item_id"]), "source": b["source"],
              "text": b["text"][:1500], "thread_hint": b["thread_id"]} for b in chunk]
            for chunk in chunks
        ]
        try:
            results, usage = llm.enrich_via_batch_api(
                payload_chunks,
                sla_minutes=float(cfg.get("batch_sla_minutes", 25)),
                poll_seconds=float(cfg.get("poll_seconds", 20)),
            )
        except Exception as e:  # noqa: BLE001 — submit/poll blip must not kill the hour
            print(f"[enrich] batch API unavailable ({type(e).__name__}: {str(e)[:120]}) "
                  "— falling back to sync for this pass")
            stats["batch_fallback"] = f"{type(e).__name__}"
            results = {i: None for i in range(len(chunks))}  # every chunk → sync retry
            usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "batch_id": None}
        stats["llm_calls"] += usage["calls"]
        stats["tokens_in"] += usage["input_tokens"]
        stats["tokens_out"] += usage["output_tokens"]
        stats["batch_id"] = usage["batch_id"]
        resolved = 0
        for idx, chunk in enumerate(chunks):
            if results.get(idx) is not None:
                by_id = {str(b["item_id"]): b for b in chunk}
                stats["llm_enriched"] += _write_enriched(results[idx], by_id)
                resolved += 1
            else:  # SLA breach / errored / expired / invalid → sync retry
                _sync_chunk(chunk, stats)
        stats["batch_resolved_chunks"] = f"{resolved}/{len(chunks)}"

    from community.enrich import embeddings
    stats["embedded"] = embeddings.embed_pending()

    wm = max(p["ingested_at"] for p in pending)
    repo.advance_state("enrich", "", watermark=wm, items=len(pending))
    stats["watermark"] = wm.isoformat()
    # batch tokens bill at 50% (cost plan §2.1)
    rate = 0.5 if not sync else 1.0
    est = (stats["tokens_in"] / 1e6 * 1.0 + stats["tokens_out"] / 1e6 * 5.0) * rate
    stats["est_llm_usd"] = round(est, 3)
    print(f"[enrich] tokens in={stats['tokens_in']} out={stats['tokens_out']} "
          f"est ${stats['est_llm_usd']} ({stats['transport']})")
    return stats
