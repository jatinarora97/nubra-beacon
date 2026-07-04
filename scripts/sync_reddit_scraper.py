"""Vendor the zanshash/reddit_scraper into community/lib/reddit_scraper/.

Source of truth: github.com/zanshash/reddit_scraper (local checkout at
poc/reference/reddit_scraper — `git pull` there first to update). Rewrites the
two flat imports to package-relative and stamps provenance. Re-run to refresh;
--check for CI drift detection.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

SRC = pathlib.Path(__file__).resolve().parent.parent / "poc" / "reference" / "reddit_scraper"
DEST = pathlib.Path(__file__).resolve().parent.parent / "community" / "lib" / "reddit_scraper"
FILES = ["scraper.py", "models.py", "config.py"]


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
        header = (f"# VENDORED from github.com/zanshash/reddit_scraper @ {commit}\n"
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
