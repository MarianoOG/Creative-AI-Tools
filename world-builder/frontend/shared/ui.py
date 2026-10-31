"""Small UI pieces every page uses: error display, the image grid, navigation and plurals."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Sequence, Tuple, TypeVar

import streamlit as st

import api

#: Images per row in every grid.
COLUMNS = 3

T = TypeVar("T")


@contextmanager
def show_errors() -> Iterator[None]:
    """Show a refused or failed API call as an error and skip the rest of the block. Reruns pass through."""
    try:
        yield
    except api.ApiError as exc:
        st.error(str(exc))


def grid(items: Sequence[T], columns: int = COLUMNS) -> Iterator[Tuple[st.delta_generator.DeltaGenerator, T]]:
    """``(column, item)`` pairs that lay ``items`` out in rows of ``columns``."""
    for start in range(0, len(items), columns):
        yield from zip(st.columns(columns), items[start:start + columns])


def plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'s' if count != 1 else ''}"


def back_to_world_button() -> None:
    if st.button("Back to the world", icon=":material/arrow_back:"):
        st.switch_page("pages/world.py")


def open_asset(asset_type: str, name: str) -> None:
    st.session_state.current_asset = (asset_type, name)
    st.switch_page("pages/asset.py")


def open_script(episode: str) -> None:
    st.session_state.current_episode = episode
    st.switch_page("pages/script.py")
