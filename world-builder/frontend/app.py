"""World Builder - one Streamlit app over the backend API.

Run from the frontend directory, with the backend already running:

    source .venv/bin/activate   # from world-builder/
    cd frontend && streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

import api
from shared.state import init_session_state

st.set_page_config(page_title="World Builder", page_icon="🌍", layout="wide")
init_session_state()

pages = {
    "Assets": [
        st.Page("views/assets/library.py", title="Asset Library", icon="🎨", default=True),
        st.Page("views/assets/create.py", title="Create", icon="✨"),
        st.Page("views/assets/worlds.py", title="Worlds", icon="🌍"),
    ],
}

try:
    st.navigation(pages).run()
except api.ApiError as exc:
    # Anything a page did not handle itself - usually the backend being down.
    st.error(str(exc))
