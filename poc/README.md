# Social Pulse (standalone prototype)

A **self-contained** experiment that captures Indian stock-market community chatter
(F&O, API/algo traders, AI-trading devs), filters the noise, and prints a daily
**"rising topics" brief**.

> This is independent of the `nubra-ai-personalization` repo on purpose. It imports
> nothing from it and writes to its own local SQLite file (`pulse.db`). Throwaway —
> we use it to see how the idea behaves before deciding what to productionize.

> **Real data only.** There is no demo/synthetic mode. Every run scrapes live, appends
> what it finds to the on-disk store (`pulse.db`, de-duplicated by id *and* content
> hash), then analyses the full accumulated window — so the picture compounds across runs.

## Setup

```bash
cd social-pulse
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install playwright anthropic && playwright install chromium   # live scrape + LLM
cp config.example.yaml config.yaml      # edit subreddits / window / keywords
# LLM (Haiku enrichment): put ANTHROPIC_API_KEY in .env  (no in-app key entry)
```

## Run

```bash
python run.py --sources reddit            # live Reddit scrape (Playwright)
python run.py --sources reddit --days 14  # scrape + analysis window
streamlit run app.py                      # interactive dashboard (recommended)
```

In the dashboard: tick the communities (grouped checkboxes incl. Zerodha/dhan/smallcase/
Upstox/groww + F&O/algo/dev subs), set the look-back window, then **Scrape & analyse**.

## What it does

1. **Scrape** — live Reddit via the Playwright scraper → common `RawItem`s.
2. **Store** — append to `pulse.db`; skip anything already saved (id + content-hash dedup).
3. **Load** — read the accumulated store within the last-N-days window (the working set).
4. **Dedupe** — near-dup collapse with cross-source spread tracked.
5. **Prefilter** — cheap keyword relevance gate, no LLM spend.
6. **Classify** — Haiku batch (audience / topic / sentiment / is_noise).
7. **Trend** — rank topics by velocity × cross-source spread × audience weight.
8. **Actions** — per-trend marketing playbook (infographic · educational · reel ·
   open-source/GitHub · community engagement) with a recommended first move, channels,
   and data-backed rationale — Haiku ghost-writes the copy.
9. **Rising Voices** — score *people* (relevance × quality × audience × reach +
   consistency + breadth) to surface the next finfluencers / advocates to engage.

See `docs/social-pulse-architecture-2026-06-14.md` for the full design and how this
would later feed the production `intelligence_store`. The reference Reddit scraper we
build on top of lives in `reference/reddit_scraper/`.
