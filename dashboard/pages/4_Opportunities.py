from __future__ import annotations

import streamlit as st

from _shared import api_get, api_post, feedback_widget, page

page("Opportunities", "🎯")

REASONS = ["not_relevant", "already_handled", "too_late", "too_risky", "other"]

status = st.sidebar.selectbox("Status", ["suggested", "acted", "dismissed"], index=0)
min_p = st.sidebar.slider("Min score", 0, 100, 40)
rows = api_get("/opportunities", status=status, min_priority=min_p, limit=50)
if not rows:
    st.info("No opportunities match the filters.")
    st.stop()

for n, o in enumerate(rows, 1):
    insight = o.get("insight") or {}
    kind = (insight.get("kind") or "thread").replace("_", " ")
    inter = insight.get("interactions", "?")
    head = f"Priority {n} — {kind} · {inter} interactions · score {o['priority']}/100"
    with st.container(border=True):
        st.markdown(f"#### {head}")
        if o.get("title"):
            st.markdown(f"> {o['title']}")
        cols = st.columns([3, 2])
        with cols[0]:
            if o.get("url"):
                st.markdown(f"[open thread ↗]({o['url']})")
            if o.get("recommended_timing"):
                t = o["recommended_timing"]
                st.caption(f"when: {t.get('action', '')} {t.get('window', '')} — {t.get('why', '')}")
            if o.get("brand_reply"):
                st.markdown("**🏢 Brand draft**")
                st.code(o["brand_reply"], language=None)   # code block = copy button
                st.markdown("**🧑 Rep draft**")
                st.code(o["rep_reply"], language=None)
            else:
                st.caption("no drafts (below draft bar or gated)")
        with cols[1]:
            if o["status"] == "suggested":
                if st.button("✅ Acted", key=f"act{o['id']}", type="primary"):
                    ok, msg = api_post(f"/opportunities/{o['id']}/status", {"status": "acted"})
                    st.success("Marked acted") if ok else st.error(msg)
                    api_get.clear()
                reason = st.selectbox("Dismiss reason", REASONS, key=f"rsn{o['id']}")
                if st.button("🗑 Dismiss", key=f"dis{o['id']}"):
                    ok, msg = api_post(f"/opportunities/{o['id']}/status",
                                       {"status": "dismissed", "dismissed_reason": reason})
                    st.success("Dismissed") if ok else st.error(msg)
                    api_get.clear()
            else:
                st.caption(f"status: {o['status']}"
                           + (f" ({o['dismissed_reason']})" if o.get("dismissed_reason") else ""))

feedback_widget({"kind": "page", "page": "opportunities"})
