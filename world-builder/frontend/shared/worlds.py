"""The sidebar world picker shared by every page."""

from __future__ import annotations

from typing import Dict, Tuple

import streamlit as st

import api


def render_world_switcher(link: bool = True) -> Tuple[str, Dict]:
    """Draw the picker and return the active world plus the ``/worlds`` payload.

    The selectbox has no ``key`` so pages can assign ``current_world`` freely
    (after a create, rename or delete). ``link=False`` hides the Worlds link.
    """
    payload = api.get("/worlds")
    worlds = [world["name"] for world in payload["worlds"]]
    current = st.session_state.current_world
    if current not in worlds:
        current = st.session_state.current_world = worlds[0]

    with st.sidebar:
        chosen = st.selectbox(
            "World",
            worlds,
            index=worlds.index(current),
            help="Assets are grouped by world. A scene can only use references "
            "from the world it is generated into.",
        )
        if link:
            st.page_link("pages/worlds.py", label="Manage worlds", icon="🌍")

    if chosen != current:
        # Forget what belonged to the old world: scene references and ticked tiles.
        state = st.session_state
        for key in [key for key in state if key.startswith(("scene_refs_", "select_"))]:
            del state[key]
        state.current_world = chosen
        state.selection = set()
        state.gallery_page = 0
        st.rerun()

    return chosen, payload
