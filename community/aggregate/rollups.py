"""Stage ④ AGGREGATE (LLD-02 §8) — conversations, topic_daily, issue/feature
rollups, author_stats. Consumes item_enrichment past the 'aggregate' watermark
(enriched_at — arrival clock).

LOCAL-MODE SIMPLIFICATION (documented deviation): embeddings are skipped, so
feature_key assignment is exact-slug matching on canonical_label instead of the
LLD-02 §8.4 centroid nearest-neighbour (τ=0.80). feature_keys.centroid stays NULL;
prod swaps the matcher without schema change.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from community.reference.taxonomy import TOPICS, seed_taxonomy
from community.store import db, repositories as repo


# ── helpers ───────────────────────────────────────────────────────────────

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")[:60]


def _new_enrichment(wm: datetime | None) -> list[dict]:
    return db.query(
        """
        SELECT ie.item_id, ie.ingested_at, ie.audience, ie.intent, ie.topic_key,
               ie.sentiment, ie.entities, ie.is_noise, ie.enriched_at,
               si.source, si.thread_id, si.created_at, si.author_id,
               (si.engagement->>'score')::float AS score,
               COALESCE((si.engagement->'native'->>'views')::bigint, 0)  AS views,
               a.followers, a.account_created_at
        FROM item_enrichment ie
        JOIN social_items si ON si.item_id = ie.item_id
        JOIN authors a ON a.author_id = si.author_id
        WHERE (%s::timestamptz IS NULL OR ie.enriched_at > %s)
        ORDER BY ie.enriched_at
        """,
        (wm, wm),
    )


# ── conversations ─────────────────────────────────────────────────────────

def _rebuild_conversations(threads: set[tuple[str, str]]) -> int:
    now = datetime.now(timezone.utc)
    n = 0
    for source, thread_id in threads:
        items = db.query(
            """
            SELECT si.item_id, si.created_at, si.author_id, si.duplicate_of,
                   (si.engagement->>'score')::float AS score,
                   ie.topic_key, ie.is_noise, ie.entities
            FROM social_items si
            LEFT JOIN item_enrichment ie ON ie.item_id = si.item_id
            WHERE si.source = %s AND si.thread_id = %s
            """,
            (source, thread_id),
        )
        if not items:
            continue
        canonical = [i for i in items if i["duplicate_of"] is None]
        last3h = [i for i in canonical if i["created_at"] > now - timedelta(hours=3)]
        prior3h = [i for i in canonical
                   if now - timedelta(hours=6) < i["created_at"] <= now - timedelta(hours=3)]
        velocity = len(last3h) / max(len(prior3h), 1)
        topics = Counter(i["topic_key"] for i in canonical
                         if i["topic_key"] and not i["is_noise"])
        dominant = topics.most_common(1)[0][0] if topics else None
        nubra = any((i["entities"] or {}).get("broker") == "nubra" for i in items)
        root = min(canonical or items, key=lambda i: i["created_at"])
        peak = max((i["score"] or 0) for i in items)  # incl. dup credit
        db.execute(
            """
            INSERT INTO conversations (source, thread_id, root_item_id, item_count,
                participant_count, velocity, peak_engagement, dominant_topic_key,
                is_nubra_watch, first_seen, last_seen)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (source, thread_id) DO UPDATE SET
                root_item_id = EXCLUDED.root_item_id,
                item_count = EXCLUDED.item_count,
                participant_count = EXCLUDED.participant_count,
                velocity = EXCLUDED.velocity,
                peak_engagement = EXCLUDED.peak_engagement,
                dominant_topic_key = EXCLUDED.dominant_topic_key,
                is_nubra_watch = EXCLUDED.is_nubra_watch,
                first_seen = LEAST(conversations.first_seen, EXCLUDED.first_seen),
                last_seen = GREATEST(conversations.last_seen, EXCLUDED.last_seen)
                -- headsup_at deliberately untouched (owned by the heads-up sender)
            """,
            (source, thread_id, root["item_id"], len(canonical),
             len({i["author_id"] for i in items}), velocity, int(peak * 100),
             dominant, nubra,
             min(i["created_at"] for i in items), max(i["created_at"] for i in items)),
        )
        n += 1
    return n


# ── topic_daily ───────────────────────────────────────────────────────────

def _recompute_topic_days(days: set) -> tuple[int, int]:
    """Full recompute per touched day (idempotent). UPSERT never touches
    headsup_at / headsup_count — the heads-up sender owns those."""
    rising = 0
    for day in sorted(days):
        rows = db.query(
            """
            WITH canon AS (
                SELECT ie.topic_key, ie.audience, si.source, si.item_id,
                       (si.engagement->>'score')::float AS score
                FROM item_enrichment ie
                JOIN social_items si ON si.item_id = ie.item_id
                WHERE NOT ie.is_noise AND si.duplicate_of IS NULL
                  AND si.created_at::date = %s
            ),
            dup_credit AS (
                SELECT c.topic_key, COALESCE(SUM((d.engagement->>'score')::float),0) AS dscore
                FROM canon c
                JOIN social_items d ON d.duplicate_of = c.item_id
                GROUP BY c.topic_key
            )
            SELECT c.topic_key,
                   COUNT(*) AS cnt,
                   COUNT(DISTINCT c.source) FILTER (WHERE TRUE) AS srcs,
                   SUM(c.score) + COALESCE(MAX(dc.dscore), 0) AS eng,
                   jsonb_object_agg(COALESCE(c.audience,'other'), 1) AS _dummy
            FROM canon c LEFT JOIN dup_credit dc USING (topic_key)
            GROUP BY c.topic_key
            """,
            (day,),
        )
        # audience mix needs shares — compute per topic in python (jsonb_object_agg
        # above can't sum shares); refetch audiences per topic for the day
        aud_rows = db.query(
            """
            SELECT ie.topic_key, COALESCE(ie.audience,'other') AS aud, COUNT(*) AS n
            FROM item_enrichment ie JOIN social_items si ON si.item_id = ie.item_id
            WHERE NOT ie.is_noise AND si.duplicate_of IS NULL AND si.created_at::date = %s
            GROUP BY 1, 2
            """,
            (day,),
        )
        mix: dict[str, dict[str, int]] = defaultdict(dict)
        for r in aud_rows:
            mix[r["topic_key"]][r["aud"]] = r["n"]
        for r in rows:
            total = sum(mix[r["topic_key"]].values()) or 1
            audience_mix = {k: round(v / total, 2) for k, v in mix[r["topic_key"]].items()}
            hist = db.query(
                """
                SELECT count FROM topic_daily
                WHERE topic_key = %s AND day BETWEEN %s::date - 7 AND %s::date - 1
                """,
                (r["topic_key"], day, day),
            )
            vz = None
            if len(hist) >= 7:
                counts = [h["count"] for h in hist]
                mean = sum(counts) / len(counts)
                std = (sum((c - mean) ** 2 for c in counts) / len(counts)) ** 0.5
                vz = (r["cnt"] - mean) / (std + 1)
                if vz >= 1.5:
                    rising += 1
            db.execute(
                """
                INSERT INTO topic_daily (topic_key, day, count, velocity_z, spread,
                                         engagement_sum, audience_mix)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (topic_key, day) DO UPDATE SET
                    count = EXCLUDED.count, velocity_z = EXCLUDED.velocity_z,
                    spread = EXCLUDED.spread, engagement_sum = EXCLUDED.engagement_sum,
                    audience_mix = EXCLUDED.audience_mix
                    -- headsup_at / headsup_count deliberately untouched
                """,
                (r["topic_key"], day, r["cnt"], vz, r["srcs"],
                 int(r["eng"] or 0), db.jsonb(audience_mix)),
            )
    return len(days), rising


# ── issue_rollup ──────────────────────────────────────────────────────────

def _rollup_issues(rows: list[dict]) -> int:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        ents = r["entities"] or {}
        broker = ents.get("broker")
        if r["intent"] == "complaint" and broker and not r["is_noise"]:
            issue_key = ents.get("issue_type") or "support"
            groups[(broker, issue_key, r["created_at"].date())].append(r)
    for (broker, issue_key, day), items in groups.items():
        sentiments = [i["sentiment"] for i in items if i["sentiment"] is not None]
        neg_share = (sum(1 for s in sentiments if s < -0.3) / len(sentiments)) if sentiments else 0
        reach = sum(max(i["followers"] or 0, i["views"] or 0) for i in items)
        severity = math.log1p(reach) * neg_share
        samples = [i["item_id"] for i in
                   sorted(items, key=lambda x: -(x["score"] or 0))[:5]]
        db.execute(
            """
            INSERT INTO issue_rollup (broker, issue_key, day, count, severity,
                                      sentiment_avg, sample_item_ids)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (broker, issue_key, day) DO UPDATE SET
                count = issue_rollup.count + EXCLUDED.count,
                severity = GREATEST(issue_rollup.severity, EXCLUDED.severity),
                sentiment_avg = (COALESCE(issue_rollup.sentiment_avg,0) + COALESCE(EXCLUDED.sentiment_avg,0)) / 2,
                sample_item_ids = (SELECT ARRAY(SELECT DISTINCT unnest(issue_rollup.sample_item_ids || EXCLUDED.sample_item_ids) LIMIT 5))
            """,
            (broker, issue_key, day, len(items), severity,
             sum(sentiments) / len(sentiments) if sentiments else None, samples),
        )
    return len(groups)


# ── feature_rollup + feature_keys (slug fallback — see module docstring) ─

def _feature_key_for(phrase: str) -> str:
    slug = _slug(phrase)
    if not slug:
        slug = "unspecified"
    existing = db.query("SELECT feature_key, canonical_label FROM feature_keys")
    for row in existing:
        if _slug(row["canonical_label"]) == slug:
            db.execute(
                "UPDATE feature_keys SET phrase_count = phrase_count + 1, updated_at = now() "
                "WHERE feature_key = %s", (row["feature_key"],))
            return row["feature_key"]
    key = f"feat_{len(existing) + 1:05d}"
    db.execute(
        "INSERT INTO feature_keys (feature_key, canonical_label) VALUES (%s, %s) "
        "ON CONFLICT (feature_key) DO NOTHING",
        (key, phrase[:120]),
    )
    return key


def _rollup_features(rows: list[dict]) -> int:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        ents = r["entities"] or {}
        phrase = ents.get("feature_phrase")
        if r["intent"] == "feature_request" and phrase and not r["is_noise"]:
            key = _feature_key_for(phrase)
            groups[(key, phrase, r["created_at"].date())].append(r)
    for (key, phrase, day), items in groups.items():
        brokers = sorted({(i["entities"] or {}).get("broker") for i in items
                          if (i["entities"] or {}).get("broker")})
        samples = [i["item_id"] for i in items[:5]]
        db.execute(
            """
            INSERT INTO feature_rollup (feature_key, day, canonical_label, count,
                                        brokers_mentioned, sample_item_ids)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (feature_key, day) DO UPDATE SET
                count = feature_rollup.count + EXCLUDED.count,
                brokers_mentioned = (SELECT ARRAY(SELECT DISTINCT unnest(feature_rollup.brokers_mentioned || EXCLUDED.brokers_mentioned))),
                sample_item_ids = (SELECT ARRAY(SELECT DISTINCT unnest(feature_rollup.sample_item_ids || EXCLUDED.sample_item_ids) LIMIT 5))
            """,
            (key, day, phrase[:120], len(items), brokers, samples),
        )
    return len(groups)


# ── author_stats ──────────────────────────────────────────────────────────

def _score_authors(author_ids: set[int]) -> int:
    now = datetime.now(timezone.utc)
    taxonomy = set(TOPICS)
    for aid in author_ids:
        rows = db.query(
            """
            SELECT ie.topic_key, ie.is_noise, si.created_at::date AS day,
                   (si.engagement->>'score')::float AS score
            FROM social_items si
            LEFT JOIN item_enrichment ie ON ie.item_id = si.item_id
            WHERE si.author_id = %s AND si.created_at > %s - interval '30 days'
            """,
            (aid, now),
        )
        if not rows:
            continue
        enriched = [r for r in rows if r["topic_key"] is not None]
        relevant = [r for r in enriched if not r["is_noise"] and r["topic_key"] in taxonomy]
        relevance = len(relevant) / len(enriched) if enriched else 0
        consistency = len({r["day"] for r in rows}) / 30
        breadth = min(len({r["topic_key"] for r in relevant}), 8) / 8
        voice = 100 * (0.4 * relevance + 0.3 * consistency + 0.3 * breadth)
        author = db.one("SELECT followers, account_created_at FROM authors WHERE author_id=%s", (aid,))
        avg_score = sum(r["score"] or 0 for r in rows) / len(rows)
        flag = bool(
            ((author["followers"] or 0) > 10000 and avg_score < 1.0)
            or (author["account_created_at"] and
                (now - author["account_created_at"]).days < 90)
        )
        db.execute(
            """
            INSERT INTO author_stats (author_id, voice_score, contributions, communities,
                                      relevance, authenticity_flag, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (author_id) DO UPDATE SET
                voice_score = EXCLUDED.voice_score,
                contributions = EXCLUDED.contributions,
                communities = EXCLUDED.communities,
                relevance = EXCLUDED.relevance,
                authenticity_flag = EXCLUDED.authenticity_flag,
                updated_at = now()
            """,
            (aid, round(voice, 1), len(rows),
             len({r["topic_key"] for r in relevant}), round(relevance, 3), flag),
        )
    return len(author_ids)


# ── entry point ───────────────────────────────────────────────────────────

def run() -> dict:
    seed_taxonomy()
    state = repo.get_state("aggregate", "")
    wm = state["watermark"] if state else None
    rows = _new_enrichment(wm)
    if not rows:
        return {"new_enrichment": 0, "note": "nothing to aggregate"}

    threads = {(r["source"], r["thread_id"]) for r in rows if r["thread_id"]}
    days = {r["created_at"].date() for r in rows}
    author_ids = {r["author_id"] for r in rows}

    conversations = _rebuild_conversations(threads)
    days_touched, topics_rising = _recompute_topic_days(days)
    issue_rows = _rollup_issues(rows)
    feature_rows = _rollup_features(rows)
    authors_scored = _score_authors(author_ids)

    new_wm = max(r["enriched_at"] for r in rows)
    repo.advance_state("aggregate", "", watermark=new_wm, items=len(rows))
    return {
        "new_enrichment": len(rows), "conversations": conversations,
        "days_touched": days_touched, "topics_rising": topics_rising,
        "issue_rows": issue_rows, "feature_rows": feature_rows,
        "authors_scored": authors_scored, "watermark": new_wm.isoformat(),
    }
