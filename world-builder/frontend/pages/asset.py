"""Asset: one character, location or object. Edit its name and description, and generate, pick, regenerate and delete its variations.

Opens on ``current_asset``, or on the ``world``/``type``/``name`` query
parameters of a link from the World page. Every edit here changes
``world.json`` only; no image file is ever removed.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import streamlit as st

import api
from shared.state import notify, show_notice
from shared.worlds import model_select, render_world_switcher

UPLOAD_TYPES = ["png", "jpg", "jpeg", "webp"]
COLUMNS = 3
WAIT = "Generating... this can take a few minutes."


def take_link() -> None:
    """Open the asset a World-page link names, then drop the query parameters."""
    params = st.query_params
    if params.get('name') and params.get('type'):
        if params.get('world') and params['world'] != st.session_state.current_world:
            st.session_state.current_world = params['world']
            st.session_state.current_episode = st.session_state.current_scene = None
        st.session_state.current_asset = (params['type'], params['name'])
        st.query_params.clear()


def pick_asset(assets: List[Dict]) -> Optional[Dict]:
    keys = [(asset['asset_type'], asset['name']) for asset in assets]
    current = st.session_state.current_asset if st.session_state.current_asset in keys else keys[0]
    chosen = st.selectbox(
        "Asset", keys, index=keys.index(current), format_func=lambda key: f"{key[0].capitalize()} · {key[1]}"
    )
    st.session_state.current_asset = chosen
    return assets[keys.index(chosen)]


def body(asset: Dict, **fields) -> Dict:
    return {'world': asset['world'], 'asset_type': asset['asset_type'], 'name': asset['name'], **fields}


def finish(result: Dict, message: str) -> None:
    if result.get('warning'):
        notify('warning', result['warning'])
    notify('success', message)


def uploads_of(uploads: List) -> Optional[List]:
    return [('uploads', (upload.name, upload.getvalue(), upload.type)) for upload in uploads] or None


def render_details(asset: Dict) -> None:
    """Name and description. Saving edits ``world.json``; a rename also updates the scripts that use the asset."""
    key = f"{asset['asset_type']}_{asset['name']}"
    name = st.text_input("Name", value=asset['name'], key=f"name_{key}", help="Scenes that use it are updated too.")
    description = st.text_area("Description", value=asset['description'], height=110, key=f"description_{key}")
    changed = name.strip() != asset['name'] or description.strip() != asset['description']
    if st.button("Save", disabled=not changed, key=f"save_{key}"):
        try:
            saved = api.patch("/assets", json=body(asset, new_name=name, description=description))['asset']
        except api.ApiError as exc:
            st.error(str(exc))
            return
        st.session_state.current_asset = (asset['asset_type'], saved['name'])
        notify('success', "Saved. Regenerate the variations to apply a new description.")


def render_variation(asset: Dict, variation: Dict, provider: str) -> None:
    preferred = variation['name'] == asset['preferred']
    st.image(str(api.file_path(variation['path'])), width='stretch')
    st.markdown(f"**{variation['name']}**" + ("  ·  :material/star: preferred" if preferred else ""))
    st.caption(" · ".join(part for part in (variation['description'], variation['provider']) if part))
    key = f"{asset['asset_type']}_{asset['name']}_{variation['name']}"
    prefer_col, again_col, delete_col = st.columns(3)
    if prefer_col.button(":material/star:", disabled=preferred, key=f"prefer_{key}", width='stretch',
                         help="Make preferred: scenes that name the asset without a variation use this image."):
        api.patch("/assets", json=body(asset, preferred=variation['name']))
        notify('success', f"**{variation['name']}** is now preferred.")
    if again_col.button(":material/refresh:", key=f"again_{key}", width='stretch',
                        help="Regenerate from the current description. The old file stays on disk."):
        with st.spinner(WAIT):
            try:
                result = api.post("/assets/regenerate", json=body(asset, variation=variation['name'], provider=provider))
            except api.ApiError as exc:
                st.error(str(exc))
                return
        finish(result, f"Regenerated **{variation['name']}**.")
    with delete_col.popover(":material/delete:", width='stretch', help="Delete"):
        st.caption("Removes it from the asset. The image file stays in the data folder.")
        if st.button("Delete variation", icon=":material/delete:", key=f"delete_{key}"):
            api.delete("/assets", **body(asset, variation=variation['name']))
            notify('success', f"Removed **{variation['name']}**.")


def render_variations(asset: Dict, provider: str) -> None:
    variations = asset['variations']
    title_col, all_col = st.columns([3, 1])
    title_col.subheader("Views" if asset['asset_type'] == 'location' else "Variations")
    if variations and all_col.button("Regenerate all", width='stretch'):
        with st.spinner(f"Regenerating {len(variations)} image(s), one after another... this can take a while."):
            try:
                result = api.post("/assets/regenerate", json=body(asset, provider=provider))
            except api.ApiError as exc:
                st.error(str(exc))
                return
        finish(result, "Regenerated every variation.")
    if not variations:
        st.info("No images yet.")
    for row_start in range(0, len(variations), COLUMNS):
        for column, variation in zip(st.columns(COLUMNS), variations[row_start:row_start + COLUMNS]):
            with column:
                render_variation(asset, variation, provider)


def render_new_variation(asset: Dict, provider: str) -> None:
    key = f"{asset['asset_type']}_{asset['name']}"
    st.subheader("New variation")
    if asset['variations']:
        st.caption(f"Drawn from the preferred image (**{asset['preferred']}**), changed as described.")
    else:
        st.caption("The first variation is drawn from the description, and becomes the preferred one.")
    name = st.text_input("Variation name", placeholder="older", key=f"variation_name_{key}")
    change = st.text_area(
        "What is different (optional)", placeholder="Twenty years older, grey fur, a walking stick.",
        key=f"variation_change_{key}",
    )
    uploads = st.file_uploader(
        "Reference images (optional)", type=UPLOAD_TYPES, accept_multiple_files=True, key=f"variation_uploads_{key}",
        help="Inspiration, never the art style. Kept, so a regenerate uses them again.",
    ) or []
    if st.button("Generate variation", type="primary", disabled=not name.strip(), key=f"variation_go_{key}"):
        data = body(asset, variation=name, description=change, provider=provider)
        with st.spinner(WAIT):
            try:
                added = api.post("/assets/variations", data=data, files=uploads_of(uploads))['asset']
            except api.ApiError as exc:
                st.error(str(exc))
                return
        notify('success', f"Added **{added['variations'][-1]['name']}**.")


def render_new_views(asset: Dict, options: Dict, provider: str) -> None:
    have = {variation['name'] for variation in asset['variations']}
    missing = [view for view in options['location_views'] if view not in have]
    if not missing:
        return
    first = options['location_views'][0]
    st.subheader("Missing views")
    st.caption(
        f"Rendered one after another: {', '.join(missing)}. The {first} view comes from the description; "
        "the others are drawn from it."
    )
    uploads = []
    if first in missing:
        uploads = st.file_uploader(
            "Reference images (optional)", type=UPLOAD_TYPES, accept_multiple_files=True,
            key=f"views_uploads_{asset['name']}", help="Inspiration for the establishing view. Kept for regenerating.",
        ) or []
    if st.button(f"Generate {len(missing)} view(s)", type="primary", key=f"views_go_{asset['name']}"):
        with st.spinner(f"Rendering {len(missing)} view(s)... this can take a while."):
            try:
                result = api.post(
                    "/assets/views", data={'world': asset['world'], 'name': asset['name'], 'provider': provider},
                    files=uploads_of(uploads),
                )
            except api.ApiError as exc:
                st.error(str(exc))
                return
        finish(result, f"Rendered the views of **{asset['name']}**.")


def main() -> None:
    take_link()
    options = api.options()
    world, _ = render_world_switcher()
    if st.button("Back to the world", icon=":material/arrow_back:"):
        st.switch_page("pages/world.py")

    assets = api.get("/assets", world=world)['assets']
    if not assets:
        st.title("Asset")
        st.info(f"No assets in **{world}** yet. Create one from the World page.")
        return
    asset = pick_asset(assets)
    st.title(asset['name'])
    st.caption(f"{asset['asset_type'].capitalize()} in **{world}** · landscape, high quality")
    show_notice()

    render_details(asset)
    provider = model_select(options, key='asset_provider')
    st.caption("Every image generated or regenerated on this page uses this model.")
    st.divider()
    render_variations(asset, provider)
    st.divider()
    if asset['asset_type'] == 'location':
        render_new_views(asset, options, provider)
    else:
        render_new_variation(asset, provider)


main()
