"""Storyboard: an episode's final frames in a grid, their generation, and a zip of them all.

Two frames per row, each with one line under it: the shot's type (saved as soon
as it changes) and a Generate or Regenerate button with its price (this
world's average logged cost for the model, else a rough list price).

A final frame is the finished image of a shot, rendered once by OpenAI, Gemini or Runware (Flux 2 Klein) at 1K (the video's size) from
the shot's text and the designs of everything the scene lists, in the world's
style. Each one can be regenerated on its own (there is no "regenerate all": it
costs too much to be one click away); the old file stays on disk.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import streamlit as st

import api
from shared.state import show_notice
from shared.story import (
    build_zip, episode_url, export_files, generate_shots, pick_episode, save_shot_setting, shots_in_order,
)
from shared.ui import grid
from shared.worlds import render_world_switcher


#: Frames per row: two leave room for the shot type and the button on one line under each.
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


def render_grid(world: str, episode: str, script: Dict, shot_types: List[str], price: Optional[float]) -> List[Tuple[str, str]]:
    """Every shot's final frame, scene by scene, two per row, with one line under each: the shot type
    (saved as soon as it changes) and a priced Generate or Regenerate button. Returns the ones clicked."""
    clicked = []
    for scene in script['scenes']:
        if not scene['shots']:
            continue
        st.subheader(scene['heading'] or scene['id'])
        for column, shot in grid(scene['shots'], FRAME_COLUMNS):
            with column:
                if shot.get('final_path'):
                    st.image(str(api.file_path(shot['final_path'])), width='stretch')
                else:
                    st.info(f"`{shot['id']}`: no frame yet.")
                type_col, button_col = st.columns(2, vertical_alignment='center')
                key = f"shot_type_{world}_{episode}_{scene['id']}_{shot['id']}_{st.session_state.script_revision}"
                type_col.selectbox(
                    "Shot type", shot_types, index=shot_types.index(shot['type']) if shot['type'] in shot_types else None,
                    placeholder="Shot type", label_visibility='collapsed', help=f"{shot['id']}: shot type", key=key,
                    on_change=save_shot_setting, args=(world, episode, scene['id'], shot['id'], 'type', key, True),
                )
                label = "Regenerate" if shot.get('final_path') else "Generate"
                if button_col.button(f"{label} · {price_label(price)}", key=f"final_{scene['id']}_{shot['id']}",
                                     width='stretch'):
                    clicked.append((scene['id'], shot['id']))
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

    options = api.options()
    providers = options['final_providers']
    model_col, action_col = st.columns([3, 2], vertical_alignment='bottom')
    provider = model_col.selectbox(
        "Model", providers, index=providers.index(script['final_provider']),
        format_func=options['providers'].get, key=f"final_provider_{world}_{episode}",
    )
    price = frame_price(api.get(f"/worlds/{world}/costs")['entries'], provider, options['price_estimates'])
    missing = [(scene['id'], shot['id']) for scene, shot in shots if not shot.get('final_path')]

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
    clicked = render_grid(world, episode, script, options['shot_types'], price)
    to_generate = missing if generate_all else clicked
    if to_generate:
        generate_shots(world, episode, to_generate, "frame", {'provider': provider})


main()
