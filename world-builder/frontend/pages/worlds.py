"""Worlds: create, rename and delete worlds. Switching happens in the sidebar."""

from __future__ import annotations

from typing import Dict

import streamlit as st

import api
from shared.state import notify, show_notice
from shared.worlds import render_world_switcher


def plural(count: int) -> str:
    return f"{count} asset{'s' if count != 1 else ''}"


def render_create() -> None:
    """Name a new world and switch to it."""
    st.subheader("New world")
    name_col, button_col = st.columns([3, 1])
    name = name_col.text_input("World name", placeholder="night_market", label_visibility='collapsed')
    if button_col.button("Create", type="primary", width='stretch'):
        try:
            st.session_state.current_world = api.post("/worlds", json={'name': name})['name']
        except api.ApiError as exc:
            st.error(str(exc))
            return
        notify('success', f"Created **{st.session_state.current_world}**.")


def render_world_row(entry: Dict, active: bool) -> None:
    """One world: its size, a rename, and a delete behind a confirmation."""
    world, count = entry['name'], entry['asset_count']
    st.markdown(f"### {world}" + ("  ·  *active*" if active else ""))
    st.caption(plural(count))

    rename_col, delete_col = st.columns(2)
    with rename_col:
        new_name = st.text_input("Rename to", value=world, key=f"rename_{world}")
        if st.button("Rename", key=f"rename_button_{world}"):
            try:
                renamed = api.patch(f"/worlds/{world}", json={'name': new_name})['name']
            except api.ApiError as exc:
                st.error(str(exc))
                return
            if active:
                st.session_state.current_world = renamed
            notify('success', f"Renamed **{world}** to **{renamed}**.")

    with delete_col:
        st.caption(f"Deletes {world} and its {plural(count)}. This cannot be undone.")
        confirmed = st.checkbox("Confirm delete", key=f"confirm_world_{world}")
        if st.button("Delete", type="primary", key=f"delete_world_{world}", disabled=not confirmed):
            try:
                api.delete(f"/worlds/{world}")
            except api.ApiError as exc:
                st.error(str(exc))
                return
            if active:
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
    show_notice()

    if st.button("← Back to library"):
        st.switch_page("pages/library.py")

    st.divider()
    render_create()
    for entry in payload['worlds']:
        st.divider()
        render_world_row(entry, entry['name'] == active)


main()
