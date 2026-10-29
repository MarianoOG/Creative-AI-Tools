"""The sidebar world picker shared by every asset page."""

from __future__ import annotations

from typing import Dict, Tuple

import streamlit as st

import api

WORLDS_PAGE = "views/assets/worlds.py"


def _drop_world_scoped_state() -> None:
    """Forget everything that only made sense in the world we just left.

    Streamlit is not guaranteed to prune a multiselect's value when its options
    disappear, so without this a world switch could still submit scene
    references from the old world. The library's tile checkboxes go for the same
    reason. Safe to delete those widget keys here because the switcher is drawn
    before any of them: Streamlit only objects to touching a widget's state
    after the widget itself has been created on this run.
    """
    state = st.session_state
    for key in [key for key in state if key.startswith(("scene_refs_", "select_"))]:
        del state[key]
    state.selection = set()
    state.gallery_page = 0


def render_world_switcher(link: bool = True) -> Tuple[str, Dict]:
    """Draw the picker and return the active world plus the ``/worlds`` payload.

    The selectbox deliberately carries no ``key``: ``current_world`` stays a
    plain session value that any page can assign to after a world is created,
    renamed or deleted. Binding the widget to it directly would make those
    assignments illegal on the run that performs them. Passing ``index`` instead
    means the widget follows ``current_world`` in both directions.

    It also reconciles ``current_world`` with the backend, so a world renamed or
    deleted in another tab cannot leave the picker pointing at nothing.

    ``link=False`` drops the link to the Worlds page, for the Worlds page itself.
    """
    payload = api.get("/worlds")
    worlds = [world["name"] for world in payload["worlds"]]
    current = st.session_state.get('current_world')
    if current not in worlds:
        current = worlds[0]
        st.session_state.current_world = current

    with st.sidebar:
        chosen = st.selectbox(
            "World",
            worlds,
            index=worlds.index(current),
            help="Assets are grouped by world. A scene can only use references "
            "from the world it is generated into.",
        )
        if link:
            st.page_link(WORLDS_PAGE, label="Manage worlds", icon="🌍")

    if chosen != current:
        st.session_state.current_world = chosen
        _drop_world_scoped_state()
        st.rerun()

    return chosen, payload
