"""`./cm doctor` — one in-container command that answers "is this box healthy
and why not" without installing anything or crafting one-liners (prod ask,
2026-07-09). Every check prints one PASS/FAIL/SKIP line; exit 1 if any FAIL.

Prod: docker compose exec api ./cm doctor
"""
from __future__ import annotations

import os

_RESULTS: list[tuple[str, str, str]] = []  # (status, name, detail)


def _check(name: str):
    def deco(fn):
        def run():
            try:
                detail = fn() or "ok"
                _RESULTS.append(("PASS", name, str(detail)))
            except _Skip as s:
                _RESULTS.append(("SKIP", name, str(s)))
            except Exception as e:  # noqa: BLE001 — a doctor never crashes
                _RESULTS.append(("FAIL", name, f"{type(e).__name__}: {str(e)[:160]}"))
        return run
    return deco


class _Skip(Exception):
    pass


@_check("database")
def _db():
    from community.store import db
    n = db.one("SELECT count(*) AS n FROM social_items")["n"]
    wm = db.one("SELECT max(last_success_at) AS t FROM pipeline_state")["t"]
    return f"{n} items, last stage success {wm or 'never'}"


@_check("migrations")
def _migrations():
    from community.store import db
    rows = db.query("SELECT count(*) AS n FROM schema_migrations")
    return f"{rows[0]['n']} applied"


@_check("reddit (old.reddit reachable + real listing)")
def _reddit():
    from community.scrape.reddit import _preflight
    if not _preflight():
        raise RuntimeError("old.reddit is blocked or unreachable from this network "
                           "— reddit collection will be skipped by preflight")
    return "listing page served with posts"


@_check("chromium (playwright headless launch)")
def _chromium():
    import asyncio

    async def probe():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto("about:blank", timeout=10_000)
            ver = browser.version
            await browser.close()
            return ver
    return f"launched (chromium {asyncio.run(probe())})"


@_check("anthropic key (free count_tokens call)")
def _anthropic():
    from community.config.settings import settings
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set — enrichment and drafts are dead")
    from community.llm.client import client
    r = client().messages.count_tokens(
        model=settings.enrich_model,
        messages=[{"role": "user", "content": "ping"}])
    return f"key valid ({r.input_tokens} tokens counted, {settings.enrich_model})"


@_check("x / twitterapi.io")
def _x():
    import httpx

    from community.config.settings import settings
    if not settings.twitterapi_key:
        raise _Skip("TWITTERAPI_IO_KEY not set — X collection off")
    r = httpx.get("https://api.twitterapi.io/twitter/tweet/advanced_search",
                  params={"query": "nubra", "queryType": "Latest"},
                  headers={"X-API-Key": settings.twitterapi_key}, timeout=15)
    if r.status_code == 402:
        raise RuntimeError("402 — credits exhausted")
    r.raise_for_status()
    return f"search ok (status {r.status_code})"


@_check("langfuse")
def _langfuse():
    import httpx
    pk, sk = os.environ.get("LANGFUSE_PUBLIC_KEY"), os.environ.get("LANGFUSE_SECRET_KEY")
    if not (pk and sk):
        raise _Skip("keys not set — llm_usage table is the only meter")
    host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
    r = httpx.post(f"{host}/api/public/ingestion", auth=(pk, sk),
                   json={"batch": []}, timeout=10)
    if r.status_code == 403:
        raise RuntimeError(f"auth ok but ingestion refused: {r.json().get('message', '')[:100]}")
    if r.status_code >= 400:
        raise RuntimeError(f"status {r.status_code}")
    return "ingestion accepting"


@_check("slack channel")
def _slack():
    if not os.environ.get("SLACK_WEBHOOK_URL"):
        raise _Skip("SLACK_WEBHOOK_URL not set — archive-only")
    from community.config.settings import settings
    return ("creds present; sends " +
            ("ACTIVE (MODE=prod)" if settings.mode == "prod"
             else f"gated off (MODE={settings.mode})"))


@_check("email channel")
def _email():
    if not (os.environ.get("GMAIL_SENDER") and os.environ.get("GMAIL_APP_PASSWORD")):
        raise _Skip("GMAIL_SENDER/GMAIL_APP_PASSWORD not set — archive-only")
    from community.config.settings import settings
    return ("creds present; sends " +
            ("ACTIVE (MODE=prod)" if settings.mode == "prod"
             else f"gated off (MODE={settings.mode})"))


@_check("grounding catalog")
def _grounding():
    from community.store import db
    n = db.one("SELECT count(*) AS n FROM nubra_features WHERE is_current")["n"]
    if n == 0:
        raise RuntimeError("EMPTY — drafts cannot ground; run scripts/seed_features.py")
    v = db.one("SELECT version FROM nubra_features WHERE is_current LIMIT 1")["version"]
    return f"{n} features current (version {v})"


@_check("watch sources")
def _sources():
    from community.store import db
    rows = db.query("SELECT kind, count(*) AS n FROM watch_sources "
                    "WHERE active GROUP BY kind ORDER BY kind")
    if not rows:
        raise RuntimeError("EMPTY — registry fallback only, no brand-watch keyword; "
                           "run scripts/seed_sources.py")
    return ", ".join(f"{r['n']} {r['kind']}" for r in rows)



def _live_probe(name: str) -> dict:
    """One cheap live reachability/auth check per source family (user decision
    2026-07-18: the health page must test the actual APIs, not just stored
    state). Small timeouts; failures return a reason, never raise."""
    import os

    import httpx
    try:
        if name == "twitter":
            key = os.getenv("TWITTERAPI_IO_KEY")
            if not key:
                return {"live": "no_key"}
            r = httpx.get("https://api.twitterapi.io/twitter/tweet/advanced_search",
                          params={"query": "nubra", "queryType": "Latest"},
                          headers={"X-API-Key": key}, timeout=12)
            return {"live": "ok" if r.status_code == 200 else f"http_{r.status_code}"}
        if name == "reddit":
            from community.scrape.reddit import _preflight
            return {"live": "ok" if _preflight() else "blocked_or_down"}
        if name == "youtube":
            key = os.getenv("YOUTUBE_API_KEY")
            if not key:
                return {"live": "no_key"}
            r = httpx.get("https://www.googleapis.com/youtube/v3/search",
                          params={"part": "id", "q": "nubra", "maxResults": 1, "key": key},
                          timeout=12)
            return {"live": "ok" if r.status_code == 200 else f"http_{r.status_code}"}
        if name == "github":
            headers = {"Accept": "application/vnd.github+json"}
            tok = os.getenv("GITHUB_TOKEN")
            if tok:
                headers["Authorization"] = f"Bearer {tok}"
            r = httpx.get("https://api.github.com/rate_limit", headers=headers, timeout=12)
            if r.status_code != 200:
                return {"live": f"http_{r.status_code}"}
            core = r.json().get("resources", {}).get("core", {})
            return {"live": "ok", "detail": f"{core.get('remaining')}/{core.get('limit')} calls left"}
        if name == "broker_communities":
            r = httpx.get("https://tradingqna.com/latest.json", timeout=12,
                          headers={"User-Agent": "Mozilla/5.0"})
            return {"live": "ok" if r.status_code == 200 else f"http_{r.status_code}"}
        if name == "app_reviews":
            r = httpx.get("https://itunes.apple.com/in/rss/customerreviews/id=6746636699/json",
                          timeout=12, follow_redirects=True)
            return {"live": "ok" if r.status_code == 200 else f"http_{r.status_code}"}
        return {"live": "no_probe"}
    except Exception as e:  # noqa: BLE001 — a probe failure is a result, not an error
        return {"live": "unreachable", "detail": f"{type(e).__name__}: {str(e)[:80]}"}


def _collector_check(source: str):
    """PASS/SKIP/FAIL from the same live probe the Source-health page uses."""
    r = _live_probe(source)
    live = r.get("live")
    detail = r.get("detail", "")
    if live == "ok":
        return ("PASS", f"{live}{' — ' + detail if detail else ''}")
    if live in ("no_key",):
        return ("SKIP", "key not set — source off")
    return ("FAIL", f"{live}{' — ' + detail if detail else ''}")


@_check("youtube (live API probe)")
def _youtube():
    status, msg = _collector_check("youtube")
    if status == "SKIP":
        raise _Skip(msg)
    if status == "FAIL":
        raise RuntimeError(msg)
    return msg


@_check("github (live API probe)")
def _github():
    status, msg = _collector_check("github")
    if status == "FAIL":
        raise RuntimeError(msg)
    return msg


@_check("broker forums (reachability)")
def _forums():
    status, msg = _collector_check("broker_communities")
    if status == "FAIL":
        raise RuntimeError(msg)
    return msg


@_check("app stores (reachability)")
def _appstores():
    status, msg = _collector_check("app_reviews")
    if status == "FAIL":
        raise RuntimeError(msg)
    return msg


def run_doctor() -> int:
    checks = [_db, _migrations, _grounding, _sources, _reddit, _chromium,
              _anthropic, _x, _youtube, _github, _forums, _appstores,
              _langfuse, _slack, _email]
    for c in checks:
        c()
    width = max(len(n) for _, n, _ in _RESULTS) if _RESULTS else 0
    fails = 0
    for status, name, detail in _RESULTS:
        print(f"{status:<4}  {name:<{width}}  {detail}")
        fails += status == "FAIL"
    print(f"\n{len(_RESULTS) - fails}/{len(_RESULTS)} checks healthy"
          + (f" — {fails} FAILING" if fails else ""))
    return 1 if fails else 0
