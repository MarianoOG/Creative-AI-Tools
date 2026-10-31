"""Worlds: create, rename, restyle and delete worlds. Switching happens in the sidebar."""

from __future__ import annotations

from typing import Dict

import streamlit as st

import api
from shared.state import notify, show_notice
from shared.ui import back_to_world_button, plural, show_errors
from shared.worlds import render_world_switcher


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
        with show_errors():
            st.session_state.current_world = api.post("/worlds", json=body)['name']
            notify('success', f"Created **{st.session_state.current_world}**.")


def render_world_row(entry: Dict, active: bool) -> None:
    """One world: its size, its name and style behind one save, and a delete behind a confirmation."""
    world, count = entry['name'], entry['asset_count']
    st.markdown(f"### {world}" + ("  ·  *active*" if active else ""))
    st.caption(f"{plural(count, 'asset')} · {plural(entry['episode_count'], 'episode')}")

    edit_col, delete_col = st.columns(2)
    with edit_col:
        style = api.get(f"/worlds/{world}/style")['style']
        new_name = st.text_input("Name", value=world, key=f"rename_{world}")
        new_style = st.text_area(
            "Style",
            value=style,
            height=220,
            key=f"style_{world}",
            help="Every character, object, location and storyboard frame in this world is drawn in this style.",
        )
        if not style:
            st.caption("No style yet: generation is disabled until you write one.")
        changed = new_name.strip() != world or new_style.strip() != style
        if st.button("Save world", type="primary", key=f"save_world_{world}", disabled=not changed):
            with show_errors():
                if new_style.strip() != style:
                    api.put(f"/worlds/{world}/style", json={'style': new_style})
                renamed = api.patch(f"/worlds/{world}", json={'name': new_name})['name']
                if active:
                    st.session_state.current_world = renamed
                notify('success', f"Saved **{renamed}**.")

    with delete_col:
        st.caption(f"Removes {world}, its {plural(count, 'asset')} and every episode from the app. Its folder is kept, hidden.")
        confirmed = st.checkbox("Confirm delete", key=f"confirm_world_{world}")
        if st.button("Delete", icon=":material/delete:", key=f"delete_world_{world}", disabled=not confirmed):
            with show_errors():
                api.delete(f"/worlds/{world}")
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

    back_to_world_button()

    st.divider()
    render_create()
    for entry in payload['worlds']:
        st.divider()
        render_world_row(entry, entry['name'] == active)


main()
