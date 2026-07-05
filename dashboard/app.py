"""Overview — today's roundup rendered, links into every page."""
from __future__ import annotations

import httpx
import streamlit as st

from _shared import api_get, feedback_widget, page

page("Overview")

try:
    r = api_get("/roundups", period="daily")
except httpx.HTTPStatusError:
    st.info("No roundup yet — run `./cm run-local` first.")
    st.stop()

p = r["payload"]
st.caption(f"Daily roundup · {r['date']} · grounding: {p.get('grounding', '?')}")
st.markdown(f"> {p.get('headline', '')}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Trending topics", len(p.get("trending", [])))
c2.metric("Broker issues", len(p.get("broker_issues", [])))
c3.metric("Opportunities", len(p.get("opportunities", [])))
c4.metric("Content proposals", len(p.get("content_proposals", [])))

left, right = st.columns(2)
with left:
    st.subheader("Trending")
    for t in p.get("trending", [])[:8]:
        z = f" · z={t['velocity_z']:.1f}" if t.get("velocity_z") else ""
        st.markdown(f"- **{t.get('label') or t['topic_key']}** — {t['count']} items{z}")
    st.page_link("pages/1_Trends.py", label="→ Trends page")

    st.subheader("Broker issues")
    for i in p.get("broker_issues", [])[:6]:
        st.markdown(f"- **{i['broker']}** · {i['issue_key']} — {i['count']}")
    st.page_link("pages/2_Broker_issues.py", label="→ Broker issues page")

with right:
    st.subheader("Top opportunities")
    for n, o in enumerate(p.get("opportunities", [])[:5], 1):
        kind = (o.get("insight") or o.get("matched_insight") or {}).get("kind", "thread")
        st.markdown(f"**Priority {n}** · {kind.replace('_', ' ')} · score {o['priority']}"
                    + (f" · [{'thread'}]({o['url']})" if o.get("url") else ""))
    st.page_link("pages/4_Opportunities.py", label="→ Opportunities page (act/dismiss)")

    st.subheader("Nubra watch")
    watch = p.get("nubra_watch", [])
    if watch:
        for n in watch:
            st.markdown(f"- “{n['summary']}”")
    else:
        st.caption("no Nubra mentions in the window")

feedback_widget({"kind": "roundup", "period": "daily", "date": str(r["date"])})
