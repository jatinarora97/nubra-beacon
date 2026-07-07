"""Stage ④ AGGREGATE (LLD-02 §8) — conversations, topic_daily, issue/feature
rollups, author_stats. Consumes item_enrichment past the 'aggregate' watermark
(enriched_at — arrival clock).

feature_key assignment is the LLD-02 §8.4 incremental centroid design: embed the
feature phrase (multilingual-e5-small), nearest existing feature_keys.centroid by
cosine; ≥ τ (registry aggregate.feature_sim_threshold) → reuse key + fold into
the running-mean centroid; else mint feat_NNNNN. Near-misses (0.70–τ) logged for
threshold tuning. No per-run re-clustering (arch §4.2).
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from community.reference.taxonomy import TOPICS, seed_taxonomy
from community.store import db, repositories as repo


# ── helpers ───────────────────────────────────────────────────────────────

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

def _rollup_issues(days: set) -> int:
    """Full recompute per touched day (idempotent — mirrors _recompute_topic_days).
    The previous additive UPSERT double-counted whenever a rerun or watermark
    replay re-fed items (counts drifted to 2x while sample ids deduped);
    recompute-and-replace makes replays safe."""
    n_groups = 0
    for day in sorted(days):
        items = db.query(
            """
            SELECT ie.item_id, ie.sentiment, ie.entities,
                   (si.engagement->>'score')::float AS score,
                   COALESCE((si.engagement->'native'->>'views')::bigint, 0) AS views,
                   a.followers
            FROM item_enrichment ie
            JOIN social_items si ON si.item_id = ie.item_id
            JOIN authors a ON a.author_id = si.author_id
            WHERE NOT ie.is_noise AND ie.intent = 'complaint'
              AND ie.entities->>'broker' IS NOT NULL
              AND si.created_at::date = %s
            """,
            (day,),
        )
        groups: dict[tuple, list[dict]] = defaultdict(list)
        for r in items:
            ents = r["entities"] or {}
            groups[(ents["broker"], ents.get("issue_type") or "support")].append(r)
        db.execute("DELETE FROM issue_rollup WHERE day = %s", (day,))
        for (broker, issue_key), grp in groups.items():
            sentiments = [i["sentiment"] for i in grp if i["sentiment"] is not None]
            neg_share = (sum(1 for s in sentiments if s < -0.3) / len(sentiments)) if sentiments else 0
            reach = sum(max(i["followers"] or 0, i["views"] or 0) for i in grp)
            severity = math.log1p(reach) * neg_share
            samples = [i["item_id"] for i in
                       sorted(grp, key=lambda x: -(x["score"] or 0))[:5]]
            db.execute(
                """
                INSERT INTO issue_rollup (broker, issue_key, day, count, severity,
                                          sentiment_avg, sample_item_ids)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                (broker, issue_key, day, len(grp), severity,
                 sum(sentiments) / len(sentiments) if sentiments else None, samples),
            )
            n_groups += 1
    return n_groups


# ── feature_rollup + feature_keys (LLD-02 §8.4 incremental centroids) ─────

def _mint_key(phrase: str, vec: list[float]) -> str:
    from community.enrich.embeddings import to_vec

    nxt = db.one(
        "SELECT COALESCE(MAX(substring(feature_key FROM 6)::int), 0) + 1 AS n "
        "FROM feature_keys WHERE feature_key ~ '^feat_[0-9]+$'")["n"]
    key = f"feat_{nxt:05d}"
    db.execute(
        "INSERT INTO feature_keys (feature_key, canonical_label, centroid, phrase_count) "
        "VALUES (%s, %s, %s::vector, 1) ON CONFLICT (feature_key) DO NOTHING",
        (key, phrase[:120], to_vec(vec)),
    )
    return key


def _feature_key_for(phrase: str) -> str:
    """Incremental centroid assignment: nearest existing centroid ≥ τ → assign
    + fold (running mean, renormalized); else mint. Near-misses logged."""
    from community.config.settings import settings
    from community.enrich import embeddings

    vec = embeddings.embed_texts([phrase])[0]
    vstr = embeddings.to_vec(vec)
    tau = float(settings.registry.get("aggregate", {}).get("feature_sim_threshold", 0.80))
    best = db.one(
        "SELECT feature_key, canonical_label, phrase_count, centroid::text AS c, "
        "1 - (centroid <=> %s::vector) AS sim "
        "FROM feature_keys WHERE centroid IS NOT NULL AND is_active "
        "ORDER BY centroid <=> %s::vector LIMIT 1",
        (vstr, vstr),
    )
    if best and best["sim"] is not None:
        if best["sim"] >= tau:
            n = best["phrase_count"]
            old = embeddings.from_vec(best["c"])
            folded = [(o * n + v) / (n + 1) for o, v in zip(old, vec)]
            norm_ = sum(x * x for x in folded) ** 0.5 or 1.0
            folded = [x / norm_ for x in folded]
            db.execute(
                "UPDATE feature_keys SET centroid = %s::vector, "
                "phrase_count = phrase_count + 1, updated_at = now() "
                "WHERE feature_key = %s",
                (embeddings.to_vec(folded), best["feature_key"]),
            )
            return best["feature_key"]
        if tau - 0.03 <= best["sim"] < tau:  # near-miss band, e5 range is compressed
            print(f"[aggregate] feature near-miss {best['sim']:.2f}: "
                  f"{phrase[:50]!r} vs {best['canonical_label'][:50]!r} "
                  f"({best['feature_key']}) — below τ={tau}")
    return _mint_key(phrase, vec)


def recompute_feature_day(key: str, day) -> None:
    """Replace the (feature_key, day) rollup row from feature_item_map — the
    single source of truth for counts. Mirrors the _rollup_issues recompute."""
    stats = db.query(
        """
        SELECT m.item_id, ie.entities, (si.engagement->>'score')::float AS score
        FROM feature_item_map m
        JOIN item_enrichment ie ON ie.item_id = m.item_id
        JOIN social_items si ON si.item_id = m.item_id
        WHERE m.feature_key = %s AND m.day = %s
        """,
        (key, day),
    )
    db.execute("DELETE FROM feature_rollup WHERE feature_key=%s AND day=%s", (key, day))
    if not stats:
        return
    label = (db.one("SELECT canonical_label FROM feature_keys WHERE feature_key=%s",
                    (key,)) or {}).get("canonical_label") or key
    brokers = sorted({(s["entities"] or {}).get("broker") for s in stats
                      if (s["entities"] or {}).get("broker")})
    samples = [s["item_id"] for s in
               sorted(stats, key=lambda x: -(x["score"] or 0))[:5]]
    db.execute(
        """
        INSERT INTO feature_rollup (feature_key, day, canonical_label, count,
                                    brokers_mentioned, sample_item_ids)
        VALUES (%s,%s,%s,%s,%s,%s)
        """,
        (key, day, label[:120], len(stats), brokers, samples),
    )


def _rollup_features(rows: list[dict]) -> int:
    """Exactly-once + idempotent (work plan 2026-07-07, B3). feature_item_map
    is the ledger of item -> feature_key: an item folds into a centroid only
    when it FIRST enters the map (replayed items reuse their recorded key, so
    centroids never re-fold), and rollup counts are recomputed FROM the map —
    the additive upsert that let watermark replays double-count is gone."""
    touched: set[tuple] = set()
    for r in rows:
        ents = r["entities"] or {}
        phrase = ents.get("feature_phrase")
        if r["intent"] != "feature_request" or not phrase or r["is_noise"]:
            continue
        day = r["created_at"].date()
        existing = db.one(
            "SELECT feature_key FROM feature_item_map WHERE item_id=%s",
            (r["item_id"],))
        if existing:
            key = existing["feature_key"]  # replay — no re-fold, no re-mint
        else:
            key = _feature_key_for(phrase)  # folds/mints exactly once per item
            db.execute(
                "INSERT INTO feature_item_map (item_id, feature_key, day) "
                "VALUES (%s,%s,%s) ON CONFLICT (item_id) DO NOTHING",
                (r["item_id"], key, day))
        touched.add((key, day))
    for key, day in sorted(touched, key=lambda t: (t[0], str(t[1]))):
        recompute_feature_day(key, day)
    return len(touched)


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
    issue_rows = _rollup_issues(days)
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
