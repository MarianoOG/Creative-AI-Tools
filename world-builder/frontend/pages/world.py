"""World: the current world's characters, locations and objects (each by its preferred image), and its episodes, one tab each."""

from __future__ import annotations

import base64
from io import BytesIO
from urllib.parse import urlencode

import streamlit as st
from PIL import Image

import api
from shared.state import notify, show_notice
from shared.worlds import render_world_switcher

COLUMNS = 3
ASSET_TABS = {'character': "Characters", 'location': "Locations", 'object': "Objects"}
THUMBNAIL = (960, 540)


@st.cache_data(show_spinner=False, max_entries=256)
def thumbnail(path: str, mtime: float) -> str:
    """A small JPEG of an image as a data URI, for the clickable tile. ``mtime`` is only a cache key."""
    image = Image.open(api.file_path(path)).convert("RGB")
    image.thumbnail(THUMBNAIL)
    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def stay_on(tab: str) -> None:
    """Reopen ``tab`` after the next rerun, which would otherwise show the first one."""
    st.session_state.world_tab = tab


def open_asset(asset_type: str, name: str) -> None:
    st.session_state.current_asset = (asset_type, name)
    st.switch_page("pages/asset.py")


def render_tile(world: str, asset: dict) -> None:
    """The preferred image (a link to the Asset page), the name, Edit, and the details with Delete."""
    asset_type, name = asset['asset_type'], asset['name']
    preferred = next((v for v in asset['variations'] if v['name'] == asset['preferred']), None)
    if preferred:
        link = "asset?" + urlencode({'world': world, 'type': asset_type, 'name': name})
        st.markdown(
            f'<a href="{link}" target="_self"><img src="{thumbnail(preferred["path"], preferred["mtime"])}" '
            f'alt="{name}" style="width:100%;border-radius:0.5rem;display:block"></a>',
            unsafe_allow_html=True,
        )
    else:
        st.info("No images yet.")
    name_col, edit_col = st.columns([3, 1])
    name_col.markdown(f"**{name}**")
    if edit_col.button("Edit", key=f"edit_{asset_type}_{name}", width='stretch'):
        open_asset(asset_type, name)
    with st.expander("Details"):
        if asset['description']:
            st.write(asset['description'])
        count = len(asset['variations'])
        st.caption(f"{count} {'view' if asset_type == 'location' else 'variation'}{'s' if count != 1 else ''}"
                   + (f" · preferred: {asset['preferred']}" if asset['preferred'] else ""))
        confirmed = st.checkbox("Confirm delete", key=f"confirm_{asset_type}_{name}")
        if st.button("Delete", icon=":material/delete:", disabled=not confirmed, key=f"delete_{asset_type}_{name}",
                     width='stretch', help="Removes it from the world. Its image files stay in the data folder."):
            stay_on(ASSET_TABS[asset_type])
            api.delete("/assets", world=world, asset_type=asset_type, name=name)
            notify('success', f"Removed **{name}** from {world}.")


def render_new_asset(world: str, asset_type: str) -> None:
    """Create an asset (name and description only) and open it on the Asset page to generate its images."""
    with st.popover(f"New {asset_type}", icon=":material/add:", type="primary"):
        name = st.text_input("Name", placeholder=f"{asset_type}_name", key=f"new_name_{asset_type}",
                             help="Used in scripts. Spaces and punctuation become underscores.")
        description = st.text_area("Description", key=f"new_description_{asset_type}", height=120)
        if st.button("Create", disabled=not (name.strip() and description.strip()), key=f"new_go_{asset_type}"):
            stay_on(ASSET_TABS[asset_type])
            try:
                created = api.post("/assets", json={
                    'world': world, 'asset_type': asset_type, 'name': name, 'description': description,
                })['asset']
            except api.ApiError as exc:
                st.error(str(exc))
                return
            open_asset(asset_type, created['name'])


def render_assets(world: str, asset_type: str) -> None:
    render_new_asset(world, asset_type)
    assets = api.get("/assets", world=world, asset_type=asset_type)['assets']
    if not assets:
        st.info(f"No {asset_type}s in {world} yet.")
        return
    for row_start in range(0, len(assets), COLUMNS):
        for column, asset in zip(st.columns(COLUMNS), assets[row_start:row_start + COLUMNS]):
            with column:
                render_tile(world, asset)


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
                "are removed from the app (the folder is kept, hidden, in the data folder)."
            )
            if st.button("Delete episode", icon=":material/delete:", key=f"delete_episode_{episode['name']}"):
                stay_on("Episodes")
                api.delete(f"/worlds/{world}/episodes/{episode['name']}")
                notify('success', f"Deleted episode **{episode['name']}**.")


def main() -> None:
    world, _ = render_world_switcher()

    st.title(world)
    show_notice()

    tab_names = [*ASSET_TABS.values(), "Episodes"]
    *asset_tabs, episodes_tab = st.tabs(tab_names, default=st.session_state.get('world_tab'))
    for tab, asset_type in zip(asset_tabs, ASSET_TABS):
        with tab:
            render_assets(world, asset_type)
    with episodes_tab:
        render_episodes(world)


main()
