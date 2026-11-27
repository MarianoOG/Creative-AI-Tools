"""World Builder UI. Run ``streamlit run app.py`` from ``frontend/`` with the backend running."""

from __future__ import annotations

import streamlit as st

import api
from shared.state import init_session_state

st.set_page_config(page_title="World Builder", page_icon=":material/public:", layout="wide")
init_session_state()

# What .streamlit/config.toml cannot set (the project's design system). Streamlit
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
    /* The picked option of a view picker reads brightest, like the selected tab */
    [data-testid="stBaseButton-segmented_controlActive"],
    [data-testid="stBaseButton-segmented_controlActive"] p {
        background-color: #ededee;
        border-color: #ededee;
        color: #0e0e10;
    }
    /* Pages start with their top bar instead of a title, so less space above it */
    .stMainBlockContainer {
        padding-top: 3.5rem;
    }
    /* A page's top bar (shared.ui.top_bar) stays on screen, under Streamlit's header, as the page
       scrolls. Its wrapper is what sticks: the bar alone is exactly as tall as the wrapper and
       would have no room to move. A band above it hides what scrolls between it and the window's top. */
    [data-testid="stLayoutWrapper"]:has(> .st-key-top_bar) {
        position: sticky;
        top: 3.75rem;
        z-index: 99;
    }
    [data-testid="stLayoutWrapper"]:has(> .st-key-top_bar)::before {
        content: "";
        position: absolute;
        left: 0;
        right: 0;
        bottom: 100%;
        height: 4rem;
        background-color: #0e0e10;  /* background (grey-950) */
    }
    .st-key-top_bar {
        background-color: #0e0e10;
        padding: 0.5rem 0;
        border-bottom: 1px solid #2c2c30;  /* border (grey-700) */
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
        st.Page("pages/video.py", title="Video", icon=":material/videocam:"),
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
