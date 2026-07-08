"""Vendor the zanshash/reddit_scraper into community/lib/reddit_scraper/.

Source of truth: github.com/zanshash/reddit_scraper (local checkout at
.vendor/reddit_scraper, auto-cloned on first run — `git pull` there to update).
Rewrites the two flat imports to package-relative, applies the NESTED-REPLIES
patch (below), and stamps provenance. Re-run to refresh; --check for CI drift.

Nested-replies patch: upstream collects top-level comments only. We addition-
ally walk ONE nested level per top comment (strict child chain
`> div.child > div.sitetable > div.thing.comment`, cap 3 replies) and carry
them as Comment.replies. Applied here — never hand-edit the vendored copy.
If upstream refactors fetch_comments/models the anchors below fail loudly.
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

PATCHES = {
    "models.py": [(_MODELS_FIELD_OLD, _MODELS_FIELD_NEW),
                  (_MODELS_DICT_OLD, _MODELS_DICT_NEW)],
    "scraper.py": [(_SCRAPER_APPEND_OLD, _SCRAPER_APPEND_NEW),
                   (_SCRAPER_SKIP_OLD, _SCRAPER_SKIP_NEW),
                   (_SCRAPER_GLOBAL_OLD, _SCRAPER_GLOBAL_NEW)],
}


def main(check: bool = False) -> None:
    commit = subprocess.run(
        ["git", "-C", str(SRC), "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True).stdout.strip() or "unknown"
    DEST.mkdir(parents=True, exist_ok=True)
    outputs = {DEST / "__init__.py": ""}
    for name in FILES:
        body = (SRC / name).read_text()
        body = body.replace("from config import", "from .config import")
        body = body.replace("from models import", "from .models import")
        for anchor, replacement in PATCHES.get(name, []):
            if anchor not in body:
                raise SystemExit(
                    f"nested-replies patch anchor missing in upstream {name} — "
                    "upstream changed; re-derive the patch or drop it")
            body = body.replace(anchor, replacement)
        header = (f"# VENDORED from github.com/zanshash/reddit_scraper @ {commit}\n"
                  "# (+ nested-replies patch — see this script's docstring)\n"
                  "# Do not edit here; update the source repo, then run "
                  "scripts/sync_reddit_scraper.py\n")
        outputs[DEST / name] = header + body
    drift = []
    for path, content in outputs.items():
        if check:
            if not path.exists() or path.read_text() != content:
                drift.append(path.name)
        else:
            path.write_text(content)
            print(f"vendored: {path.name}")
    if check and drift:
        raise SystemExit(f"reddit_scraper drift: {drift} — run scripts/sync_reddit_scraper.py")
    if check:
        print("reddit_scraper in sync")


if __name__ == "__main__":
    main(check="--check" in sys.argv)
