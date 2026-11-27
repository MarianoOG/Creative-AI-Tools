"""Storyboard: an episode's final frames in a grid, their generation, and a zip of them all.

Like the Script page, the episode, the model and Export all frames are in the
sidebar, and a bar at the top (which stays on screen as the page scrolls) says
how many frames are done and has Generate for the missing ones.

Two frames per row, each with the shot's number and words under it, a warning
when the shot changed after its frame was made, and a Generate or Regenerate
button with its price (this world's average logged cost for the model, else a
rough list price).

A final frame is the finished image of a shot, rendered once by one of the Runware image models at 1K (the video's size) from
the shot's text and the designs of everything tagged on it (and the locations
tagged on its scene), in the world's style. Each one can be regenerated on its own (there is no "regenerate all": it
costs too much to be one click away); the old file stays on disk.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import streamlit as st

import api
from shared.state import show_notice
from shared.story import (
    build_zip, episode_url, excerpt, export_files, generate_shots, pick_episode, shot_label, shots_in_order,
)
from shared.ui import grid, plural, top_bar
from shared.worlds import render_world_switcher


#: Frames per row: two leave room for the shot's words and the button under each.
FRAME_COLUMNS = 2


def frame_price(world_costs: List[Dict], provider: str, estimates: Dict) -> Optional[float]:
    """What one frame costs with ``provider``: the average of this world's logged final frames by it,
    else the model's rough list price."""
    logged = [e['usd'] for e in world_costs if e['asset_type'] == "final" and e['provider'] == provider]
    return sum(logged) / len(logged) if logged else estimates.get(provider)


def price_label(usd: Optional[float]) -> str:
    """The price for a button. The dollar sign is escaped, as two in one label would render as LaTeX."""
    if usd is None:
        return "price varies"
    amount = f"{usd:.3f}"
    return f"~\\${amount[:-1] if amount.endswith('0') else amount}"  # 0.050 -> 0.05, 0.015 stays


def render_grid(world: str, episode: str, script: Dict, price: Optional[float]) -> List[Tuple[str, str]]:
    """Every shot's final frame, scene by scene, two per row, with its words and a priced Generate or
    Regenerate button under each. Returns the ``(label, shot id)`` of the ones clicked."""
    clicked = []
    for scene in script['scenes']:
        shots = [shot for shot in scene['shots'] if shot['id']]
        if not shots:
            continue
        st.subheader(f"{scene['number']}. {scene['heading']}")
        for column, shot in grid(shots, FRAME_COLUMNS):
            label = shot_label(scene, shot)
            with column:
                if shot.get('final_path'):
                    st.image(str(api.file_path(shot['final_path'])), width='stretch')
                else:
                    st.info(f"Shot {label}: no frame yet.")
                st.caption(f"**{label}** · {excerpt(shot['action'])}")
                warning_col, button_col = st.columns(2, vertical_alignment='center')
                if shot['final_stale']:
                    warning_col.warning("The shot changed after this frame.", icon=":material/sync_problem:")
                action = "Regenerate" if shot.get('final_path') else "Generate"
                if button_col.button(f"{action} · {price_label(price)}", key=f"final_{shot['id']}", width='stretch'):
                    clicked.append((label, shot['id']))
    return clicked


def render_sidebar(world: str, episode: str, script: Dict, options: Dict) -> str:
    """The model (saved on the episode as soon as it changes) and Export all frames. Returns the model."""
    providers = options['final_providers']
    key = f"final_provider_{world}_{episode}"
    with st.sidebar:
        provider = st.selectbox(
            "Model", providers, index=providers.index(script['final_provider']),
            format_func=options['providers'].get, key=key, help="Renders every frame generated from here.",
            on_change=lambda: api.patch(episode_url(world, episode), json={'final_provider': st.session_state[key]}),
        )
        files = export_files(script, 'final_path')
        # No "regenerate all": re-rendering every frame at once is too expensive to offer. One at a time only.
        st.download_button(
            "Export all frames", data=build_zip(files) if files else b"", file_name=f"{world}_{episode}.zip",
            mime="application/zip", icon=":material/download:", width='stretch', disabled=not files,
            help="A zip of every frame, named in story order." if files else "No frames yet.",
        )
    return provider


def main() -> None:
    world, _ = render_world_switcher()
    episode = pick_episode(world, st.sidebar)
    if not episode:
        return
    script = api.get(episode_url(world, episode))
    options = api.options()
    provider = render_sidebar(world, episode, script, options)
    shots = shots_in_order(script)
    price = frame_price(api.get(f"/worlds/{world}/costs")['entries'], provider, options['price_estimates'])
    missing = [(shot_label(scene, shot), shot['id']) for scene, shot in shots if not shot.get('final_path')]
    stale = sum(1 for _, shot in shots if shot['final_stale'])

    generate_all = False
    with top_bar():
        status_col, action_col = st.columns([3, 1.4], vertical_alignment='center')
        status = [f"{len(shots) - len(missing)} of {plural(len(shots), 'frame')} done"]
        if stale:
            status.append(f"{stale} made before their shot changed: regenerate them one at a time below")
        status_col.caption(" · ".join(status) if shots else "No shots yet.")
        total = price_label(price * len(missing) if price is not None else None)
        generate_all = action_col.button(
            f"Generate {plural(len(missing), 'frame')} · {total}" if missing else "Every shot has a frame",
            type="primary", width='stretch', disabled=not missing, icon=":material/auto_awesome:",
        )
    show_notice()
    if not shots:
        st.info("This episode has no shots yet. Write them on the Script page.")
        return
    if script['needs_ids']:
        st.info("Some shots were added outside the app and are not shown. Reprocess the file on the Script page.")

    clicked = render_grid(world, episode, script, price)
    to_generate = missing if generate_all else clicked
    if to_generate:
        generate_shots(world, episode, to_generate, "frame", {'provider': provider})


main()
