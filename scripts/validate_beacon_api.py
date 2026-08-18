"""Validate the live Beacon API against the v1 contract — shapes, auth,
pagination, errors. Stdlib only; run from anywhere that reaches the api:

    python3 scripts/validate_beacon_api.py http://localhost:8400 nbk_xxx

(on prod: docker compose exec api python scripts/validate_beacon_api.py \
    http://localhost:8400 nbk_xxx)
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE, KEY = (sys.argv + ["http://localhost:8400", ""])[1:3]
V1 = f"{BASE}/api/beacon/v1"
PASS = FAIL = 0


def call(path: str, key: str | None = KEY) -> tuple[int, dict | list | None]:
    req = urllib.request.Request(V1 + path, headers={"X-API-Key": key} if key else {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:  # noqa: BLE001
        print(f"  !! {path}: {type(e).__name__}: {e}")
        return -1, None


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    PASS, FAIL = PASS + ok, FAIL + (not ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def envelope(name: str, path: str, row_keys: tuple = (), allow_empty: bool = True):
    code, body = call(path)
    if code != 200 or not isinstance(body, dict) or "results" not in body:
        check(name, False, f"status {code}, envelope missing")
        return None
    rows = body["results"]
    if not rows:
        check(name, allow_empty, "0 results (empty window is OK)" if allow_empty
              else "0 results")
        return body
    missing = [k for k in row_keys if k not in rows[0]]
    check(name, not missing,
          f"{len(rows)} rows" + (f", MISSING keys: {missing}" if missing else ""))
    return body


# ── auth ────────────────────────────────────────────────────────────────────
check("401 without key", call("/taxonomy", key=None)[0] == 401)
check("401 wrong key", call("/taxonomy", key="nbk_wrong")[0] == 401)
check("200 with key", call("/taxonomy")[0] == 200)

# ── corpus ──────────────────────────────────────────────────────────────────
W = "?since=2026-08-01"
b = envelope("/items", f"/items{W}&limit=5",
             ("item_id", "source", "external_id", "thread_id", "text", "url",
              "created_at", "ingested_at", "engagement", "author", "topic_key",
              "intent", "sentiment", "entities", "is_noise", "raw"))
if b and b["results"]:
    r0 = b["results"][0]
    check("full text (not truncated marker)", len(r0["text"]) != 300)
    check("raw internals stripped",
          not any(k in (r0["raw"] or {}) for k in
                  ("s3_video", "transcript_state", "tiers_done")))
    if b.get("next_cursor"):
        b2 = call(f"/items{W}&limit=5&cursor={b['next_cursor']}")[1]
        ids1 = {x["item_id"] for x in b["results"]}
        ids2 = {x["item_id"] for x in (b2 or {}).get("results", [])}
        check("cursor pages disjoint", not (ids1 & ids2))
    src, eid = r0["source"], r0["external_id"]
    code, det = call(f"/items/{src}/{eid}")
    check("/items/{source}/{external_id}",
          code == 200 and "item" in (det or {}) and "thread_siblings" in det)

envelope("/items/search (OR + phrase)",
         f"/items/search{W}&q=%22option%20chain%22%20OR%20scam&limit=3",
         ("match_snippet", "text", "source"))

# ── people ──────────────────────────────────────────────────────────────────
b = envelope("/authors", f"/authors{W}&min_items=1&limit=5",
             ("source", "handle", "first_seen_at", "last_seen_at",
              "item_count", "avg_engagement", "top_topics"))
if b and b["results"]:
    a0 = b["results"][0]
    code, det = call(f"/authors/{a0['source']}/{a0['handle']}")
    check("/authors/{source}/{handle}",
          code == 200 and "author" in (det or {}) and "recent_items" in det)

# ── intelligence ────────────────────────────────────────────────────────────
envelope("/trends", f"/trends{W}")
envelope("/broker-issues", f"/broker-issues{W}")
envelope("/feature-requests", f"/feature-requests{W}")
envelope("/nubra-mentions", f"/nubra-mentions{W}")
envelope("/topic-suggestions", "/topic-suggestions")

# ── action layer ────────────────────────────────────────────────────────────
envelope("/opportunities", f"/opportunities{W}")
envelope("/drafts", f"/drafts{W}")
envelope("/briefs", "/briefs")
envelope("/social-recommendations", "/social-recommendations")
envelope("/roundups", "/roundups?period=daily")

# ── ops + meta ──────────────────────────────────────────────────────────────
envelope("/runs", "/runs", ("stage", "source", "watermark", "last_success_at"))
envelope("/source-health", "/source-health", ("name", "enabled", "health"))
envelope("/watch-sources", "/watch-sources", ("kind", "value", "active"))
code, tax = call("/taxonomy")
check("/taxonomy shape", code == 200 and all(
    k in (tax or {}) for k in ("sources", "topics", "intents", "audiences",
                               "issue_types", "brokers")))
code, g = call("/grounding")
check("/grounding shape", code == 200 and "results" in (g or {})
      and "version" in (g or {}),
      f"version={g.get('version') if g else '?'} features={len(g['results']) if g else 0}")
check("/usage", call("/usage")[0] == 200)

# ── errors ──────────────────────────────────────────────────────────────────
check("422 bad source", call("/items?sources=facebook")[0] == 422)
check("422 bad cursor", call("/items?cursor=garbage!!")[0] == 422)
check("422 bad date", call("/items?since=yesterday")[0] == 422)
check("422 since>=until", call("/items?since=2026-08-10&until=2026-08-01")[0] == 422)
check("404 unknown item", call("/items/twitter/nope123")[0] == 404)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
