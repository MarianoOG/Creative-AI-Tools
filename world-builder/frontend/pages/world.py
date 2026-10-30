"""World: the current world's characters, locations and objects, and its episodes, one tab each."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Dict, List

import streamlit as st

import api
from shared.state import notify, show_notice
from shared.worlds import render_world_switcher

COLUMNS = 4
ASSET_TABS = {'character': "Characters", 'location': "Locations", 'object': "Objects"}


@st.cache_data(show_spinner=False, max_entries=32)
def load_bytes(path: str, mtime: float) -> bytes:
    """Read an image for download. ``mtime`` is only a cache key. Capped: renders are several MB."""
    return api.file_path(path).read_bytes()


def stay_on(tab: str) -> None:
    """Reopen ``tab`` after the next rerun, which would otherwise show the first one."""
    st.session_state.world_tab = tab


def transfer(path: str, target: str, copy: bool) -> None:
    """Move or duplicate an asset into ``target``, then rerun with the outcome."""
    outcome = api.post("/assets/transfer", json={'paths': [path], 'target': target, 'copy_assets': copy})
    if outcome['failed']:
        notify('warning', "; ".join(outcome['failed']))
    notify('success', f"{'Duplicated' if copy else 'Moved'} to **{target}**.")


def render_tile(asset: Dict, targets: List[str]) -> None:
    """A thumbnail, and the move, download and delete actions in an expander."""
    path = asset['path']
    name = Path(path).name
    tab = ASSET_TABS[asset['asset_type']]
    st.image(str(api.file_path(path)), width='stretch')
    st.caption(asset['label'])

    with st.expander("Details"):
        st.text(name)
        if targets:
            target = st.selectbox("Move or duplicate to", targets, key=f"target_{path}")
            move_col, copy_col = st.columns(2)
            if move_col.button("Move", key=f"move_{path}", width='stretch'):
                stay_on(tab)
                transfer(path, target, copy=False)
            if copy_col.button("Duplicate", key=f"copy_{path}", width='stretch'):
                stay_on(tab)
                transfer(path, target, copy=True)
        st.download_button(
            "Download",
            data=load_bytes(path, asset['mtime']),
            file_name=name,
            mime=mimetypes.guess_type(name)[0] or "image/png",
            key=f"download_{path}",
            width='stretch',
        )
        confirmed = st.checkbox("Confirm delete", key=f"confirm_{path}")
        if st.button("Delete", icon=":material/delete:", disabled=not confirmed, key=f"delete_{path}", width='stretch'):
            stay_on(tab)
            api.delete("/assets", path=path)
            st.rerun()


def render_assets(world: str, asset_type: str, targets: List[str]) -> None:
    if st.button(f"Create a {asset_type}", icon=":material/add:", key=f"create_{asset_type}", type="primary"):
        st.session_state.create_type = asset_type
        st.switch_page("pages/create.py")
    assets = api.get("/assets", world=world, asset_type=asset_type)['assets']
    if not assets:
        st.info(f"No {asset_type}s in {world} yet.")
        return
    for row_start in range(0, len(assets), COLUMNS):
        for column, asset in zip(st.columns(COLUMNS), assets[row_start:row_start + COLUMNS]):
            with column:
                render_tile(asset, targets)


def render_episodes(world: str) -> None:
    episodes = api.get(f"/worlds/{world}/episodes")['episodes']
    suggested = f"episode{len(episodes) + 1}"
    name_col, button_col = st.columns([3, 1])
    name = name_col.text_input("New episode", placeholder=suggested, label_visibility='collapsed')
    if button_col.button("Create episode", icon=":material/add:", type="primary", width='stretch'):
        stay_on("Episodes")
        try:
            created = api.post(f"/worlds/{world}/episodes", json={'name': name or suggested})['name']
        except api.ApiError as exc:
            st.error(str(exc))
            return
        notify('success', f"Created episode **{created}**.")

    if not episodes:
        st.info(f"No episodes in {world} yet.")
    for episode in episodes:
        st.divider()
        info_col, open_col = st.columns([4, 1])
        info_col.markdown(f"### {episode['title']}")
        info_col.caption(f"`{episode['name']}` · {episode['scene_count']} scenes · {episode['shot_count']} shots")
        if episode['synopsis']:
            info_col.write(episode['synopsis'])
        if open_col.button("Open script", key=f"open_{episode['name']}", width='stretch'):
            st.session_state.current_episode = episode['name']
            st.session_state.current_scene = None
            st.switch_page("pages/episode.py")
        with open_col.popover("Delete", width='stretch'):
            st.warning(
                f"All {episode['scene_count']} scenes and every shot image in **{episode['name']}** "
                "will be lost. This cannot be undone."
            )
            if st.button("Delete episode", icon=":material/delete:", key=f"delete_episode_{episode['name']}"):
                stay_on("Episodes")
                api.delete(f"/worlds/{world}/episodes/{episode['name']}")
                notify('success', f"Deleted episode **{episode['name']}**.")


def main() -> None:
    world, payload = render_world_switcher()
    targets = [entry['name'] for entry in payload['worlds'] if entry['name'] != world]

    st.title(world)
    show_notice()

    tab_names = [*ASSET_TABS.values(), "Episodes"]
    *asset_tabs, episodes_tab = st.tabs(tab_names, default=st.session_state.get('world_tab'))
    for tab, asset_type in zip(asset_tabs, ASSET_TABS):
        with tab:
            render_assets(world, asset_type, targets)
    with episodes_tab:
        render_episodes(world)


main()
