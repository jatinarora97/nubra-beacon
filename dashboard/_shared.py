"""Dashboard shared helpers — API access + theme + feedback widget.

ALL data comes from the read-API over HTTP (CM_API_BASE). No DB access here.
"""
from __future__ import annotations

import os

import httpx
import streamlit as st

API = os.getenv("CM_API_BASE", "http://127.0.0.1:8400/api/v1")

CSS = """
<style>
.block-container {padding-top: 2.2rem; max-width: 1150px;}
h1, h2, h3 {letter-spacing: -0.01em;}
[data-testid="stMetricValue"] {color: #6EA8FE;}
a {color: #6EA8FE;}
.stButton button[kind="primary"] {background: #2E6FF2; border: 0;}
div[data-testid="stSidebarNav"]::before {
  content: "📡 Nubra Community"; display: block; padding: 0.8rem 1rem 0.4rem;
  font-weight: 700; color: #6EA8FE; font-size: 1.05rem;
}
</style>
"""


def page(title: str, icon: str = "📡") -> None:
    st.set_page_config(page_title=f"{title} · Nubra Community", page_icon=icon,
                       layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    st.title(f"{icon} {title}")


@st.cache_data(ttl=300, show_spinner=False)
def api_get(path: str, **params) -> list | dict:
    r = httpx.get(f"{API}{path}",
                  params={k: v for k, v in params.items() if v not in (None, "", [])},
                  timeout=20)
    r.raise_for_status()
    return r.json()


def api_post(path: str, body: dict) -> tuple[bool, str]:
    try:
        r = httpx.post(f"{API}{path}", json=body, timeout=20)
        if r.status_code >= 400:
            return False, r.json().get("detail", r.text)[:200]
        return True, "ok"
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:200]


def feedback_widget(object_ref: dict) -> None:
    with st.sidebar.expander("💬 Feedback on this page"):
        cat = st.selectbox("Category", ["useful", "not_useful", "wrong", "idea"],
                           key=f"fb_cat_{object_ref}")
        txt = st.text_area("Details (optional)", key=f"fb_txt_{object_ref}")
        if st.button("Send", key=f"fb_btn_{object_ref}"):
            ok, msg = api_post("/feedback", {"object_ref": object_ref,
                                             "category": cat, "free_text": txt or None})
            st.success("Thanks — recorded.") if ok else st.error(msg)
