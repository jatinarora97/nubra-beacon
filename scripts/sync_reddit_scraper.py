"""Vendor the zanshash/reddit_scraper into community/lib/reddit_scraper/.

Source of truth: github.com/zanshash/reddit_scraper (local checkout at
.vendor/reddit_scraper, auto-cloned on first run — `git pull` there to update).
Rewrites the two flat imports to package-relative, applies the NESTED-REPLIES
and LOGIN patches (below), and stamps provenance. Re-run to refresh; --check
for CI drift.

Nested-replies patch: upstream collects top-level comments only. We addition-
ally walk ONE nested level per top comment (strict child chain
`> div.child > div.sitetable > div.thing.comment`, cap 3 replies) and carry
them as Comment.replies. Applied here — never hand-edit the vendored copy.
If upstream refactors fetch_comments/models the anchors below fail loudly.

Login patch (2026-09-24): old.reddit now forces a login wall on logged-out
listing pages (verified on prod — a fresh anonymous browser bounces to
/login?reason=lor2 and never sees post content; confirmed distinct from a
DOM/selector drift issue — the legacy markup is unchanged once authenticated).
Adds REDDIT_USERNAME/REDDIT_PASSWORD (set by the caller, like SKIP_IDS) and a
login step that runs once per `run()`, reusing a cached session
(out/reddit_scraper/reddit_auth_state.json) across hourly runs where it still
grants access, so we don't log in from a script every single hour.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

SRC = pathlib.Path(__file__).resolve().parent.parent / ".vendor" / "reddit_scraper"
UPSTREAM = "https://github.com/zanshash/reddit_scraper"

if not SRC.is_dir():  # fresh checkout (e.g. prod machine) — clone the upstream
    SRC.parent.mkdir(exist_ok=True)
    subprocess.run(["git", "clone", UPSTREAM, str(SRC)], check=True)
DEST = pathlib.Path(__file__).resolve().parent.parent / "community" / "lib" / "reddit_scraper"
FILES = ["scraper.py", "models.py", "config.py"]

# ── nested-replies patch (anchor -> replacement, applied per file) ──────────

_MODELS_FIELD_OLD = """@dataclass
class Comment:
    author: str
    score: Optional[int]
    body: str"""
_MODELS_FIELD_NEW = """@dataclass
class Comment:
    author: str
    score: Optional[int]
    body: str
    replies: List[dict] = field(default_factory=list)  # PATCH: one nested level"""

_MODELS_DICT_OLD = """            "comments": [
                {"author": c.author, "score": c.score, "body": c.body}
                for c in self.comments
            ],"""
_MODELS_DICT_NEW = """            "comments": [
                {"author": c.author, "score": c.score, "body": c.body,
                 "replies": c.replies}
                for c in self.comments
            ],"""

_SCRAPER_APPEND_OLD = """            if body:
                comments.append(Comment(author=author, score=score, body=body))"""
_SCRAPER_APPEND_NEW = """            # PATCH: one nested reply level (strict child chain, cap 3)
            replies = []
            try:
                nested = await el.locator(
                    "> div.child > div.sitetable > div.thing.comment").all()
                for rel in nested[:3]:
                    r_author_el = rel.locator("a.author").first
                    r_author = ((await r_author_el.inner_text()).strip()
                                if await r_author_el.count() else "[deleted]")
                    r_score_el = rel.locator("span.score").first
                    r_score_txt = (await r_score_el.inner_text()
                                   if await r_score_el.count() else "")
                    r_score = (_parse_int(r_score_txt.split()[0])
                               if r_score_txt.strip() else None)
                    r_body_el = rel.locator(
                        "> div.entry div.usertext-body div.md").first
                    r_body = ((await r_body_el.inner_text()).strip()
                              if await r_body_el.count() else "")
                    if r_body:
                        replies.append(
                            {"author": r_author, "score": r_score, "body": r_body})
            except Exception as exc:
                log.debug(f"Reply extract error: {exc}")

            if body:
                comments.append(
                    Comment(author=author, score=score, body=body, replies=replies))"""

# PATCH 2: skip already-ingested posts before the expensive detail-page visit.
# The adapter sets scraper.SKIP_IDS to the set of external_ids already in the DB —
# hourly reruns then only pay detail visits for genuinely new posts.
_SCRAPER_SKIP_OLD = """            for meta in metas:
                if meta["id"] in seen:
                    continue
                seen.add(meta["id"])"""
_SCRAPER_SKIP_NEW = """            for meta in metas:
                if meta["id"] in seen or meta["id"] in SKIP_IDS:
                    continue
                seen.add(meta["id"])"""
_SCRAPER_GLOBAL_OLD = '''BASE = "https://old.reddit.com"'''
_SCRAPER_GLOBAL_NEW = '''BASE = "https://old.reddit.com"
SKIP_IDS: set = set()  # PATCH: pre-known ids to skip (set by the caller)'''

# PATCH 3: login. old.reddit's listing pages force a login wall for
# logged-out clients (since ~2026-08-30). Chains onto the SKIP_IDS global
# patch's own output (applied after it in PATCHES["scraper.py"] below).
_SCRAPER_AUTH_GLOBAL_OLD = _SCRAPER_GLOBAL_NEW
_SCRAPER_AUTH_GLOBAL_NEW = _SCRAPER_GLOBAL_NEW + '''
REDDIT_USERNAME: str = ""  # PATCH: auth — set by the caller
REDDIT_PASSWORD: str = ""  # PATCH: auth — set by the caller'''

_SCRAPER_LOGIN_FN_OLD = '''# ── NSFW / age gate ────────────────────────────────────────────────────────────

async def _accept_over18(page: Page):
    try:
        # old Reddit age-gate is a form with a "yes" button
        btn = page.locator("button[name='over18'], input[value='yes'][name='over18']")
        if await btn.count() > 0:
            await btn.first.click()
            await page.wait_for_load_state("domcontentloaded")
    except Exception:
        pass'''
_SCRAPER_LOGIN_FN_NEW = _SCRAPER_LOGIN_FN_OLD + '''


# ── login (auth) ─────────────────────────────────────────────────────────────
# PATCH: real field names verified against the live login form (2026-09-24,
# via prod): input[name="username"], input[name="password"], button "Log In".
# old.reddit.com/login redirects to www.reddit.com/login — go there directly;
# session cookies are shared across the reddit.com domain, so the same
# context then browses old.reddit.com authenticated.

async def _has_listing_access(page: Page, subreddit: str) -> bool:
    """True when a listing page renders real posts, not the login bounce."""
    try:
        await page.goto(f"{BASE}/r/{subreddit}/new/",
                        wait_until="domcontentloaded", timeout=20_000)
        await page.wait_for_timeout(2_000)  # let any JS bounce-through settle
        return await page.locator("div#siteTable > div.thing.link").count() > 0
    except Exception:
        return False


async def _login(page: Page) -> None:
    await page.goto("https://www.reddit.com/login/",
                    wait_until="domcontentloaded", timeout=30_000)
    user_field = page.locator('input[name="username"]')
    await user_field.wait_for(timeout=15_000)
    await user_field.fill(REDDIT_USERNAME)
    await page.locator('input[name="password"]').fill(REDDIT_PASSWORD)
    await page.locator('button:has-text("Log In")').first.click()
    # success = the login form is gone (a failed login re-shows it with an error)
    await page.locator('input[name="password"]').wait_for(
        state="detached", timeout=20_000)


async def _ensure_logged_in(ctx: BrowserContext, state_path: str) -> None:
    probe = await ctx.new_page()
    try:
        sub = SUBREDDITS[0] if SUBREDDITS else "popular"
        if await _has_listing_access(probe, sub):
            return  # cached session (if any) already grants access
        await _login(probe)
        if not await _has_listing_access(probe, sub):
            raise RuntimeError("logged in but listing still blocked afterward")
        await ctx.storage_state(path=state_path)
        log.info("reddit: logged in, session cached at %s", state_path)
    finally:
        await probe.close()'''

_SCRAPER_RUN_CTX_OLD = """    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=HEADLESS)
        ctx = await browser.new_context(
            user_agent=_UA,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        # Block ad/tracker domains to speed things up
        await ctx.route(
            re.compile(r"(doubleclick\\.net|googlesyndication|adnxs|amazon-adsystem)"),
            lambda route, _: route.abort(),
        )

        try:
            for sub in SUBREDDITS:"""
_SCRAPER_RUN_CTX_NEW = """    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=HEADLESS)
        state_path = os.path.join(OUTPUT_DIR, "reddit_auth_state.json")
        ctx = await browser.new_context(
            user_agent=_UA,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            storage_state=state_path if os.path.exists(state_path) else None,
        )
        # Block ad/tracker domains to speed things up
        await ctx.route(
            re.compile(r"(doubleclick\\.net|googlesyndication|adnxs|amazon-adsystem)"),
            lambda route, _: route.abort(),
        )

        # PATCH: auth — old.reddit forces a login wall for logged-out
        # listing access; log in once (reusing a cached session when it
        # still works) before the crawl instead of hitting the wall silently.
        if REDDIT_USERNAME and REDDIT_PASSWORD:
            await _ensure_logged_in(ctx, state_path)

        try:
            for sub in SUBREDDITS:"""

PATCHES = {
    "models.py": [(_MODELS_FIELD_OLD, _MODELS_FIELD_NEW),
                  (_MODELS_DICT_OLD, _MODELS_DICT_NEW)],
    "scraper.py": [(_SCRAPER_APPEND_OLD, _SCRAPER_APPEND_NEW),
                   (_SCRAPER_SKIP_OLD, _SCRAPER_SKIP_NEW),
                   (_SCRAPER_GLOBAL_OLD, _SCRAPER_GLOBAL_NEW),
                   (_SCRAPER_AUTH_GLOBAL_OLD, _SCRAPER_AUTH_GLOBAL_NEW),
                   (_SCRAPER_LOGIN_FN_OLD, _SCRAPER_LOGIN_FN_NEW),
                   (_SCRAPER_RUN_CTX_OLD, _SCRAPER_RUN_CTX_NEW)],
}


def main(check: bool = False) -> None:
    commit = subprocess.run(
        ["git", "-C", str(SRC), "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True).stdout.strip() or "unknown"
    DEST.mkdir(parents=True, exist_ok=True)
    outputs = {DEST / "__init__.py": ""}
    for name in FILES:
        body = (SRC / name).read_text(encoding="utf-8")
        body = body.replace("from config import", "from .config import")
        body = body.replace("from models import", "from .models import")
        for anchor, replacement in PATCHES.get(name, []):
            if anchor not in body:
                raise SystemExit(
                    f"nested-replies patch anchor missing in upstream {name} — "
                    "upstream changed; re-derive the patch or drop it")
            body = body.replace(anchor, replacement)
        header = (f"# VENDORED from github.com/zanshash/reddit_scraper @ {commit}\n"
                  "# (+ nested-replies + login patches — see this script's docstring)\n"
                  "# Do not edit here; update the source repo, then run "
                  "scripts/sync_reddit_scraper.py\n")
        outputs[DEST / name] = header + body
    drift = []
    for path, content in outputs.items():
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                drift.append(path.name)
        else:
            path.write_text(content, encoding="utf-8")
            print(f"vendored: {path.name}")
    if check and drift:
        raise SystemExit(f"reddit_scraper drift: {drift} — run scripts/sync_reddit_scraper.py")
    if check:
        print("reddit_scraper in sync")


if __name__ == "__main__":
    main(check="--check" in sys.argv)
