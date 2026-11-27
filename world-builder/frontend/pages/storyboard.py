"""Storyboard: an episode's final frames in a grid, their generation, and a zip of them all.

Two frames per row, each with the shot's number and words under it, a warning
when the shot changed after its frame was made, and a Generate or Regenerate
button with its price (this world's average logged cost for the model, else a
rough list price).

A final frame is the finished image of a shot, rendered once by OpenAI, Gemini or Runware (Flux 2 Klein) at 1K (the video's size) from
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
from shared.ui import grid
from shared.worlds import render_world_switcher


#: Frames per row: two leave room for the shot's words and the button under each.
FRAME_COLUMNS = 2


def frame_price(world_costs: List[Dict], provider: str, estimates: Dict) -> Optional[float]:
    """What one frame costs with ``provider``: the average of this world's logged final frames by it,
    else the provider's rough list price (``None`` for OpenAI, which bills per token)."""
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


def main() -> None:
    world, _ = render_world_switcher()
    st.title("Storyboard")
    episode = pick_episode(world)
    if not episode:
        return
    script = api.get(episode_url(world, episode))
    show_notice()
    shots = shots_in_order(script)
    if not shots:
        st.info("This episode has no shots yet. Write them on the Script page.")
        return
    if script['needs_ids']:
        st.info("Some shots were added outside the app and are not shown. Reprocess the file on the Script page.")

    options = api.options()
    providers = options['final_providers']
    model_col, action_col = st.columns([3, 2], vertical_alignment='bottom')
    provider = model_col.selectbox(
        "Model", providers, index=providers.index(script['final_provider']),
        format_func=options['providers'].get, key=f"final_provider_{world}_{episode}",
    )
    price = frame_price(api.get(f"/worlds/{world}/costs")['entries'], provider, options['price_estimates'])
    missing = [(shot_label(scene, shot), shot['id']) for scene, shot in shots if not shot.get('final_path')]

    def batch_price(count: int) -> str:
        return price_label(price * count if price is not None else None)

    generate_all = False
    with action_col:
        if missing:
            generate_all = st.button(
                f"Generate {len(missing)} frame(s) · {batch_price(len(missing))}", type="primary", width='stretch'
            )
        else:
            # No "regenerate all": re-rendering every frame at once is too expensive to offer. One at a time only.
            st.download_button(
                "Export all frames", data=build_zip(export_files(script, 'final_path')), file_name=f"{world}_{episode}.zip",
                mime="application/zip", type="primary", icon=":material/download:", width='stretch',
            )

    st.divider()
    stale = sum(1 for _, shot in shots if shot['final_stale'])
    if stale:
        st.caption(f"{stale} frame(s) were made before their shot changed. Regenerate them one at a time below.")
    clicked = render_grid(world, episode, script, price)
    to_generate = missing if generate_all else clicked
    if to_generate:
        generate_shots(world, episode, to_generate, "frame", {'provider': provider})


main()
