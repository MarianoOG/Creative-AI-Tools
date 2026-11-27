"""Small UI pieces every page uses: the top bar and its view picker, error display, the image grid,
navigation and plurals."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Dict, Iterator, Sequence, Tuple, TypeVar

import streamlit as st

import api

#: Images per row in every grid.
COLUMNS = 3

T = TypeVar("T")


@contextmanager
def top_bar() -> Iterator[None]:
    """A page's top bar: one row that stays on screen as the page scrolls (styled in ``app.py``).
    It holds the page's views and its main actions, in place of a title."""
    with st.container(key="top_bar"):
        yield


def view_picker(views: Dict[str, str], state_key: str, container=st) -> str:
    """A segmented picker of ``views`` (name -> icon) that remembers the choice in ``state_key`` across
    pages. Clicking the picked view again keeps it (a segmented control would otherwise unselect it)."""
    widget_key = f"{state_key}_pick"
    if st.session_state.get(state_key) not in views:
        st.session_state[state_key] = next(iter(views))
    if st.session_state.get(widget_key) is None:
        st.session_state[widget_key] = st.session_state[state_key]

    def keep() -> None:
        if st.session_state[widget_key] is None:
            st.session_state[widget_key] = st.session_state[state_key]
        else:
            st.session_state[state_key] = st.session_state[widget_key]

    container.segmented_control("View", list(views), format_func=lambda name: f"{views[name]} {name}",
                                key=widget_key, on_change=keep, label_visibility='collapsed')
    return st.session_state[state_key]


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
