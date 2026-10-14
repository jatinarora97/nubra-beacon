"""Compare Reddit actors on Apify with one small capped job each. See community/scrape/apify_compare.py."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from community.scrape.apify_compare import main

if __name__ == "__main__":
    sys.exit(main())
