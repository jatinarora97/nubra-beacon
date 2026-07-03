"""Twitter / X adapter — via twitterapi.io (managed scrape, REST, no own-account risk).

Why twitterapi.io and not the official API or a free scraper: see
`docs/social-pulse-twitter-x-ingestion-2026-06-29.md`. Short version — it's ~$0.15/1k
tweets, supports the full search-operator grammar incl. historical search, and carries
no account-ban risk to us. Free scrapers (twikit/twscrape/…) are login-gated and break
every 2-4 weeks; not viable for a standing radar.

Each tweet (and optionally each reply) becomes its own `RawItem`, so the rest of the
pipeline (store dedup → prefilter → classify → trend → actions → rising-voices) treats X
exactly like Reddit — no downstream changes.

Auth: TWITTERAPI_IO_KEY in the environment (loaded from .env like ANTHROPIC_API_KEY).
"""
from __future__ import annotations

import csv
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..schema import RawItem

ENDPOINT = "https://api.twitterapi.io/twitter/tweet/advanced_search"

# Interim store: a vetted CSV that Streamlit reads (no live API spend in-app).
# Refresh it with `python fetch_twitter_csv.py`.
CSV_PATH = Path(__file__).resolve().parents[2] / "data" / "twitter_pulse.csv"

# Default India F&O / options / algo-dev / broker query set — tuned for Nubra's interest
# (NSE/BSE F&O, the algo/API crowd, and broker chatter). Each entry: (body, min_faves).
# A lower min_faves for the smaller algo/dev community; higher for the broad retail tags.
DEFAULT_QUERIES = [
    ("#BankNifty OR #Nifty50 OR #Nifty OR #FinNifty OR #Sensex", 25),
    ("#FnO OR #optionstrading OR #optionselling OR #optionbuying OR \"option trading\"", 15),
    ("#algotrading OR \"algo trading\" OR kiteconnect OR \"kite api\" OR openalgo OR \"dhan api\" OR \"trading api\"", 5),
    ("(zerodha OR groww OR dhan OR upstox OR angelone OR \"discount broker\") (nifty OR option OR fno OR trading OR brokerage)", 10),
    ("#StockMarketIndia OR #IndianStockMarket OR #sharemarketindia OR #intraday OR #trading", 30),
]


def _hdr(key: str) -> dict:
    return {"X-API-Key": key, "Accept": "application/json"}


def _parse_ts(s: str) -> datetime:
    # twitterapi.io createdAt format: "Mon Jun 29 10:02:56 +0000 2026"
    try:
        return datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y").astimezone(timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _to_item(t: dict, query: str) -> RawItem | None:
    text = (t.get("text") or "").strip()
    if not text:
        return None
    author = t.get("author") or {}
    handle = author.get("userName") or "[unknown]"
    return RawItem(
        source="twitter",
        source_type="reply" if t.get("isReply") else "tweet",
        external_id=str(t.get("id")),
        text=text,
        author=handle,
        url=t.get("url") or t.get("twitterUrl"),
        created_at=_parse_ts(t.get("createdAt") or ""),
        engagement={
            "score": t.get("likeCount") or 0,          # 'score' = likes (downstream convention)
            "replies": t.get("replyCount") or 0,
            "retweets": t.get("retweetCount") or 0,
            "quotes": t.get("quoteCount") or 0,
            "views": t.get("viewCount") or 0,
            "bookmarks": t.get("bookmarkCount") or 0,
            "upvote_ratio": None,
        },
        raw={
            "channel": "x",
            "handle": handle,
            "name": author.get("name"),
            "followers": author.get("followers"),
            "verified": bool(author.get("isBlueVerified") or author.get("isVerified")),
            "lang": t.get("lang"),
            "is_reply": bool(t.get("isReply")),
            "conversation_id": t.get("conversationId"),
            "query": query,
            # NOTE: deliberately no 'subreddit' key — keeps X out of the Reddit subreddit
            # charts. Rising-Voices breadth just won't credit X cross-community (fine).
        },
    )


def _get_page(key: str, params: dict, retries: int = 4, backoff: float = 6.0):
    """One request with 429-aware backoff. Returns parsed JSON or None."""
    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=_hdr(key))
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                wait = backoff * (attempt + 1)   # 6s, 12s, 18s …
                print(f"  [twitter] 429 rate-limited — waiting {wait:.0f}s "
                      f"(attempt {attempt + 1}/{retries})")
                time.sleep(wait)
                continue
            print(f"  [twitter] HTTP {e.code} — giving up this page")
            return None
        except Exception as e:  # noqa: BLE001
            print(f"  [twitter] page error: {e}")
            return None
    return None


def _search(key: str, query: str, max_pages: int, sleep: float = 1.5):
    """Yield tweet dicts for one query, walking cursor pagination up to max_pages."""
    cursor = None
    for _ in range(max_pages):
        params = {"query": query, "queryType": "Latest"}
        if cursor:
            params["cursor"] = cursor
        data = _get_page(key, params)
        if data is None:
            return
        tweets = data.get("tweets") or []
        for t in tweets:
            yield t
        if not data.get("has_next_page") or not data.get("next_cursor") or not tweets:
            return
        cursor = data["next_cursor"]
        time.sleep(sleep)  # be polite; also smooths trial-tier rate limits


def fetch_twitter(cfg: dict) -> list[RawItem]:
    """Fetch high-engagement, last-N-days tweets per the `twitter` config block.

    Honours a HARD budget via `max_tweets` (≈ $0.00015/tweet on twitterapi.io) so a run
    can never overspend. Queries are built from the config lists, or fall back to the
    India F&O default set.
    """
    tw = cfg.get("twitter", {})
    key = os.environ.get("TWITTERAPI_IO_KEY")
    if not key:
        raise SystemExit("TWITTERAPI_IO_KEY not set in environment/.env — cannot fetch X.")

    days = int(tw.get("days", 7) or 7)
    lang = tw.get("lang", "en")
    max_tweets = int(tw.get("max_tweets", 600))
    pages_per_query = int(tw.get("pages_per_query", 8))
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    until = (now + timedelta(days=1)).strftime("%Y-%m-%d")   # inclusive of today

    queries = _build_queries(tw, lang, since, until)

    items: list[RawItem] = []
    seen: set[str] = set()
    billed = 0          # every tweet the API RETURNS is billed — cap on this, not on unique
    for q in queries:
        if billed >= max_tweets:
            break
        before = len(items)
        for t in _search(key, q, pages_per_query):
            billed += 1
            tid = str(t.get("id"))
            if tid not in seen:
                it = _to_item(t, q)
                if it is not None:
                    seen.add(tid)
                    items.append(it)
            if billed >= max_tweets:
                break
        print(f"  [twitter] +{len(items) - before} unique from: {q[:55]}…  "
              f"(unique {len(items)} / billed {billed})")
    print(f"  [twitter] {len(items)} unique tweets · ~{billed} reads "
          f"(≈ ${billed * 0.00015:.3f}) · cap {max_tweets}")
    return items


# --------------------------- vetting + CSV store ---------------------------

# Crypto/forex/airdrop noise — the $-cashtag queries especially drag these in.
_CRYPTO_DENY = [
    "perpetual", "pre ipo", "preipo", "presale", "airdrop", "memecoin", "meme coin",
    "crypto", "bitcoin", "ethereum", "$btc", "$eth", "$doge", "$sol", "$bnb",
    "ger40", "xauusd", "binance", "altcoin", "shitcoin", "pump.fun", "solana",
]
# At least one of these must appear → keeps it Indian-market / F&O / algo relevant.
_INDIA_ALLOW = [
    "nifty", "banknifty", "bank nifty", "sensex", "finnifty", "fno", "f&o", "option",
    "expiry", "intraday", "zerodha", "dhan", "groww", "upstox", "angelone", "angel one",
    "sebi", "nse", "bse", "algotrading", "algo trading", "kite", "openalgo", "sharemarket",
    "share market", "stock market", "stocks", "trading", "trader", "ipo", "rupee",
]


def _relevant(text: str) -> tuple[bool, str]:
    t = (text or "").lower()
    if any(d in t for d in _CRYPTO_DENY):
        return False, "crypto/forex noise"
    if not any(a in t for a in _INDIA_ALLOW):
        return False, "no India/F&O signal"
    return True, ""


def vet(items: list[RawItem]) -> tuple[list[RawItem], list[tuple[str, str]]]:
    """Drop empties, dupes, crypto/forex noise, and off-topic tweets.

    Returns (kept, dropped) where dropped is [(id, reason)] for transparency.
    """
    kept: list[RawItem] = []
    dropped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for it in items:
        if it.external_id in seen:
            dropped.append((it.external_id, "duplicate"))
            continue
        seen.add(it.external_id)
        if not (it.text or "").strip():
            dropped.append((it.external_id, "empty"))
            continue
        ok, reason = _relevant(it.text)
        if not ok:
            dropped.append((it.external_id, reason))
            continue
        kept.append(it)
    return kept, dropped


_CSV_COLS = ["external_id", "created_at", "author", "followers", "verified", "source_type",
             "likes", "replies", "retweets", "quotes", "views", "lang", "is_reply",
             "query", "url", "text", "engagement_json", "raw_json"]


def save_twitter_csv(items: list[RawItem], path: Path = CSV_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_COLS)
        w.writeheader()
        for it in items:
            e, r = it.engagement or {}, it.raw or {}
            w.writerow({
                "external_id": it.external_id,
                "created_at": it.created_at.astimezone(timezone.utc).isoformat(),
                "author": it.author, "followers": r.get("followers"),
                "verified": r.get("verified"), "source_type": it.source_type,
                "likes": e.get("score"), "replies": e.get("replies"),
                "retweets": e.get("retweets"), "quotes": e.get("quotes"),
                "views": e.get("views"), "lang": r.get("lang"),
                "is_reply": r.get("is_reply"), "query": r.get("query"),
                "url": it.url, "text": it.text,
                "engagement_json": json.dumps(e), "raw_json": json.dumps(r, default=str),
            })
    return path


def load_twitter_csv(cfg: dict | None = None, path: Path = CSV_PATH) -> list[RawItem]:
    """Read the vetted CSV into RawItems — this is what Streamlit uses (no API spend)."""
    p = Path(path)
    if not p.exists():
        print(f"  [twitter] CSV not found at {p} — run `python fetch_twitter_csv.py` first.")
        return []
    items: list[RawItem] = []
    with open(p, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                created = datetime.fromisoformat(row["created_at"])
            except Exception:
                created = datetime.now(timezone.utc)
            try:
                eng = json.loads(row.get("engagement_json") or "{}")
            except Exception:
                eng = {}
            try:
                raw = json.loads(row.get("raw_json") or "{}")
            except Exception:
                raw = {}
            items.append(RawItem(
                source="twitter", source_type=row.get("source_type") or "tweet",
                external_id=row["external_id"], text=row.get("text") or "",
                author=row.get("author") or "[unknown]", url=row.get("url") or None,
                created_at=created, engagement=eng, raw=raw,
            ))
    print(f"  [twitter] loaded {len(items)} tweets from CSV {p.name}")
    return items


def _build_queries(tw: dict, lang: str, since: str, until: str) -> list[str]:
    """Build full query strings (body + min_faves + lang + date window).

    Precedence: explicit `queries` (list of {body, min_faves}) > config lists
    (cashtags/hashtags/keywords/handles) > India F&O defaults.
    """
    def wrap(body: str, mf: int) -> str:
        clause = f"({body})" if body else ""
        parts = [clause, f"min_faves:{mf}" if mf else "", f"lang:{lang}",
                 f"since:{since}", f"until:{until}"]
        return " ".join(p for p in parts if p)

    explicit = tw.get("queries")
    if explicit:
        return [wrap(q.get("body", ""), int(q.get("min_faves", 0))) for q in explicit]

    built: list[tuple[str, int]] = []
    tags = (tw.get("hashtags") or []) + (tw.get("cashtags") or [])
    if tags:
        built.append((" OR ".join(tags), int(tw.get("min_faves_tags", 20))))
    kws = tw.get("keywords") or []
    if kws:
        body = " OR ".join(f'"{k}"' if " " in k else k for k in kws)
        built.append((body, int(tw.get("min_faves_keywords", 5))))
    handles = tw.get("handles") or []
    if handles:
        body = " OR ".join(f"from:{h.lstrip('@')}" for h in handles)
        built.append((body, 0))   # from a known handle: take everything, no fave floor

    if not built:
        built = DEFAULT_QUERIES
    return [wrap(body, mf) for body, mf in built]
