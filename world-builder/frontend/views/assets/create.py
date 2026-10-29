"""Create - generate assets from a description, a style and some references.

Characters, objects and locations take uploaded reference images, which the
backend keeps in a temporary directory for the length of the call and never
saves. Scenes instead pick any number of existing assets out of the library.

Every Generate click is its own background job in the backend, so the form
never locks: start one, tweak the description, start another. Leaving this
page cannot abandon a paid render, and each one is announced here when it lands.
"""

from __future__ import annotations

from typing import Dict, List

import streamlit as st

import api
from shared import jobs
from shared.worlds import render_world_switcher

LIBRARY_PAGE = "views/assets/library.py"

UPLOAD_TYPES = ["png", "jpg", "jpeg", "webp"]

#: What the ``None`` style is called on screen, and in the captions that explain it.
FOLLOW_LABEL = "Follow references"


def render_form(options: Dict) -> Dict:
    """The whole input side of the page.

    Returns only the fields ``main`` needs for its own rendering decisions;
    ``submit`` reads every field back off session state by widget key.
    """
    asset_type = st.radio(
        "Asset type",
        options['asset_types'],
        format_func=str.capitalize,
        horizontal=True,
        key='asset_type',
    )

    name = st.text_input(
        "Name",
        placeholder="fox_hero",
        help="Used for the filename. Spaces and punctuation become underscores.",
        key='asset_name',
    )
    description = st.text_area(
        "Description",
        placeholder=(
            "the fox hero holds the lantern up in the night market"
            if asset_type == "scene"
            else "a lanky fox in a patched wool coat, tall ears, tired eyes"
        ),
        help=(
            "The situation to depict."
            if asset_type == "scene"
            else "The subject to design."
        ),
        height=120,
        key='asset_description',
    )

    style_col, ratio_col, quality_col = st.columns(3)
    style = style_col.selectbox(
        "Style",
        options['styles'],
        format_func=lambda s: FOLLOW_LABEL if s is None else s,
        key='style',
    )
    ratio_col.selectbox("Aspect ratio", options['aspect_ratios'], key='aspect_ratio')
    quality_col.selectbox("Quality", options['qualities'], key='quality')

    return {
        'asset_type': asset_type,
        'name': name,
        'description': description,
        'style': style,
    }


def selected_references(asset_type: str, reference_types: List[str]) -> List:
    """The reference widgets' current values: library paths for a scene,
    uploaded files otherwise.

    Branching on ``asset_type`` matters: the keys of the other branch survive in
    session state, so a scene would otherwise see uploads left behind by a
    character. Only meaningful once the reference section has been rendered on
    this run.
    """
    state = st.session_state
    if asset_type == "scene":
        return [
            path
            for reference_type in reference_types
            for path in state.get(f"scene_refs_{reference_type}") or []
        ]
    return list(state.get('uploads') or [])


def render_upload_references(follow: bool) -> None:
    """Uploader for character / object / location. Nothing here is saved.

    ``follow`` flips the caption: with no style picked these images are the
    source of the art style rather than the one thing never taken from them.
    """
    st.subheader("Reference images")
    st.caption(
        "Required here: the art style is copied from these images. "
        "These files are not saved."
        if follow
        else "Optional. Used as inspiration for the world, palette and mood - "
        "never for the art style. These files are not saved."
    )
    st.file_uploader(
        "Upload references",
        type=UPLOAD_TYPES,
        accept_multiple_files=True,
        key='uploads',
    )


def render_library_references(follow: bool, world: str, reference_types: List[str]) -> None:
    """Multi-select the existing sheets a scene should reproduce.

    Scoped to ``world``: a scene belongs to one setting, so the assets it can be
    built from are exactly that setting's. The backend enforces the same rule
    again on the way in.
    """
    st.subheader("Reference assets")
    st.caption(
        "Scenes treat these as authority: the designs are reproduced faithfully. "
        f"Pick any number of characters, objects and locations from **{world}**."
        + (
            " With no style picked each one also keeps its own art style, so "
            "the frame is not unified into one look."
            if follow
            else ""
        )
    )

    labels: Dict[str, str] = {}
    selected: List[str] = []
    for column, asset_type in zip(st.columns(len(reference_types)), reference_types):
        options = api.get("/assets", world=world, asset_type=asset_type)['assets']
        labels.update({asset['path']: asset['label'] for asset in options})
        with column:
            if not options:
                st.caption(f"No {asset_type}s in this world yet.")
                continue
            selected.extend(
                st.multiselect(
                    f"{asset_type.capitalize()}s",
                    [asset['path'] for asset in options],
                    format_func=lambda path: labels.get(path, path),
                    key=f"scene_refs_{asset_type}",
                )
            )

    if selected:
        for column, path in zip(st.columns(min(len(selected), 6)), selected):
            column.image(str(api.file_path(path)), caption=labels.get(path), width='stretch')


def submit(reference_types: List[str]) -> None:
    """Button callback: hand the form to the backend as one new job.

    Runs before the rerun paints, so the running-jobs panel already shows the
    new job on the next frame.
    """
    state = st.session_state
    asset_type = state.asset_type
    references = selected_references(asset_type, reference_types)

    data = {
        'asset_type': asset_type,
        'name': state.asset_name,
        'description': state.asset_description,
        'aspect_ratio': state.aspect_ratio,
        'quality': state.quality,
        'world': state.current_world,
    }
    # Left out entirely for "Follow references": a form field cannot be None.
    if state.style is not None:
        data['style'] = state.style

    files = []
    if asset_type == "scene":
        data['references'] = references
    else:
        files = [
            ('uploads', (upload.name, upload.getvalue(), upload.type))
            for upload in references
        ]

    try:
        jobs.track(api.post("/assets/generate", data=data, files=files or None))
        state.create_error = None
    except api.ApiError as exc:
        state.create_error = str(exc)


@st.fragment(run_every=2)
def watch_jobs() -> None:
    """Poll this session's jobs without rerunning the rest of the page."""
    running = [job for job in jobs.my_jobs() if job['status'] in jobs.ACTIVE]
    if len(running) < len(st.session_state.asset_jobs):
        # One landed: the full rerun collects it and shows its notice.
        st.rerun(scope="app")
        return

    with st.status(
        f"{len(running)} generation{'s' if len(running) != 1 else ''} in progress...",
        expanded=True,
    ):
        for job in running:
            st.write(f"{'⏳' if job['status'] == 'queued' else '🎨'} {job['label']}")
        st.caption(
            "Running in the background. You can keep creating or leave this "
            "page - every image is saved either way."
        )


def main() -> None:
    options = api.options("assets")
    jobs.collect()

    world, _ = render_world_switcher()

    st.title("✨ Create an asset")
    st.caption(
        f"Generating into **{world}**. Characters, objects and locations are "
        "reference sheets; scenes are finished frames."
    )

    if st.button("← Back to library"):
        st.switch_page(LIBRARY_PAGE)

    jobs.show_notices()
    if st.session_state.asset_jobs:
        watch_jobs()

    st.divider()
    fields = render_form(options)

    st.divider()
    follow = fields['style'] is None
    reference_types = options['reference_types']
    if fields['asset_type'] == "scene":
        render_library_references(follow, world, reference_types)
    else:
        render_upload_references(follow)

    st.divider()
    # With no style picked there is nothing to render from - the backend
    # rejects it without references, so the button is held instead.
    missing_references = follow and not selected_references(fields['asset_type'], reference_types)
    ready = bool(fields['name'].strip() and fields['description'].strip()) and not missing_references
    st.button(
        "Generate",
        type="primary",
        disabled=not ready,
        on_click=submit,
        args=(reference_types,),
    )
    if not (fields['name'].strip() and fields['description'].strip()):
        st.caption("A name and a description are required.")
    if missing_references:
        st.caption(
            f"**{FOLLOW_LABEL}** takes the look from the references, so at "
            "least one is required."
        )

    if st.session_state.create_error:
        st.error(st.session_state.create_error)


main()
