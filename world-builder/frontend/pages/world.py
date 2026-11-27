"""World: the current world's characters, locations and objects (each by its preferred image), and its episodes.

The top bar (which stays on screen as the page scrolls) picks one of the four
views, says what the world has cost so far, and has the view's New button.
"""

from __future__ import annotations

import base64
import html
from io import BytesIO
from urllib.parse import urlencode

import streamlit as st
from PIL import Image

import api
from shared.state import notify, show_notice
from shared.ui import grid, open_asset, open_script, plural, show_errors, top_bar, view_picker
from shared.worlds import render_world_switcher

ASSET_TABS = {'character': "Characters", 'location': "Locations", 'object': "Objects"}
#: The views, with their icons, in the order the bar shows them.
VIEWS = {"Characters": ":material/person:", "Locations": ":material/landscape:", "Objects": ":material/category:",
         "Episodes": ":material/movie:"}
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
    """Keep showing ``tab`` (a view's name) after the next rerun."""
    st.session_state.world_tab = tab


def render_actions(key: str, edit, confirm_text: str, delete_label: str, delete) -> None:
    """One row: Edit (wide) and a trash button that opens a popover to confirm the delete."""
    edit_col, delete_col = st.columns([3, 1])
    if edit_col.button("Edit", key=f"edit_{key}", width='stretch'):
        edit()
    with delete_col.popover(":material/delete:", width='stretch', help="Delete"):
        st.warning(confirm_text)
        if st.button(delete_label, icon=":material/delete:", key=f"delete_{key}"):
            delete()


def render_tile(world: str, asset: dict) -> None:
    """The preferred image (a link to the Asset page), the name with its variation count, Edit and Delete."""
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
    st.markdown(f"**{name}** &nbsp;:gray[{plural(len(asset['variations']), 'variation')}]")

    def delete() -> None:
        stay_on(ASSET_TABS[asset_type])
        api.delete("/assets", world=world, asset_type=asset_type, name=name)
        notify('success', f"Removed **{name}** from {world}.")

    render_actions(
        f"{asset_type}_{name}", lambda: open_asset(asset_type, name),
        f"Removes **{name}** from the world. Its image files stay in the data folder.", f"Delete {asset_type}", delete,
    )


def render_new_asset(world: str, asset_type: str) -> None:
    """Create an asset (name and description only) and open it on the Asset page to generate its images."""
    with st.popover(f"New {asset_type}", icon=":material/add:", type="primary", width='stretch'):
        name = st.text_input("Name", placeholder=f"{asset_type}_name", key=f"new_name_{asset_type}",
                             help="Used in scripts. Spaces and punctuation become underscores.")
        description = st.text_area("Description", key=f"new_description_{asset_type}", height=120)
        if st.button("Create", disabled=not (name.strip() and description.strip()), key=f"new_go_{asset_type}"):
            stay_on(ASSET_TABS[asset_type])
            with show_errors():
                created = api.post("/assets", json={
                    'world': world, 'asset_type': asset_type, 'name': name, 'description': description,
                })['asset']
                open_asset(asset_type, created['name'])


def render_assets(world: str, asset_type: str) -> None:
    assets = api.get("/assets", world=world, asset_type=asset_type)['assets']
    if not assets:
        st.info(f"No {asset_type}s in {world} yet.")
        return
    for column, asset in grid(assets):
        with column:
            render_tile(world, asset)


def render_new_episode(world: str) -> None:
    """Create an episode (title, synopsis and aspect ratio) and open it on the Script page to write its scenes."""
    with st.popover("New episode", icon=":material/add:", type="primary", width='stretch'):
        title = st.text_input("Title", key="new_episode_title",
                              help="Also names the episode's folder. Spaces and punctuation become underscores.")
        synopsis = st.text_area("Synopsis", key="new_episode_synopsis", height=120)
        ratios = api.options()['aspect_ratios']
        aspect_ratio = st.selectbox("Aspect ratio", ratios, key="new_episode_ratio",
                                    help="Every frame of the episode uses this aspect ratio.")
        if st.button("Create", disabled=not title.strip(), key="new_episode_go"):
            stay_on("Episodes")
            with show_errors():
                created = api.post(f"/worlds/{world}/episodes", json={
                    'title': title, 'synopsis': synopsis, 'aspect_ratio': aspect_ratio,
                })['name']
                open_script(created)


def render_episode(world: str, episode: dict) -> None:
    """A compact card: title, counts, the synopsis cut to three lines, Edit and Delete."""
    name = episode['name']
    with st.container(border=True):
        st.markdown(f"**{episode['title']}**")
        st.caption(f"`{name}` · {plural(episode['scene_count'], 'scene')} · {plural(episode['shot_count'], 'shot')}")
        st.markdown(f'<div class="synopsis">{html.escape(episode["synopsis"] or "")}</div>', unsafe_allow_html=True)

        def delete() -> None:
            stay_on("Episodes")
            api.delete(f"/worlds/{world}/episodes/{name}")
            notify('success', f"Deleted episode **{name}**.")

        render_actions(
            f"episode_{name}", lambda: open_script(name),
            f"Removes **{name}**, its {plural(episode['scene_count'], 'scene')} and every shot image from the app. "
            "Its folder is kept, hidden, in the data folder.", "Delete episode", delete,
        )


def render_episodes(world: str) -> None:
    """Every episode, newest first, three to a row."""
    episodes = api.get(f"/worlds/{world}/episodes")['episodes']
    if not episodes:
        st.info(f"No episodes in {world} yet.")
    for column, episode in grid(episodes):
        with column:
            render_episode(world, episode)


def cost_summary(world: str) -> str:
    costs = api.get(f"/worlds/{world}/costs")
    if not costs['entries']:
        return "Nothing spent on renders yet."
    note = " (some estimated)" if any(e['estimated'] for e in costs['entries']) else ""
    return f"Spent on renders: **\\${costs['total']:.2f}**{note}"


def main() -> None:
    world, _ = render_world_switcher()
    with top_bar():
        view_col, cost_col, new_col = st.columns([5, 3, 1.6], vertical_alignment='center')
        view = view_picker(VIEWS, 'world_tab', view_col)
        cost_col.caption(cost_summary(world),
                         help="Estimated: renders made before everything went through Runware, or that Runware "
                              "reported no cost for, are logged at list price.")
        with new_col:
            if view == "Episodes":
                render_new_episode(world)
            else:
                render_new_asset(world, next(key for key, name in ASSET_TABS.items() if name == view))
    show_notice()

    if view == "Episodes":
        render_episodes(world)
    else:
        render_assets(world, next(key for key, name in ASSET_TABS.items() if name == view))


main()
