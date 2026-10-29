"""Asset Library - browse, download, move and delete every generated asset.

One world at a time: the sidebar switcher picks it, and everything below - the
grid, the filters, the bulk bar - is that world's. Assets cross between worlds
only by being moved or duplicated, one at a time from a tile's Details expander
or in bulk from the ticked selection.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Dict, List

import streamlit as st

import api
from shared import jobs
from shared.worlds import render_world_switcher

CREATE_PAGE = "views/assets/create.py"

#: Tiles per row and per page. Renders are 2K, so a page is a real cost.
COLUMNS = 4
PAGE_SIZE = 24

ALL = "All"


@st.cache_data(show_spinner=False, max_entries=32)
def load_bytes(path: str, mtime: float) -> bytes:
    """Read an image for download. ``mtime`` is a cache key, not an argument.

    Capped at 32 entries: a 2K render is 3-6 MB, and an uncapped cache would
    grow for the whole session as the user browses.
    """
    return api.file_path(path).read_bytes()


def _toggle_selection(key: str, path: str) -> None:
    """Mirror one tile's checkbox into the session-wide selection set."""
    if st.session_state[key]:
        st.session_state.selection.add(path)
    else:
        st.session_state.selection.discard(path)


def selected_paths() -> List[str]:
    """The current selection, pruned of anything no longer on disk.

    An asset deleted from its own expander leaves its path behind in the set;
    dropping it here keeps the next bulk action from failing on a ghost.
    """
    selection = st.session_state.selection
    alive = sorted(path for path in selection if api.file_path(path).exists())
    if len(alive) != len(selection):
        st.session_state.selection = set(alive)
    return alive


def transfer(paths: List[str], target: str, copy: bool) -> None:
    """Move or duplicate assets into ``target``, then rerun with a verdict.

    The outcome goes through session state because the rerun below wipes
    anything written to the page directly.
    """
    verb = "Duplicated" if copy else "Moved"
    outcome = api.post(
        "/assets/transfer", json={'paths': paths, 'target': target, 'copy_assets': copy}
    )
    done, failed = outcome['done'], outcome['failed']
    if not copy:
        # The tile is gone from this world, so Streamlit retires its checkbox on
        # its own; only the selection has to be told.
        st.session_state.selection.difference_update(done)

    if failed:
        st.session_state.bulk_notice = (
            'warning',
            f"{verb} {len(done)} of {len(paths)} to **{target}**. " + "; ".join(failed),
        )
    else:
        st.session_state.bulk_notice = (
            'success',
            f"{verb} {len(done)} asset{'s' if len(done) != 1 else ''} to **{target}**.",
        )
    st.rerun()


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
    target = target_col.selectbox(
        "Move or duplicate to", targets, key='bulk_target', label_visibility='collapsed'
    )
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
    """Three selectboxes built from what is actually on disk. Returns the picks."""
    type_col, style_col, provider_col = st.columns(3)
    picks = {
        'asset_type': type_col.selectbox("Type", [ALL] + facets['asset_type']),
        'style': style_col.selectbox("Style", [ALL] + facets['style']),
        'provider': provider_col.selectbox("Provider", [ALL] + facets['provider']),
    }
    return {field: value for field, value in picks.items() if value != ALL}


def paginate(assets: List[Dict]) -> List[Dict]:
    """Clamp the stored page to the current result count and slice it out."""
    pages = max(1, -(-len(assets) // PAGE_SIZE))
    page = min(st.session_state.get('gallery_page', 0), pages - 1)
    st.session_state.gallery_page = page

    if pages > 1:
        previous, label, following = st.columns([1, 2, 1])
        if previous.button("← Previous", disabled=page == 0, width='stretch'):
            st.session_state.gallery_page = page - 1
            st.rerun()
        label.markdown(
            f"<div style='text-align:center'>Page {page + 1} of {pages}</div>",
            unsafe_allow_html=True,
        )
        if following.button("Next →", disabled=page >= pages - 1, width='stretch'):
            st.session_state.gallery_page = page + 1
            st.rerun()

    start = page * PAGE_SIZE
    return assets[start:start + PAGE_SIZE]


def render_tile(asset: Dict, targets: List[str]) -> None:
    """One thumbnail plus an expander holding the full view, download and delete.

    The download button lives in the expander on purpose: it needs its bytes at
    render time, and loading every tile's 3-6 MB on every rerun would make the
    grid crawl.

    ``value=`` on the checkbox is what survives pagination: Streamlit drops
    widget state for anything not rendered on the previous run, so the tick has
    to be re-seeded from the selection set every time the tile comes back.
    """
    path = asset['path']
    name = Path(path).name
    st.image(str(api.file_path(path)), width='stretch')
    st.caption(asset['label'])

    key = f"select_{path}"
    st.checkbox(
        "Select",
        value=path in st.session_state.selection,
        key=key,
        on_change=_toggle_selection,
        args=(key, path),
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
        if st.button(
            "Delete",
            type="primary",
            disabled=not confirmed,
            key=f"delete_{path}",
            width='stretch',
        ):
            api.delete("/assets", path=path)
            st.session_state.selection.discard(path)
            st.rerun()


def running_count() -> int:
    """Unfinished generations anywhere, not only this session's."""
    return len(api.get("/jobs", kind="asset", active=True))


@st.fragment(run_every=2)
def watch_jobs() -> None:
    """Wait for generations without polling the whole grid.

    The count comes from the backend rather than session state, so this also
    covers a job started from another tab: when the count drops, the app reruns
    and the new tiles appear without anyone clicking anything.
    """
    running = running_count()
    if running < st.session_state.running_assets:
        st.rerun(scope="app")
    st.session_state.running_assets = running
    st.info(f"{running} generation{'s' if running > 1 else ''} in progress...")


def render_grid(assets: List[Dict], targets: List[str]) -> None:
    """Lay the tiles out in rows of :data:`COLUMNS`."""
    for row_start in range(0, len(assets), COLUMNS):
        row = assets[row_start:row_start + COLUMNS]
        for column, asset in zip(st.columns(COLUMNS), row):
            with column:
                render_tile(asset, targets)


def main() -> None:
    jobs.collect()

    world, payload = render_world_switcher()
    targets = [entry['name'] for entry in payload['worlds'] if entry['name'] != world]

    st.title("🎨 Asset Library")
    st.caption(f"Every character, object, location and scene in **{world}**.")

    if payload['migration_skipped']:
        st.warning(
            "Left in the old pre-world folders because that name was already "
            "taken in `default`: " + ", ".join(payload['migration_skipped'])
        )
    # Shown once: they report on something that just happened, not on a state
    # the library should keep nagging about.
    if st.session_state.bulk_notice:
        kind, text = st.session_state.bulk_notice
        getattr(st, kind)(text)
        st.session_state.bulk_notice = None
    jobs.show_notices()
    st.session_state.running_assets = running_count()
    if st.session_state.running_assets:
        watch_jobs()

    listing = api.get("/assets", world=world)
    if not listing['total']:
        st.info(f"No assets in {world} yet. Generate your first one to get started.")
        if st.button("Create an asset", type="primary"):
            st.switch_page(CREATE_PAGE)
        return

    if st.button("＋ Create an asset", type="primary"):
        st.switch_page(CREATE_PAGE)

    st.divider()
    picks = render_filters(listing['facets'])
    visible = api.get("/assets", world=world, **picks)['assets'] if picks else listing['assets']
    st.caption(f"{len(visible)} of {listing['total']} assets")

    # Above the filter result on purpose: a selection stays actionable even when
    # the filters currently hide every tile in it.
    render_bulk_bar(targets)

    if not visible:
        st.info("No assets match these filters.")
        return

    st.divider()
    render_grid(paginate(visible), targets)


main()
