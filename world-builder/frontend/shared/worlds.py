"""The sidebar shared by every page (the world picker), and the model picker."""

from __future__ import annotations

from typing import Dict, Tuple

import streamlit as st

import api


def render_world_switcher() -> Tuple[str, Dict]:
    """Draw the picker and return the active world plus the ``/worlds`` payload.

    The selectbox has no ``key`` so pages can assign ``current_world`` freely
    (after a create, rename or delete). Manage worlds is in the page menu.
    """
    payload = api.get("/worlds")
    worlds = [world["name"] for world in payload["worlds"]]
    current = st.session_state.current_world
    if current not in worlds:
        fallback = api.options()['default_world']
        current = st.session_state.current_world = fallback if fallback in worlds else worlds[0]

    with st.sidebar:
        chosen = st.selectbox("World", worlds, index=worlds.index(current))

    if chosen != current:
        state = st.session_state
        state.current_world = chosen
        state.current_episode = None
        st.rerun()

    return chosen, payload


def model_select(options: Dict, key: str, default: str = "") -> str:
    """The provider picker: one model renders each image."""
    providers = list(options['providers'])
    current = default if default in providers else options['default_provider']
    return st.selectbox(
        "Model", providers, index=providers.index(current), format_func=options['providers'].get, key=key
    )
