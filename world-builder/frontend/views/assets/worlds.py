"""Worlds - create, rename and delete the settings assets are grouped into.

Switching worlds happens in the sidebar on every page; this page is only for
changing the set of them. Rename and delete are held only for a world a running
generation is about to write into.
"""

from __future__ import annotations

from typing import Dict

import streamlit as st

import api
from shared.worlds import render_world_switcher

LIBRARY_PAGE = "views/assets/library.py"


def notify(kind: str, text: str) -> None:
    """Report through session state: the rerun below wipes the page first."""
    st.session_state.bulk_notice = (kind, text)
    st.rerun()


def render_create() -> None:
    """Name a new world and switch to it. Safe to do mid-generation: a new,
    empty folder cannot disturb a render already writing elsewhere."""
    st.subheader("New world")
    name_col, button_col = st.columns([3, 1])
    name = name_col.text_input(
        "World name",
        placeholder="night_market",
        label_visibility='collapsed',
        key='new_world_name',
    )
    if button_col.button("Create", type="primary", width='stretch'):
        try:
            st.session_state.current_world = api.post("/worlds", json={'name': name})['name']
        except api.ApiError as exc:
            st.error(str(exc))
            return
        notify('success', f"Created **{st.session_state.current_world}**.")


def render_world_row(entry: Dict, active: bool) -> None:
    """One world: its size, a rename, and a delete behind a confirmation."""
    world, count, busy = entry['name'], entry['asset_count'], entry['busy']
    heading = f"### {world}" + ("  ·  *active*" if active else "")
    st.markdown(heading)
    st.caption(f"{count} asset{'s' if count != 1 else ''}")
    if busy:
        st.info("A generation is writing into this world. Renaming and deleting "
                "are held until it lands.")

    rename_col, delete_col = st.columns(2)

    with rename_col:
        new_name = st.text_input(
            "Rename to",
            value=world,
            key=f"rename_{world}",
            disabled=busy,
        )
        if st.button("Rename", key=f"rename_button_{world}", disabled=busy):
            try:
                renamed = api.patch(f"/worlds/{world}", json={'name': new_name})['name']
            except api.ApiError as exc:
                st.error(str(exc))
                return
            if active:
                st.session_state.current_world = renamed
            notify('success', f"Renamed **{world}** to **{renamed}**.")

    with delete_col:
        st.caption(
            f"Deletes {world} and its {count} asset{'s' if count != 1 else ''}. "
            "This cannot be undone - the data folder is not tracked by git."
        )
        confirmed = st.checkbox(
            "Confirm delete", key=f"confirm_world_{world}", disabled=busy
        )
        if st.button(
            "Delete",
            type="primary",
            key=f"delete_world_{world}",
            disabled=busy or not confirmed,
        ):
            try:
                api.delete(f"/worlds/{world}")
            except api.ApiError as exc:
                st.error(str(exc))
                return
            if active:
                # The switcher reconciles ``current_world`` against the backend,
                # but the selection belongs to the world that just went away.
                st.session_state.selection = set()
                st.session_state.current_world = None
            notify('success', f"Deleted **{world}**.")


def main() -> None:
    active, payload = render_world_switcher(link=False)

    st.title("🌍 Worlds")
    st.caption(
        "A world owns its own characters, objects, locations and scenes. A scene "
        "can only be built from references in its own world."
    )

    if st.session_state.bulk_notice:
        kind, text = st.session_state.bulk_notice
        getattr(st, kind)(text)
        st.session_state.bulk_notice = None

    if st.button("← Back to library"):
        st.switch_page(LIBRARY_PAGE)

    st.divider()
    render_create()

    for entry in payload['worlds']:
        st.divider()
        render_world_row(entry, entry['name'] == active)


main()
