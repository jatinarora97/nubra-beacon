from __future__ import annotations

import pandas as pd
import streamlit as st

from _shared import api_get, feedback_widget, page

page("Broker issues", "🔥")

broker = st.sidebar.text_input("Broker filter (e.g. zerodha)") or None
rows = api_get("/issues", broker=broker)
if not rows:
    st.info("No broker issues in the window.")
    st.stop()

for r in rows:
    total = sum(d["count"] for d in r["day_counts"])
    sev = f" · severity {r['severity']:.1f}" if r.get("severity") else ""
    with st.expander(f"**{r['broker']}** · {r['issue_key']} — {total} complaint(s){sev}"):
        df = pd.DataFrame(r["day_counts"])
        st.line_chart(df.set_index("day")["count"], color="#E4574C")
        if r.get("sample_item_ids"):
            st.caption(f"sample items: {r['sample_item_ids'][:5]}")

matrix = pd.DataFrame(
    [{"broker": r["broker"], "issue": r["issue_key"],
      "count": sum(d["count"] for d in r["day_counts"])} for r in rows]
).pivot_table(index="broker", columns="issue", values="count", fill_value=0)
st.subheader("Broker × issue matrix")
st.dataframe(matrix, use_container_width=True)

feedback_widget({"kind": "page", "page": "broker_issues"})
