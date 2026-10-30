"""Session state shared by every page."""

from __future__ import annotations

import streamlit as st


def init_session_state() -> None:
    defaults = {
        'gallery_page': 0,
        # The world every page shows, and the one new assets are written into.
        'current_world': None,
        # Paths ticked in the library. Kept here, not in the checkboxes, so a
        # selection survives paging.
        'selection': set(),
        # One-shot (kind, text) message shown after the rerun that caused it.
        'notice': None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def notify(kind: str, text: str) -> None:
    """Show ``text`` once, after a rerun (which would otherwise wipe it)."""
    st.session_state.notice = (kind, text)
    st.rerun()


def show_notice() -> None:
    if st.session_state.notice:
        kind, text = st.session_state.notice
        getattr(st, kind)(text)
        st.session_state.notice = None
