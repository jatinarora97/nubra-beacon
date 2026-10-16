"""Preview reply drafts on real recent threads, saving nothing. See community/recommend/preview.py.
(Named for Reddit, where it started; `--source twitter` previews X with the tweet prompt and its 280-character rule.)

    docker compose exec -T api python scripts/preview_reddit_drafts.py                 # 10 newest Reddit opportunities
    docker compose exec -T api python scripts/preview_reddit_drafts.py --n 20 --judge  # more, plus the LLM judge
    docker compose exec -T api python scripts/preview_reddit_drafts.py --opp 12345     # one specific opportunity
    docker compose exec -T api python scripts/preview_reddit_drafts.py --source twitter  # newest X opportunities

Try an edited prompt BEFORE it ships (no image push needed): copy the file in and point at it.

    docker compose cp reply_reddit.txt api:/tmp/reply_reddit.txt
    docker compose exec -T api python scripts/preview_reddit_drafts.py --prompt-file /tmp/reply_reddit.txt

    docker compose cp reply_twitter.txt api:/tmp/reply_twitter.txt
    docker compose exec -T api python scripts/preview_reddit_drafts.py --source twitter --prompt-file /tmp/reply_twitter.txt

Costs one model call per thread (two more per thread with --judge). Nothing is written to opportunities or
compliance_audit; the only database write is the normal LLM-usage meter row of each call.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys

os.environ.setdefault("PGCONNECT_TIMEOUT", "10")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from community.recommend import preview  # noqa: E402
from community.reference import features  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, default=preview.DEFAULT_COUNT, help="how many opportunities to preview")
    ap.add_argument("--opp", type=int, default=None, help="preview this opportunity id only")
    ap.add_argument("--source", default="reddit", help="which source's opportunities, prompt and rules: reddit (default) or twitter")
    ap.add_argument("--prompt-file", default=None, help="use this prompt text instead of the shipped one")
    ap.add_argument("--judge", action="store_true", help="also run the LLM compliance judge (2 extra calls each)")
    args = ap.parse_args()

    catalog = features.catalog_for_prompt()
    if not catalog:
        print("the grounding catalog is empty - nothing to draft from")
        return 1
    try:
        opps = preview.pick(args.source, args.n, args.opp)
    except Exception as e:  # noqa: BLE001
        print(f"could not read the database: {type(e).__name__}: {str(e)[:200]}")
        return 1
    if not opps:
        print(f"no suggested {args.source} opportunities to preview")
        return 0
    system = preview.system_prompt(args.source, args.prompt_file)
    label = args.prompt_file or f"the shipped {args.source} prompt"
    results = [preview.preview_one(o, catalog, system, judge=args.judge) for o in opps]
    print(preview.render(results, label))
    clean = sum(1 for r in results if "drafts" in r and not r["problems"] and not any(r["l1"].values()))
    print(f"\n{len(results)} previewed, {clean} clean on the validator and the regex rules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
