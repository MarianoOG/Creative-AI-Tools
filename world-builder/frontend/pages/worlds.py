"""Worlds: create, rename and delete worlds. Switching happens in the sidebar."""

from __future__ import annotations

from typing import Dict

import streamlit as st

import api
from shared.state import notify, show_notice
from shared.worlds import render_world_switcher


def plural(count: int, noun: str = "asset") -> str:
    return f"{count} {noun}{'s' if count != 1 else ''}"


def render_create() -> None:
    """Name a new world, start its style from a preset, and switch to it."""
    st.subheader("New world")
    presets = api.options()['styles']
    name_col, style_col, button_col = st.columns([2, 2, 1])
    name = name_col.text_input("World name", placeholder="night_market")
    preset = style_col.selectbox(
        "Start the style from", [None, *presets], format_func=lambda p: "Blank" if p is None else p
    )
    if button_col.button("Create", type="primary", width='stretch'):
        body = {'name': name, 'style': presets.get(preset, "")}
        try:
            st.session_state.current_world = api.post("/worlds", json=body)['name']
        except api.ApiError as exc:
            st.error(str(exc))
            return
        notify('success', f"Created **{st.session_state.current_world}**.")


def render_world_row(entry: Dict, active: bool) -> None:
    """One world: its size, a rename, and a delete behind a confirmation."""
    world, count = entry['name'], entry['asset_count']
    st.markdown(f"### {world}" + ("  ·  *active*" if active else ""))
    st.caption(f"{plural(count)} · {plural(entry['episode_count'], 'episode')}")

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
        st.caption(f"Removes {world}, its {plural(count)} and every episode from the app. Its folder is kept, hidden.")
        confirmed = st.checkbox("Confirm delete", key=f"confirm_world_{world}")
        if st.button("Delete", icon=":material/delete:", key=f"delete_world_{world}", disabled=not confirmed):
            try:
                api.delete(f"/worlds/{world}")
            except api.ApiError as exc:
                st.error(str(exc))
                return
            if active:
                st.session_state.current_world = None
            notify('success', f"Deleted **{world}**.")


def main() -> None:
    active, payload = render_world_switcher()

    st.title("Worlds")
    st.caption(
        "A world has one style and owns its characters, "
        "locations, objects and episodes."
    )
    show_notice()

    if st.button("Back to the world", icon=":material/arrow_back:"):
        st.switch_page("pages/world.py")

    st.divider()
    render_create()
    for entry in payload['worlds']:
        st.divider()
        render_world_row(entry, entry['name'] == active)


main()
