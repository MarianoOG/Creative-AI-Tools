"""Asset Library: browse, download, move and delete the current world's assets."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Dict, List

import streamlit as st

import api
from shared.state import notify, show_notice
from shared.worlds import render_world_switcher

CREATE_PAGE = "views/assets/create.py"
COLUMNS = 4
PAGE_SIZE = 24
ALL = "All"


@st.cache_data(show_spinner=False, max_entries=32)
def load_bytes(path: str, mtime: float) -> bytes:
    """Read an image for download. ``mtime`` is only a cache key. Capped: renders are several MB."""
    return api.file_path(path).read_bytes()


def _toggle_selection(key: str, path: str) -> None:
    if st.session_state[key]:
        st.session_state.selection.add(path)
    else:
        st.session_state.selection.discard(path)


def selected_paths() -> List[str]:
    """The current selection, pruned of files that no longer exist."""
    alive = sorted(path for path in st.session_state.selection if api.file_path(path).exists())
    st.session_state.selection = set(alive)
    return alive


def transfer(paths: List[str], target: str, copy: bool) -> None:
    """Move or duplicate assets into ``target``, then rerun with the outcome."""
    outcome = api.post("/assets/transfer", json={'paths': paths, 'target': target, 'copy_assets': copy})
    done, failed = outcome['done'], outcome['failed']
    if not copy:
        st.session_state.selection.difference_update(done)
    verb = "Duplicated" if copy else "Moved"
    if failed:
        notify('warning', f"{verb} {len(done)} of {len(paths)} to **{target}**. " + "; ".join(failed))
    else:
        notify('success', f"{verb} {len(done)} asset{'s' if len(done) != 1 else ''} to **{target}**.")


def render_bulk_bar(targets: List[str]) -> None:
    """Act on every ticked tile at once. Hidden while nothing is ticked."""
    paths = selected_paths()
    if not paths:
        return

    st.info(f"{len(paths)} selected")
    if not targets:
        st.caption("Create another world before moving anything out of this one.")
        return

    target_col, move_col, copy_col, clear_col = st.columns([3, 1, 1, 1])
    target = target_col.selectbox("Move or duplicate to", targets, key='bulk_target', label_visibility='collapsed')
    if move_col.button("Move", key='bulk_move', width='stretch'):
        transfer(paths, target, copy=False)
    if copy_col.button("Duplicate", key='bulk_copy', width='stretch'):
        transfer(paths, target, copy=True)
    if clear_col.button("Clear", key='bulk_clear', width='stretch'):
        for path in paths:
            st.session_state.pop(f"select_{path}", None)
        st.session_state.selection = set()
        st.rerun()


def render_filters(facets: Dict[str, List[str]]) -> Dict[str, str]:
    """Filters built from what is on disk. Returns only the ones set."""
    type_col, style_col, provider_col = st.columns(3)
    picks = {
        'asset_type': type_col.selectbox("Type", [ALL] + facets['asset_type']),
        'style': style_col.selectbox("Style", [ALL] + facets['style']),
        'provider': provider_col.selectbox("Provider", [ALL] + facets['provider']),
    }
    return {field: value for field, value in picks.items() if value != ALL}


def paginate(assets: List[Dict]) -> List[Dict]:
    pages = max(1, -(-len(assets) // PAGE_SIZE))
    page = st.session_state.gallery_page = min(st.session_state.gallery_page, pages - 1)

    if pages > 1:
        previous, label, following = st.columns([1, 2, 1])
        if previous.button("← Previous", disabled=page == 0, width='stretch'):
            st.session_state.gallery_page = page - 1
            st.rerun()
        label.markdown(f"<div style='text-align:center'>Page {page + 1} of {pages}</div>", unsafe_allow_html=True)
        if following.button("Next →", disabled=page >= pages - 1, width='stretch'):
            st.session_state.gallery_page = page + 1
            st.rerun()

    return assets[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]


def render_tile(asset: Dict, targets: List[str]) -> None:
    """A thumbnail, a select box, and the full view, transfer, download and delete in an expander."""
    path = asset['path']
    name = Path(path).name
    st.image(str(api.file_path(path)), width='stretch')
    st.caption(asset['label'])

    # ``value`` re-seeds the tick from the selection when the tile comes back after paging.
    key = f"select_{path}"
    st.checkbox(
        "Select", value=path in st.session_state.selection, key=key, on_change=_toggle_selection, args=(key, path)
    )

    with st.expander("Details"):
        st.text(name)
        if targets:
            target = st.selectbox("Move or duplicate to", targets, key=f"target_{path}")
            move_col, copy_col = st.columns(2)
            if move_col.button("Move", key=f"move_{path}", width='stretch'):
                transfer([path], target, copy=False)
            if copy_col.button("Duplicate", key=f"copy_{path}", width='stretch'):
                transfer([path], target, copy=True)
        st.download_button(
            "Download",
            data=load_bytes(path, asset['mtime']),
            file_name=name,
            mime=mimetypes.guess_type(name)[0] or "image/png",
            key=f"download_{path}",
            width='stretch',
        )
        confirmed = st.checkbox("Confirm delete", key=f"confirm_{path}")
        if st.button("Delete", type="primary", disabled=not confirmed, key=f"delete_{path}", width='stretch'):
            api.delete("/assets", path=path)
            st.session_state.selection.discard(path)
            st.rerun()


def main() -> None:
    world, payload = render_world_switcher()
    targets = [entry['name'] for entry in payload['worlds'] if entry['name'] != world]

    st.title("🎨 Asset Library")
    st.caption(f"Every character, object, location and scene in **{world}**.")
    show_notice()

    listing = api.get("/assets", world=world)
    if not listing['total']:
        st.info(f"No assets in {world} yet. Generate your first one to get started.")
    if st.button("＋ Create an asset", type="primary"):
        st.switch_page(CREATE_PAGE)
    if not listing['total']:
        return

    st.divider()
    picks = render_filters(listing['facets'])
    visible = api.get("/assets", world=world, **picks)['assets'] if picks else listing['assets']
    st.caption(f"{len(visible)} of {listing['total']} assets")

    # Above the grid, so a selection stays actionable when the filters hide it.
    render_bulk_bar(targets)

    if not visible:
        st.info("No assets match these filters.")
        return

    st.divider()
    page = paginate(visible)
    for row_start in range(0, len(page), COLUMNS):
        for column, asset in zip(st.columns(COLUMNS), page[row_start:row_start + COLUMNS]):
            with column:
                render_tile(asset, targets)


main()
