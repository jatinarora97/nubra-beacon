from __future__ import annotations

import streamlit as st

from _shared import api_get, feedback_widget, page

page("Drill-down", "🔍")

with st.sidebar:
    source = st.selectbox("Source", ["", "twitter", "reddit"]) or None
    intent = st.selectbox("Intent", ["", "complaint", "feature_request", "question",
                                     "praise", "comparison", "how_to", "news_opinion"]) or None
    audience = st.selectbox("Audience", ["", "active_trader", "long_term_investor",
                                         "beginner", "influencer", "other"]) or None
    topic = st.text_input("Topic key") or None
    broker = st.text_input("Broker") or None
    q = st.text_input("Text search") or None
    limit = st.slider("Rows", 10, 100, 25)

rows = api_get("/items", source=source, intent=intent, audience=audience,
               topic=topic, broker=broker, q=q, limit=limit)
st.caption(f"{len(rows)} canonical item(s)")

for r in rows:
    dup = f" · {r['duplicate_count']} duplicate(s)" if r.get("duplicate_count") else ""
    label = (f"[{r['source']}] {r.get('intent') or '—'} · {r.get('topic_key') or '—'} · "
             f"@{r['author']}{dup}")
    with st.expander(label):
        st.markdown(f"> {r['text']}")
        st.caption(f"{r['created_at']} · engagement {r.get('engagement', {})}")
        if r.get("url"):
            st.markdown(f"[open ↗]({r['url']})")
        if st.button("Load thread detail", key=f"det{r['source']}{r['external_id']}"):
            d = api_get(f"/items/{r['source']}/{r['external_id']}")
            st.json(d["item"].get("entities") or {})
            st.markdown(f"**{len(d['thread_siblings'])} sibling(s) in thread**")
            for s in d["thread_siblings"][:10]:
                st.markdown(f"- _{s['source_type']}_ @{s['author']}: {s['text']}")

feedback_widget({"kind": "page", "page": "drill_down"})
