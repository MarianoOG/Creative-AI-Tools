"""The sidebar shared by every page: the world picker and the world's style."""

from __future__ import annotations

from typing import Dict, Tuple

import streamlit as st

import api


def render_style_editor(world: str) -> None:
    """Show and edit the world's ``style.txt``, which every generated image in it uses."""
    style = api.get(f"/worlds/{world}/style")['style']
    st.markdown("**Style** · `style.txt`")
    text = st.text_area(
        "Style",
        value=style,
        height=220,
        key=f"style_{world}",
        label_visibility='collapsed',
        help="Every character, object, location and storyboard frame in this world is drawn in this style.",
    )
    if text.strip() != style:
        if st.button("Save style", type="primary", width='stretch'):
            api.put(f"/worlds/{world}/style", json={'style': text})
            st.rerun()
    elif not style:
        st.caption("No style yet: generation is disabled until you write one.")


def render_world_switcher(link: bool = True) -> Tuple[str, Dict]:
    """Draw the picker and the style editor, and return the active world plus the ``/worlds`` payload.

    The selectbox has no ``key`` so pages can assign ``current_world`` freely
    (after a create, rename or delete). ``link=False`` hides the Worlds link.
    """
    payload = api.get("/worlds")
    worlds = [world["name"] for world in payload["worlds"]]
    current = st.session_state.current_world
    if current not in worlds:
        fallback = api.options()['default_world']
        current = st.session_state.current_world = fallback if fallback in worlds else worlds[0]

    with st.sidebar:
        chosen = st.selectbox("World", worlds, index=worlds.index(current))
        if link:
            st.page_link("pages/worlds.py", label="Manage worlds", icon="🌍")

    if chosen != current:
        state = st.session_state
        state.current_world = chosen
        state.current_episode = state.current_scene = None
        st.rerun()

    with st.sidebar:
        st.divider()
        render_style_editor(chosen)

    return chosen, payload
