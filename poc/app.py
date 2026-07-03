#!/usr/bin/env python3
"""Social Pulse — visual dashboard.

Run:  streamlit run app.py

Walks the pipeline stage-by-stage so you can SEE: what's fetched, what the LLM does
(prompt + raw response + token usage), and how trends are scored.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

_NOW = datetime.now(timezone.utc)


def _age(dt):
    try:
        return round((_NOW - dt).total_seconds() / 60)
    except Exception:
        return None

ROOT = Path(__file__).resolve().parent


# ---- tiny .env loader (no extra dependency) ---------------------------------
def _load_env():
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


_load_env()

import yaml  # noqa: E402

from social_pulse.schema import connect, upsert_items, load_items, store_counts  # noqa: E402
from social_pulse.pipeline.dedupe import dedupe  # noqa: E402
from social_pulse.pipeline.prefilter import prefilter  # noqa: E402
from social_pulse.pipeline.classify import classify_with_meta  # noqa: E402
from social_pulse.pipeline.trend import rank_topics  # noqa: E402
from social_pulse.pipeline import brief as brief_mod  # noqa: E402
from social_pulse.pipeline import actions as actions_mod  # noqa: E402
from social_pulse.pipeline import influencers as voices_mod  # noqa: E402


def load_config() -> dict:
    for name in ("config.yaml", "config.example.yaml"):
        p = ROOT / name
        if p.exists():
            return yaml.safe_load(p.read_text()) or {}
    return {}


def ingest(sources, cfg):
    items = []
    for s in sources:
        if s == "reddit":
            from social_pulse.sources.reddit import fetch_reddit
            items += fetch_reddit(cfg)
        elif s == "telegram":
            from social_pulse.sources.telegram import fetch_telegram
            items += fetch_telegram(cfg)
        elif s == "twitter":
            # interim: read the vetted CSV (refresh it with `python fetch_twitter_csv.py`).
            from social_pulse.sources.twitter import load_twitter_csv
            items += load_twitter_csv(cfg)
    return items


# ============================ UI ============================
st.set_page_config(page_title="Social Pulse", page_icon="📡", layout="wide")
st.title("📡 Social Pulse — Indian Market Community Radar")
st.caption("F&O · API/algo traders · AI-trading devs — scrape → store → dedupe → filter → LLM classify → trend → act")

cfg = load_config()

from social_pulse.sources.reddit import DEFAULT_SUBS, SUB_GROUPS  # noqa: E402

_LLM_ON = bool(os.environ.get("ANTHROPIC_API_KEY"))

# persistent store header — accumulated across every run
_store = store_counts(connect())

with st.sidebar:
    st.header("Run")
    st.caption(f"🗄️ Store: **{_store['total']}** items on disk "
               f"({', '.join(f'{k}:{v}' for k, v in _store['by_source'].items()) or 'empty'})")
    sources = st.multiselect(
        "Live sources", ["reddit", "twitter", "telegram"], default=["reddit"],
        help="Real scrapes only — no demo data. Reddit via Playwright; X via twitterapi.io.",
    )
    stored_only = st.toggle(
        "Analyze stored data only (no new scrape)", value=False,
        help="Skip fetching — re-run the pipeline on what's already in the store. Zero API spend.",
    )

    # LLM status chip — key comes from .env only (no in-app key entry).
    if _LLM_ON:
        st.caption("🤖 Haiku enrichment **on** (key from `.env`)")
    else:
        st.caption("⚠️ No `ANTHROPIC_API_KEY` in `.env` — classification quality reduced")

    rc = cfg.setdefault("reddit", {})
    subs = list(rc.get("subreddits", DEFAULT_SUBS))
    days = int(rc.get("days", 7))
    if "reddit" in sources:
        st.divider()
        st.subheader("Reddit (live scrape)")
        preselected = set(rc.get("subreddits", DEFAULT_SUBS))

        st.markdown("**Subreddits** — tick the communities to scan")
        subs = []
        for group, group_subs in SUB_GROUPS.items():
            with st.expander(group, expanded=any(s in preselected for s in group_subs)):
                for s in group_subs:
                    if st.checkbox(f"r/{s}", value=s in preselected, key=f"sub_{s}"):
                        subs.append(s)
        if not subs:
            st.warning("Pick at least one subreddit.")

        listings = st.multiselect("Sort feeds", ["hot", "rising", "new"],
                                  default=rc.get("listings", ["hot", "rising"]),
                                  help="'rising' is the strongest free pulse signal")
        days = st.slider("Look back (days, 0 = no limit)", 0, 30,
                         int(rc.get("days", 7)),
                         help="Scrape window AND the working-set window read back from the store.")
        posts_per = st.slider("Posts per feed", 3, 40, int(rc.get("limit_per_listing", 10)))
        comments_per = st.slider("Comments per post", 0, 40, int(rc.get("comment_limit", 12)))
        rc.update({"subreddits": subs, "listings": listings, "days": days,
                   "limit_per_listing": posts_per, "comment_limit": comments_per,
                   "fetch_comments": comments_per > 0})
        est = max(1, len(subs)) * max(1, len(listings)) * posts_per
        window = "all time" if days == 0 else f"last {days}d"
        st.caption(f"≈ {est} posts × (1 + {comments_per} comments) · {window} — "
                   f"a real browser scrape; expect ~1–4 min.")

    tw = cfg.setdefault("twitter", {})
    if "twitter" in sources:
        st.divider()
        st.subheader("Twitter / X (CSV-backed)")
        from social_pulse.sources.twitter import CSV_PATH  # noqa: E402
        if CSV_PATH.exists():
            import csv as _csv
            with open(CSV_PATH, encoding="utf-8") as _f:
                _n = sum(1 for _ in _csv.reader(_f)) - 1
            st.caption(f"📄 Reading **{max(_n, 0)}** vetted tweets from `data/{CSV_PATH.name}` — "
                       f"no API spend in-app.")
        else:
            st.warning("No tweet CSV yet — run `python fetch_twitter_csv.py` to fetch & vet.")
        st.caption("Refresh the data offline: `python fetch_twitter_csv.py` "
                   "(live twitterapi.io fetch, budget-capped).")

    st.divider()
    btn_label = "📊 Analyse stored data" if stored_only else "▶ Scrape & analyse"
    run = st.button(btn_label, type="primary", use_container_width=True)

if not run:
    st.info("Pick sources + communities in the sidebar, then hit **Scrape & analyse**. "
            "Each run scrapes live data, appends it to the on-disk store (de-duplicated), "
            "and analyses the full accumulated window — no demo data.")
    st.stop()

if not sources:
    st.error("Select at least one live source in the sidebar.")
    st.stop()

# working-set window: reddit slider drives it, but for an X-only run use the X window
window_days = days
if "twitter" in sources and "reddit" not in sources:
    window_days = int(cfg.get("twitter", {}).get("days", 7))

# ---------------- pipeline ----------------
with st.status("Running pipeline…", expanded=True) as status:
    con = connect()
    src_label = ", ".join(sources)
    if stored_only:
        fetched, new_rows = [], 0
        status.write(f"🗄️ **Stored-data-only** — skipping scrape (no API spend). Source(s): {src_label}")
    else:
        status.write(f"📥 Fetching live from **{src_label}** … (Reddit scrape is a few minutes)")
        fetched = ingest(sources, cfg)
        new_rows = upsert_items(con, fetched)
        status.write(f"   fetched **{len(fetched)}** items → **{new_rows}** new stored "
                     f"({len(fetched) - new_rows} already on disk)")
    # analyse the FULL accumulated store within the window, not just this batch
    items = load_items(con, days=window_days, sources=sources)
    status.write(f"🗄️ Working set from store: **{len(items)}** items (last {window_days or '∞'}d)")
    if not items:
        status.update(label="Nothing to analyse", state="error")
        st.stop()
    groups = dedupe(items)
    status.write(f"🧹 Deduped → **{len(groups)}** unique")
    kept = prefilter(groups, cfg)
    status.write(f"🔎 Prefiltered → **{len(kept)}** relevant")
    status.write("🤖 Classifying with Haiku …")
    classified, llm_meta = classify_with_meta(kept)
    status.write(f"   classifier: **{llm_meta['method']}**")
    ranked = rank_topics(classified, cfg)
    status.write(f"📈 Ranked **{len(ranked)}** rising topics")
    status.write("🎯 Building marketing action plans …")
    action_plans = actions_mod.build_actions(ranked, cfg)
    action_plans, actions_meta = actions_mod.enrich_with_llm(action_plans)
    status.write(f"   actions: **{actions_meta['method']}** for {len(action_plans)} topics")
    status.write("🌟 Scouting rising voices …")
    voices = voices_mod.find_rising_voices(items, cfg)
    voices, voices_meta = voices_mod.enrich_with_llm(voices)
    status.write(f"   found **{len(voices)}** candidate voices")
    status.update(label="Pipeline complete ✅", state="complete", expanded=False)

stats = {"scraped": len(fetched), "new_stored": new_rows, "ingested": len(items),
         "unique": len(groups), "relevant": len(kept)}

# ---------------- top metrics ----------------
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Scraped now", stats["scraped"], delta=f"+{stats['new_stored']} new")
c2.metric("Working set", stats["ingested"], help="Stored items in the analysis window")
c3.metric("Unique (deduped)", stats["unique"], delta=stats["unique"] - stats["ingested"])
c4.metric("Relevant", stats["relevant"], delta=stats["relevant"] - stats["unique"])
c5.metric("Rising topics", len(ranked))
c6.metric("Classifier", "Haiku" if llm_meta["method"] == "llm" else "keyword")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["1️⃣ Fetched & deduped", "2️⃣ Noise filter", "3️⃣ 🤖 LLM", "4️⃣ 📈 Trends",
     "5️⃣ 🎯 Actions", "6️⃣ 🌟 Rising Voices"]
)

# ---- Tab 1: fetched & deduped ----
with tab1:
    st.subheader("What we fetched — ground data")
    rows = []
    for it in items:
        raw = it.raw or {}
        rows.append({
            "source": it.source,
            "subreddit": raw.get("subreddit") or "",
            "type": it.source_type,
            "author": it.author,
            "score": it.engagement.get("score", 0),
            "comments": it.engagement.get("replies", 0),
            "upvote_ratio": it.engagement.get("upvote_ratio"),
            "age_min": _age(it.created_at),
            "flair": raw.get("flair") or "",
            "text": it.text,
            "link": it.url or "",
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        left, right = st.columns([1, 2])
        with left:
            st.markdown("**Items per source**")
            st.bar_chart(df["source"].value_counts())
            if (df["subreddit"] != "").any():
                st.markdown("**Per subreddit**")
                st.bar_chart(df[df["subreddit"] != ""]["subreddit"].value_counts())
        with right:
            st.markdown("**Every item fetched — click `link` to open the exact post**")
            st.dataframe(
                df, use_container_width=True, height=380, hide_index=True,
                column_config={
                    "text": st.column_config.TextColumn(width="large"),
                    "link": st.column_config.LinkColumn("link", display_text="↗ open"),
                    "upvote_ratio": st.column_config.NumberColumn(format="%.2f"),
                    "age_min": st.column_config.NumberColumn("age (min)"),
                },
            )

    st.subheader("Dedupe — collapsing cross-posted duplicates")
    dupes = [g for g in groups if len(g.members) > 1]
    if dupes:
        st.markdown(f"**{len(dupes)} duplicate cluster(s)** collapsed "
                    f"(same content pasted in multiple places):")
        for g in dupes:
            srcs = ", ".join(sorted(g.sources))
            st.warning(f"×{len(g.members)} copies across **{srcs}** "
                       f"(spread={g.spread}) — “{g.representative.text[:120]}”")
    else:
        st.caption("No duplicates in this batch.")

# ---- Tab 2: prefilter ----
with tab2:
    st.subheader("Cheap relevance gate (no LLM spend)")
    kept_hashes = {g.representative.hash for g in kept}
    dropped = [g for g in groups if g.representative.hash not in kept_hashes]
    cc1, cc2 = st.columns(2)
    with cc1:
        st.success(f"✅ Kept {len(kept)} relevant")
        st.dataframe(pd.DataFrame([{"source": g.representative.source,
                                    "text": g.representative.text} for g in kept]),
                     use_container_width=True, height=280)
    with cc2:
        st.error(f"🗑️ Dropped {len(dropped)} (off-topic / too short)")
        st.dataframe(pd.DataFrame([{"source": g.representative.source,
                                    "text": g.representative.text} for g in dropped]),
                     use_container_width=True, height=280)
    st.caption(f"Keywords gate from config: {', '.join(cfg.get('prefilter', {}).get('keywords', [])[:12])} …")

# ---- Tab 3: LLM ----
with tab3:
    st.subheader("What the LLM is doing")
    method = llm_meta["method"]
    if method == "llm":
        u = llm_meta.get("usage", {})
        m1, m2, m3 = st.columns(3)
        m1.metric("Model", "claude-haiku-4.5")
        m2.metric("Input tokens", u.get("input_tokens", "—"))
        m3.metric("Output tokens", u.get("output_tokens", "—"))
        with st.expander("📤 Exact prompt sent to Haiku"):
            st.code(llm_meta.get("prompt", ""), language="text")
        with st.expander("📥 Raw model response"):
            st.code(llm_meta.get("raw_response", ""), language="json")
    else:
        st.warning(f"Running **keyword fallback** (no/failed API key). "
                   f"{llm_meta.get('error', 'Add an Anthropic key in the sidebar for Haiku.')}")

    st.markdown("**Per-item classification**")
    cdf = pd.DataFrame([{
        "audience": c["audience"], "topic": c["topic"], "sentiment": c["sentiment"],
        "noise": "🔇" if c.get("is_noise") else "",
        "text": c["group"].representative.text,
    } for c in classified])
    st.dataframe(cdf, use_container_width=True, height=300)

    cc1, cc2 = st.columns(2)
    with cc1:
        st.markdown("**Audience mix**")
        st.bar_chart(cdf["audience"].value_counts())
    with cc2:
        st.markdown("**Sentiment**")
        st.bar_chart(cdf["sentiment"].value_counts())

# ---- Tab 4: trends ----
with tab4:
    st.subheader("Rising topics — velocity × cross-source spread × audience weight")
    if not ranked:
        st.info("No rising topics in this batch.")
    else:
        rdf = pd.DataFrame([{"topic": r["topic"], "score": r["score"],
                             "mentions": r["mentions"], "spread": r["spread"],
                             "audience": r["audience"], "sentiment": r["sentiment"]}
                            for r in ranked])
        st.bar_chart(rdf.set_index("topic")["score"])
        st.dataframe(rdf, use_container_width=True)

        st.markdown("### 📰 Daily brief — suggested post angles")
        for i, r in enumerate(ranked, 1):
            spread_tag = f" · ⚡cross-source ×{r['spread']}" if r["spread"] > 1 else ""
            with st.container(border=True):
                st.markdown(f"**{i}. {r['topic']}**  ·  score `{r['score']}`  ·  "
                            f"audience `{r['audience']}`  ·  sentiment `{r['sentiment']}`{spread_tag}")
                for ex in r["examples"]:
                    src = ex.get("subreddit") or ex["source"]
                    link = f"  [↗ open]({ex['url']})" if ex.get("url") else ""
                    st.markdown(f"- “{ex['text']}” — *{src}* · score {ex.get('score', 0)}{link}")
                st.info(f"→ **Post angle:** {brief_mod._suggest_angle(r)}")
                members = r.get("members", [])
                with st.expander(f"🔎 Ground data — all {len(members)} source item(s) behind this topic"):
                    mdf = pd.DataFrame(members)
                    if not mdf.empty:
                        st.dataframe(
                            mdf, use_container_width=True, hide_index=True,
                            column_config={
                                "text": st.column_config.TextColumn(width="large"),
                                "url": st.column_config.LinkColumn("link", display_text="↗ open"),
                            },
                        )

    # persist brief
    payload = brief_mod.to_payload(ranked, stats)
    brief_mod.save_brief(con, payload)
    st.download_button("⬇ Download brief JSON",
                       data=json.dumps(payload, indent=2, default=str),
                       file_name=f"brief-{payload['date']}.json", mime="application/json")

# ---- Tab 5: actions ----
with tab5:
    st.subheader("🎯 What to act on — and how")
    st.caption("Each rising topic → a recommended play + a format menu (infographic · "
               "educational · reel · open-source · community), backed by the numbers. "
               "Built for the community manager / brand builder, not just the analyst.")
    if not action_plans:
        st.info("No topics to act on in this batch.")
    else:
        # priority board
        board = pd.DataFrame([{
            "priority": p["priority"], "topic": p["topic"],
            "primary play": p["primary"], "audience": p["audience"],
            "sentiment": p["sentiment"], "mentions": p["mentions"],
            "communities": p["spread"], "channels": ", ".join(p["channels"][:3]),
        } for p in action_plans])
        st.markdown("**Priority board** — triage at a glance")
        st.dataframe(board, use_container_width=True, hide_index=True)

        if actions_meta.get("method") == "llm":
            st.caption("✍️ Hooks & captions below ghost-written by Haiku.")

        for i, p in enumerate(action_plans, 1):
            with st.container(border=True):
                spread_tag = f" · ⚡{p['spread']} communities" if (p["spread"] or 0) > 1 else ""
                st.markdown(f"### {i}. {p['topic']}  ·  {p['priority']}")
                st.markdown(f"**Why now:** {p['rationale']}{spread_tag}")
                st.markdown(f"📡 **Channels:** {' · '.join(p['channels'])}")

                copy = p.get("copy") or {}
                if copy.get("headline"):
                    st.success(f"**Headline:** {copy['headline']}")
                if copy.get("caption"):
                    st.markdown(f"> {copy['caption']}")
                if copy.get("hashtags"):
                    st.caption(" ".join(copy["hashtags"]))

                st.markdown(f"**▶ Recommended first move: `{p['primary']}`**")
                cols = st.columns(len(p["plays"]))
                for col, play in zip(cols, p["plays"]):
                    is_primary = play["format"] == p["primary"]
                    with col:
                        flag = "⭐ " if is_primary else ""
                        st.markdown(f"{play['icon']} **{flag}{play['format']}**")
                        st.markdown(play["title"])
                        st.caption(play["hook"])
                        st.caption(f"effort `{play['effort']}` · impact `{play['impact']}`")
                # surface any LLM-specific creative ideas
                ideas = [(k, copy.get(k)) for k in ("infographic", "reel") if copy.get(k)]
                if ideas:
                    with st.expander("✨ LLM creative ideas"):
                        for k, v in ideas:
                            st.markdown(f"- **{k.title()}:** {v}")

        st.download_button(
            "⬇ Download action plan JSON",
            data=json.dumps(action_plans, indent=2, default=str),
            file_name=f"actions-{payload['date']}.json", mime="application/json",
            key="dl_actions",
        )

# ---- Tab 6: rising voices ----
with tab6:
    st.subheader("🌟 Rising Voices — the next finfluencers / advocates")
    st.caption("Different methodology from topic-trending: we score **people** on "
               "relevance × quality × audience × (reach + consistency + breadth). "
               "Regulars who post on-topic, get heard, and span communities float to the top.")
    if not voices:
        st.info("No qualifying voices (need ≥2 on-topic contributions). Try a wider scrape "
                "or more days.")
    else:
        vdf = pd.DataFrame([{
            "author": v["author"], "score": v["score"], "audience": v["audience"],
            "contributions": v["contributions"], "posts": v["posts"],
            "comments": v["comments"], "communities": v["communities"],
            "avg_score": v["avg_engagement"], "relevance": v["relevance"],
            "quality": v["quality"],
        } for v in voices])
        st.bar_chart(vdf.head(15).set_index("author")["score"])
        st.dataframe(vdf, use_container_width=True, hide_index=True)

        if voices_meta.get("method") == "llm":
            st.caption("🧠 Archetype / why / outreach below judged by Haiku.")

        st.markdown("### Shortlist — who to engage")
        for v in voices[:12]:
            with st.container(border=True):
                head = f"**u/{v['author']}**  ·  score `{v['score']}`  ·  `{v['audience']}`"
                if v.get("archetype"):
                    head += f"  ·  *{v['archetype']}*"
                st.markdown(head)
                c = v["components"]
                st.caption(
                    f"{v['contributions']} contributions ({v['posts']}p/{v['comments']}c) · "
                    f"{v['communities']} communities · avg score {v['avg_engagement']} · "
                    f"relevance {v['relevance']} · quality {v['quality']}  |  "
                    f"reach {c['reach']} · consistency {c['consistency']} · breadth {c['breadth']}"
                )
                if v.get("why"):
                    st.markdown(f"**Why:** {v['why']}")
                if v.get("outreach"):
                    st.info(f"🤝 **Outreach:** {v['outreach']}")
                if v.get("subreddits"):
                    st.caption("Active in: " + ", ".join(v["subreddits"]))
                bi = v.get("best_item") or {}
                if bi.get("text"):
                    link = f"  [↗ open]({bi['url']})" if bi.get("url") else ""
                    st.markdown(f"🏅 Top item (score {bi.get('score', 0)}): “{bi['text']}”{link}")
                with st.expander(f"🔎 Sample contributions from u/{v['author']}"):
                    sdf = pd.DataFrame(v.get("samples", []))
                    if not sdf.empty:
                        st.dataframe(
                            sdf, use_container_width=True, hide_index=True,
                            column_config={
                                "text": st.column_config.TextColumn(width="large"),
                                "url": st.column_config.LinkColumn("link", display_text="↗ open"),
                            },
                        )

        st.download_button(
            "⬇ Download rising voices JSON",
            data=json.dumps(voices, indent=2, default=str),
            file_name=f"voices-{payload['date']}.json", mime="application/json",
            key="dl_voices",
        )
