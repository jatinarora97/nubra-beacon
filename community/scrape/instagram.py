"""Instagram collector (Apify profile-watching route).

Plan: docs/instagram-collector-plan-2026-08-12.md — POC-locked 2026-08-12.
Route: `apify/instagram-scraper` over watched accounts (hashtags proven dry).
Daily cadence (pinned posts bypass onlyPostsNewerThan and re-bill every poll —
hourly measured ≈$55/mo vs the $29 credit pool). Media is persisted to S3 at
fetch (CDN URLs expire in hours). Tier 1 (whisper transcript) and tier 2
(Haiku vision) run AFTER collection via process_tiers(), appending English
text to gated items so the ordinary enrichment path treats reels/carousels
like tweets.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Iterator

import httpx

from community.clean.normalize import norm
from community.config.log import get_logger
from community.scrape import instagram_av as av
from community.scrape.base import AuthorMeta, Engagement, SocialItem, unified_score
from community.store import db
from community.store import repositories as repo

log = get_logger("scrape.instagram")

APIFY = "https://api.apify.com/v2"
SCRAPER = "apify~instagram-scraper"
COMMENTS = "apify~instagram-comment-scraper"
WM_SOURCE = "instagram_posts"   # own pipeline_state key: watermark = max NON-pinned
                                # post ts (extra_sources' generic 'instagram' row
                                # records run time, which must not drive the fetch)

run_costs_usd: float = 0.0      # per-process accumulator, surfaced in tier stats


def _token() -> str:
    return os.getenv("APIFY_TOKEN", "").strip()


def _apify_run(actor: str, payload: dict, *, timeout_s: int = 840,
               memory_mb: int = 1024) -> list[dict]:
    """Async run + poll (sync endpoint caps at ~300s; a daily multi-account
    fetch can exceed it). Accumulates usageTotalUsd into run_costs_usd."""
    global run_costs_usd
    headers = {"Authorization": f"Bearer {_token()}"}
    with httpx.Client(timeout=60, headers=headers) as c:
        r = c.post(f"{APIFY}/acts/{actor}/runs",
                   params={"timeout": timeout_s, "memory": memory_mb}, json=payload)
        r.raise_for_status()
        data = r.json()["data"]
        run_id, dataset_id = data["id"], data["defaultDatasetId"]
        deadline = time.monotonic() + timeout_s + 60
        while time.monotonic() < deadline:
            time.sleep(10)
            st = c.get(f"{APIFY}/actor-runs/{run_id}").json()["data"]
            if st["status"] not in ("READY", "RUNNING"):
                break
        run_costs_usd += float(st.get("usageTotalUsd") or 0.0)
        if st["status"] != "SUCCEEDED":
            raise RuntimeError(f"apify {actor} run {run_id}: {st['status']}")
        items = c.get(f"{APIFY}/datasets/{dataset_id}/items",
                      params={"clean": "true"}).json()
        return items if isinstance(items, list) else []


def _accounts(reg: dict) -> list[str]:
    """DB-first (Sources page manages rows), registry list is the seed/fallback."""
    try:
        rows = db.query("SELECT value FROM watch_sources "
                        "WHERE kind='instagram_account' AND active ORDER BY value")
        if rows:
            return [r["value"] for r in rows]
    except Exception:  # noqa: BLE001 — DB hiccup: fall through to registry
        pass
    return [str(a) for a in reg.get("accounts") or []]


def _denied(caption: str, reg: dict) -> bool:
    low = caption.lower()
    return any(term and str(term).lower() in low
               for term in reg.get("caption_deny_terms") or [])


def _source_type(row: dict) -> str:
    t = (row.get("type") or "").lower()
    return {"video": "reel", "sidecar": "sidecar"}.get(t, "post")


def _dt(value) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return datetime.now(timezone.utc)


def _store_post_media(row: dict, creator: str, kind: str) -> dict:
    """Download-at-fetch → S3 (URLs expire in hours). Returns raw media keys."""
    sc = row.get("shortCode") or ""
    keys: dict = {}
    if kind == "reel" and row.get("videoUrl"):
        k = av.store_media(row["videoUrl"], av.media_key(creator, sc, "reel"))
        if k:
            keys["s3_video"] = k
    if row.get("displayUrl"):
        k = av.store_media(row["displayUrl"], av.media_key(creator, sc, "image"))
        if k:
            keys["s3_display"] = k
    child_keys = []
    for i, child in enumerate(row.get("childPosts") or [], 1):
        u = child.get("displayUrl")
        if not u:
            continue
        k = av.store_media(u, av.media_key(creator, sc, "image", suffix=f"-{i:02d}"))
        if k:
            child_keys.append(k)
    if child_keys:
        keys["s3_children"] = child_keys
    return keys


def _post_item(row: dict, media_keys: dict) -> SocialItem:
    creator = row.get("ownerUsername") or "[unknown]"
    sc = row.get("shortCode") or str(row.get("id"))
    likes = int(row.get("likesCount") or 0)
    comments = int(row.get("commentsCount") or 0)
    caption = (row.get("caption") or "").strip()
    tags = " ".join(f"#{h}" for h in row.get("hashtags") or [])
    music = row.get("musicInfo") or {}
    kind = _source_type(row)
    return SocialItem(
        source="instagram",
        source_type=kind,
        external_id=sc,
        parent_id=None,
        thread_id=sc,
        author=creator,
        author_meta=AuthorMeta(),
        text=" ".join(x for x in (caption, tags) if x)[:8000] or "[no caption]",
        lang=None,
        url=row.get("url") or f"https://www.instagram.com/p/{sc}/",
        created_at=_dt(row.get("timestamp")),
        engagement=Engagement(
            score=unified_score(likes, 0, comments),
            native={"likes": likes, "comments": comments,
                    "plays": int(row.get("videoPlayCount") or 0),
                    "views": int(row.get("videoViewCount") or 0)},
        ),
        raw={
            "short_code": sc,
            "is_pinned": bool(row.get("isPinned")),
            "video_duration_s": row.get("videoDuration"),
            "uses_original_audio": bool(music.get("uses_original_audio")),
            "product_type": row.get("productType"),
            "slide_count": len(row.get("childPosts") or []),
            **media_keys,
            "source_method": "apify_instagram_scraper",
        },
    )


def _comment_item(c: dict, post: SocialItem, *, top_liked: bool = False) -> SocialItem | None:
    text = (c.get("text") or "").strip()
    cid = c.get("id")
    if not cid or not text:
        return None
    likes = int(c.get("likesCount") or 0)
    return SocialItem(
        source="instagram",
        source_type="comment",
        external_id=f"c_{cid}",
        parent_id=post.external_id,
        thread_id=post.external_id,
        author=c.get("ownerUsername") or "[unknown]",
        author_meta=AuthorMeta(),
        text=text[:8000],
        lang=None,
        url=post.url,
        created_at=_dt(c.get("timestamp")),
        engagement=Engagement(score=unified_score(likes, 0, 0), native={"likes": likes}),
        raw={"post_short_code": post.external_id, "top_liked": top_liked,
             "source_method": "apify_instagram_scraper"},
    )


def fetch(reg: dict) -> Iterator[SocialItem]:
    """Yield post + latest-comment items for all watched accounts (one actor
    run). Steady-state passes onlyPostsNewerThan=<watermark-1d>; pinned rows
    come back anyway (actor limitation, POC-measured) and dedup drops them.
    Watermark advances from NON-pinned posts only."""
    if not _token():
        log.warning("APIFY_TOKEN not set — instagram collector skipped")
        return
    handles = _accounts(reg)
    if not handles:
        return

    backfill = bool(reg.get("backfill"))
    state = repo.get_state("ingest", WM_SOURCE)
    watermark = state.get("watermark") if state else None
    payload: dict = {
        "directUrls": [f"https://www.instagram.com/{h}/" for h in handles],
        "resultsType": "posts",
        "resultsLimit": int(reg.get("results_limit_backfill", 20)) if backfill or not watermark
        else int(reg.get("results_limit_daily", 10)),
    }
    if watermark and not backfill:
        payload["onlyPostsNewerThan"] = (watermark - timedelta(days=1)).strftime("%Y-%m-%d")

    rows = _apify_run(SCRAPER, payload, memory_mb=int(reg.get("memory_mb", 1024)))
    skipped_sponsored = skipped_denied = 0
    max_ts: datetime | None = None
    for row in rows:
        if row.get("error"):
            log.warning("account row error: %s — %s", row.get("inputUrl"), row.get("error"))
            continue
        if row.get("paidPartnership") or row.get("isSponsored"):
            skipped_sponsored += 1
            continue
        caption = row.get("caption") or ""
        if _denied(caption, reg):
            skipped_denied += 1
            continue
        creator = row.get("ownerUsername") or "[unknown]"
        kind = _source_type(row)
        media_keys = _store_post_media(row, creator, kind)
        post = _post_item(row, media_keys)
        yield post
        if not post.raw["is_pinned"]:
            max_ts = max(max_ts, post.created_at) if max_ts else post.created_at
        for c in row.get("latestComments") or []:
            item = _comment_item(c, post)
            if item:
                yield item

    if skipped_sponsored or skipped_denied:
        log.info("instagram skips: %d sponsored/paid, %d caption-denied",
                 skipped_sponsored, skipped_denied)
    if max_ts:
        repo.advance_state("ingest", WM_SOURCE, watermark=max_ts, items=len(rows))


# ── tiers (run after collection; sequential by design) ─────────────────────

def _account_median_likes(handle: str) -> float:
    row = db.one(
        """
        SELECT percentile_cont(0.5) WITHIN GROUP
               (ORDER BY (si.engagement->'native'->>'likes')::float) AS med
        FROM social_items si JOIN authors a USING (author_id)
        WHERE si.source='instagram' AND si.source_type <> 'comment'
          AND a.handle = %s
        """,
        (handle,),
    )
    return float(row["med"] or 0.0) if row else 0.0


def _gated(item: dict, reg: dict, medians: dict) -> bool:
    """Per-account RELATIVE engagement gate (likes span 27→181k across the
    watchlist — one absolute bar cannot work)."""
    handle = item["handle"]
    if handle not in medians:
        medians[handle] = _account_median_likes(handle)
    likes = float((item["engagement"].get("native") or {}).get("likes") or 0)
    bar = max(float(reg.get("tier_min_likes", 25)),
              medians[handle] * float(reg.get("tier_multiplier", 1.5)))
    return likes >= bar


def _append_text(item_id: int, old_text: str, block: str, raw_patch: dict) -> None:
    new_text = f"{old_text}\n\n{block}"[:12000]
    db.execute(
        "UPDATE social_items SET text=%s, content_hash=%s, raw = raw || %s::jsonb "
        "WHERE item_id=%s",
        (new_text, repo.content_hash(norm(new_text)), db.jsonb(raw_patch), item_id),
    )
    # absence-based re-enrichment: dropping the row re-queues the item
    db.execute("DELETE FROM item_enrichment WHERE item_id=%s", (item_id,))


def _tier1_transcript(item: dict, reg: dict) -> str:
    """Whisper the reel from S3. Retry contract (user, 2026-08-12): 3 attempts
    total across runs, resuming from the last completed segment timestamp."""
    raw = item["raw"]
    tr = raw.get("transcript_state") or {}
    attempts = int(tr.get("attempts") or 0)
    if attempts >= 3:
        return "gave_up"
    # NOTE (E2E 2026-08-12): uses_original_audio is a SIGNAL, not a gate —
    # creators speak over licensed background tracks (stockburner's scam
    # warning is `false` yet fully speech). Whisper is the arbiter: music-only
    # reels come back empty and take the documented-limitation path, at $0.
    if not raw.get("s3_video"):
        return "no_media"
    cap = float(reg.get("video_duration_cap_s", 360))
    dur = float(raw.get("video_duration_s") or 0)
    offset = float(tr.get("offset_s") or 0.0)
    path = av.fetch_media(raw["s3_video"])
    if not path:
        return "media_fetch_failed"
    try:
        out = av.transcribe(path, model_name=str(reg.get("whisper_model", "large-v3")),
                            offset_s=offset, cap_s=cap)
        text = " ".join(x for x in (tr.get("partial"), out["text"]) if x).strip()
        if not text:
            # music-only / no speech: documented limitation — caption still flows
            db.execute("UPDATE social_items SET raw = raw || %s::jsonb WHERE item_id=%s",
                       (db.jsonb({"transcript_state": {"attempts": attempts + 1,
                                                       "empty": True}}), item["item_id"]))
            return "empty"
        block = (f"TRANSCRIPT (English, auto-transcribed, detected "
                 f"{out['language']} p={out['language_probability']}): {text}")
        truncated = bool(dur and dur > cap)
        _append_text(item["item_id"], item["text"], block,
                     {"transcript_state": {"attempts": attempts + 1, "done": True,
                                           "truncated_at_s": cap if truncated else None},
                      "transcript_language": out["language"]})
        return "ok"
    except Exception as e:  # noqa: BLE001 — persist resume state, retry next run
        log.warning("transcript attempt %d failed for %s (%s: %s)", attempts + 1,
                    item["external_id"], type(e).__name__, str(e)[:120])
        db.execute("UPDATE social_items SET raw = raw || %s::jsonb WHERE item_id=%s",
                   (db.jsonb({"transcript_state": {
                       "attempts": attempts + 1, "offset_s": offset,
                       "partial": tr.get("partial") or ""}}), item["item_id"]))
        return "error"
    finally:
        path.unlink(missing_ok=True)


def _tier2_vision(item: dict) -> str:
    raw = item["raw"]
    keys = list(raw.get("s3_children") or []) or \
        ([raw["s3_display"]] if raw.get("s3_display") else [])
    if not keys:
        return "no_media"
    caption = item["text"].split("\n\n")[0]
    text, _usage = av.describe_images(keys, caption)
    if not text:
        return "vision_failed"
    _append_text(item["item_id"], item["text"], f"ON-SCREEN: {text}",
                 {"vision_done": True, "vision_slides": len(keys)})
    return "ok"


def _top_comments(item: dict, reg: dict) -> int:
    """Top-liked comments for a gated post via the comment-scraper actor
    (latestComments is a latest-sample, NOT top-liked — POC-verified)."""
    from community.scrape.extra_sources import _store
    rows = _apify_run(COMMENTS, {
        "directUrls": [item["url"]],
        "resultsLimit": int(reg.get("comments_fetch_limit", 50)),
    }, timeout_s=300)
    rows = [r for r in rows if r.get("text") and r.get("id")]
    rows.sort(key=lambda r: -int(r.get("likesCount") or 0))
    post = SocialItem(  # minimal shell for _comment_item linkage
        source="instagram", source_type="post", external_id=item["external_id"],
        thread_id=item["external_id"], author="[unknown]", text="-",
        url=item["url"], created_at=repo.now_utc(),
    )
    counters = {"inserted": 0, "skipped_existing": 0}
    for r in rows[: int(reg.get("comments_top_n", 10))]:
        citem = _comment_item(r, post, top_liked=True)
        if citem:
            _store(citem, counters)
    return counters["inserted"]


def process_tiers(reg: dict) -> dict:
    """Sequential tier pass over un-tiered instagram posts (bounded per run).
    Whisper holds ~2-3GB RAM while active — NEVER parallelize this."""
    stats = {"examined": 0, "gated": 0, "transcripts_ok": 0, "vision_ok": 0,
             "top_comments_inserted": 0, "skipped": {}, "apify_cost_usd": 0.0}
    if not _token():
        return stats
    global run_costs_usd
    run_costs_usd = 0.0
    limit = int(reg.get("max_tier_items_per_run", 12))
    items = db.query(
        """
        SELECT si.item_id, si.external_id, si.source_type, si.text, si.url,
               si.engagement, si.raw, a.handle
        FROM social_items si JOIN authors a USING (author_id)
        WHERE si.source='instagram' AND si.source_type <> 'comment'
          AND (si.raw->>'tiers_done') IS NULL
        ORDER BY si.ingested_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    medians: dict[str, float] = {}
    for item in items:
        stats["examined"] += 1
        done_patch = {"tiers_done": True}
        try:
            if not _gated(item, reg, medians):
                stats["skipped"]["below_gate"] = stats["skipped"].get("below_gate", 0) + 1
            else:
                stats["gated"] += 1
                if item["source_type"] == "reel":
                    verdict = _tier1_transcript(item, reg)
                    if verdict == "ok":
                        stats["transcripts_ok"] += 1
                    elif verdict == "error":
                        done_patch = {}  # retry next run (attempts capped at 3)
                    else:
                        stats["skipped"][verdict] = stats["skipped"].get(verdict, 0) + 1
                else:
                    verdict = _tier2_vision(item)
                    if verdict == "ok":
                        stats["vision_ok"] += 1
                    else:
                        stats["skipped"][verdict] = stats["skipped"].get(verdict, 0) + 1
                try:
                    stats["top_comments_inserted"] += _top_comments(item, reg)
                except Exception as e:  # noqa: BLE001 — comments are additive
                    log.warning("top-comments failed for %s (%s)",
                                item["external_id"], type(e).__name__)
        except Exception as e:  # noqa: BLE001 — one item must not sink the pass
            log.exception("tier pass failed for %s (%s)", item["external_id"],
                          type(e).__name__)
        if done_patch:
            db.execute("UPDATE social_items SET raw = raw || %s::jsonb WHERE item_id=%s",
                       (db.jsonb(done_patch), item["item_id"]))
    stats["apify_cost_usd"] = round(run_costs_usd, 4)
    return stats
