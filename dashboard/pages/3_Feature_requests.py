from __future__ import annotations

import streamlit as st

from _shared import api_get, feedback_widget, page

page("Feature requests", "✨")

min_days = st.sidebar.slider("Requested on ≥ N days", 1, 7, 1)
rows = api_get("/features", min_days=min_days)
if not rows:
    st.info("Nothing crossed the bar in the window.")
    st.stop()

for r in rows:
    days = r["days_requested"]
    persist = f"requested on {days} of the last 7 days" if days > 1 else "single-day"
    brokers = (" · also asked of: " + ", ".join(b for b in (r.get("brokers_mentioned") or []) if b)
               if any(r.get("brokers_mentioned") or []) else "")
    st.markdown(f"- **{r['label']}** — {r['count']} mention(s) · _{persist}_{brokers}")

feedback_widget({"kind": "page", "page": "feature_requests"})
