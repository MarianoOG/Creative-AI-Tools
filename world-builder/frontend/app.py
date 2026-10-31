"""World Builder UI. Run ``streamlit run app.py`` from ``frontend/`` with the backend running."""

from __future__ import annotations

import streamlit as st

import api
from shared.state import init_session_state

st.set_page_config(page_title="World Builder", page_icon=":material/public:", layout="wide")
init_session_state()

# What .streamlit/config.toml cannot set (MarianoOG design system). Streamlit
# always draws primary-button text in white, so the near-white `primary` fill
# with its dark `on-primary` label, and the selected tab, are styled here.
st.html(
    """
    <style>
    [data-testid="stBaseButton-primary"]:not(:disabled),
    [data-testid="stBaseButton-primaryFormSubmit"]:not(:disabled) {
        background-color: #ededee;   /* primary (grey-100) */
        border-color: #ededee;
        color: #0e0e10;              /* on-primary (grey-950) */
        transition: box-shadow 200ms cubic-bezier(0.16, 1, 0.3, 1);
    }
    [data-testid="stBaseButton-primary"]:not(:disabled):hover,
    [data-testid="stBaseButton-primaryFormSubmit"]:not(:disabled):hover,
    [data-testid="stBaseButton-primary"]:not(:disabled):active,
    [data-testid="stBaseButton-primaryFormSubmit"]:not(:disabled):active {
        background-color: #ededee;
        border-color: #ededee;
        color: #0e0e10;
        /* catch: the key light from the top-left, the counter from the bottom-right */
        box-shadow: -10px -10px 28px -12px rgba(59, 130, 246, 0.55),
                    10px 10px 28px -12px rgba(245, 158, 11, 0.4);
    }
    [data-testid="stBaseButton-primary"]:focus-visible,
    [data-testid="stBaseButton-primaryFormSubmit"]:focus-visible {
        box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.3);   /* focus (ring, blue-400) */
    }
    /* The selected tab reads brightest, with a foreground underline */
    button[role="tab"][aria-selected="true"],
    button[role="tab"][aria-selected="true"] p {
        color: #ededee;
    }
    [data-baseweb="tab-highlight"] {
        background-color: #ededee;
    }
    </style>
    """
)

pages = {
    "World": [
        st.Page("pages/world.py", title="World", icon=":material/public:", default=True),
        st.Page("pages/asset.py", title="Asset", icon=":material/add_photo_alternate:"),
    ],
    "Story": [
        st.Page("pages/script.py", title="Script", icon=":material/description:"),
        st.Page("pages/storyboard.py", title="Storyboard", icon=":material/movie:"),
    ],
    "Settings": [
        st.Page("pages/worlds.py", title="Manage worlds", icon=":material/settings:"),
    ],
}

try:
    st.navigation(pages).run()
except api.ApiError as exc:
    # Anything a page did not handle itself, usually the backend being down.
    st.error(str(exc))
