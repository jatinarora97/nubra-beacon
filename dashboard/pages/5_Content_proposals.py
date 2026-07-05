from __future__ import annotations

import streamlit as st

from _shared import api_get, feedback_widget, page

page("Content proposals", "🎬")

rows = api_get("/content-proposals")
if not rows:
    st.info("No proposals yet — run the draft stage.")
    st.stop()

st.caption(f"for {rows[0]['day']}")
for c in rows:
    with st.container(border=True):
        st.markdown(f"#### #{c['rank']} · {c['format'].upper()}")
        st.markdown(f"**Hook:** {c['hook']}")
        brief = c.get("outline") or {}
        if isinstance(brief, dict):
            for i, b in enumerate(brief.get("beats", []), 1):
                st.markdown(f"{i}. {b}")
            if brief.get("caption"):
                st.markdown("**Caption (paste-ready)**")
                st.code(brief["caption"], language=None)
            meta = []
            if brief.get("hashtags"):
                meta.append(" ".join(brief["hashtags"]))
            if brief.get("cta"):
                meta.append(f"CTA: {brief['cta']}")
            if brief.get("visual_direction"):
                meta.append(f"Visual: {brief['visual_direction']}")
            for m in meta:
                st.caption(m)
        else:
            st.markdown(" → ".join(brief))
        w = (c.get("recommended_timing") or {}).get("window", "flexible")
        st.caption(f"why: {c.get('why', '-')} · window: {w} · rides: {c.get('rides_signal')}")

feedback_widget({"kind": "page", "page": "content_proposals"})
