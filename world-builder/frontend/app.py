"""World Builder UI. Run ``streamlit run app.py`` from ``frontend/`` with the backend running."""

from __future__ import annotations

import streamlit as st

import api
from shared.state import init_session_state

st.set_page_config(page_title="World Builder", page_icon="🌍", layout="wide")
init_session_state()

pages = {
    "World": [
        st.Page("pages/world.py", title="World", icon="🌍", default=True),
        st.Page("pages/create.py", title="Create asset", icon="✨"),
    ],
    "Story": [
        st.Page("pages/episode.py", title="Episode script", icon="📜"),
        st.Page("pages/storyboard.py", title="Storyboard", icon="🎬"),
    ],
    "Settings": [
        st.Page("pages/worlds.py", title="Manage worlds", icon="🗂️"),
    ],
}

try:
    st.navigation(pages).run()
except api.ApiError as exc:
    # Anything a page did not handle itself, usually the backend being down.
    st.error(str(exc))
