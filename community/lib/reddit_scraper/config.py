# VENDORED from github.com/zanshash/reddit_scraper @ f926fc7
# (+ nested-replies patch — see this script's docstring)
# Do not edit here; update the source repo, then run scripts/sync_reddit_scraper.py
SUBREDDITS = [
    "IndiaInvestments",
    "IndianStreetBets",
    "IndianStockMarket",
    "IndiaAlgoTrading",
    "DalalStreetTalks",
    "NSEbets",
    "IndiaOptionsSelling",
]

# "top" is treated as Reddit's "Best" (highest-scoring posts of all time)
SORT_TYPES = ["hot", "new"]

POSTS_PER_FEED = 15       # posts to collect per sort type per subreddit
COMMENTS_PER_POST = 100    # top-level comments to collect per post

DOWNLOAD_IMAGES = False    # set False to skip downloading images locally
IMAGES_DIR = "images"
OUTPUT_DIR = "output"

HEADLESS = True     # set False to watch the browser while debugging
MIN_DELAY = 1.5           # seconds – random delay between requests
MAX_DELAY = 3.5
