from __future__ import annotations

import pandas as pd
import streamlit as st

from _shared import api_get, feedback_widget, page

page("Trends", "📈")

window = st.sidebar.radio("Window", ["7d", "1d"], horizontal=True)
rows = api_get("/trends", window=window, limit=20)
if not rows:
    st.info("No trend data in this window.")
    st.stop()

df = pd.DataFrame(rows)
df["label"] = df["label"].fillna(df["topic_key"])
st.bar_chart(df.set_index("label")["count"], horizontal=True, color="#2E6FF2")

st.dataframe(
    df[["label", "count", "velocity_z", "spread", "engagement_sum"]]
    .rename(columns={"label": "topic", "velocity_z": "momentum (z)"}),
    use_container_width=True, hide_index=True)

feedback_widget({"kind": "page", "page": "trends"})
