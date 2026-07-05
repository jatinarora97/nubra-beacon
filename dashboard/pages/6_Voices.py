from __future__ import annotations

import streamlit as st

from _shared import api_get, feedback_widget, page

page("Rising voices", "🔊")

rows = api_get("/voices", limit=25)
if not rows:
    st.info("Not enough author history yet.")
    st.stop()

st.caption("Accounts worth building relationships with — consistent, relevant, broad.")
for v in rows:
    flag = " ⚠️ authenticity flagged" if v.get("authenticity_flag") else ""
    st.markdown(
        f"- [@{v['handle']}]({v['profile_url']}) · {v['source']} · "
        f"{v['contributions']} contribution(s){flag}")

feedback_widget({"kind": "page", "page": "voices"})
