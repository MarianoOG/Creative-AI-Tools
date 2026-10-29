"""Session state: one set of defaults for every page of the app."""

from __future__ import annotations

import streamlit as st


def init_session_state() -> None:
    """Seed every key the pages read, so no page needs its own guard."""
    defaults = {
        # --- Assets ---
        # Ids of the generations this session started and has not yet reported
        # on. The jobs themselves live in the backend; this is only how a
        # session knows which finished runs are *its* runs to announce.
        'asset_jobs': [],
        # Finished jobs waiting to be shown once, as success / warning / error.
        'job_notices': [],
        # Running-job count the library last saw, so it refreshes when one lands.
        'running_assets': 0,
        'create_error': None,
        'gallery_page': 0,
        # The world every page is looking at, and the one anything generated
        # here is written into.
        'current_world': None,
        # Paths ticked in the library, as strings, for a bulk move or copy. The
        # set - not the tile checkboxes - is the source of truth: a checkbox key
        # only exists while its tile is on screen, so a selection made before
        # paging would otherwise disappear.
        'selection': set(),
        # One-shot result of a move, copy or world edit, shown after the rerun
        # that performed it.
        'bulk_notice': None,
        # --- YouTube ---
        'search_job': None,
        'search_error': None,
        'search_keyword': '',
        # The saved search and channel being looked at. Mirrored into the URL
        # so a refresh reopens them.
        'search_id': None,
        'selected_channel': None,
    }
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value
