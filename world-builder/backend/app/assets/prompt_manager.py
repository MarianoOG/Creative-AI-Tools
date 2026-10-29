"""Prompt composition for the four asset types this pipeline produces.

Pure data plus one function — no I/O, no API calls. A prompt is always assembled
in the same order:

    description -> style clause -> per-type framing rules -> reference clause

The framing rules are the part that must never drift: characters and objects are
*reference sheets* consumed by later animation steps, so their layout (white
background, fixed set of views) is fixed here rather than left to the caller.

Framing is composed *after* the style clause, so it has the last word on colour
and lighting. Where that would contradict the chosen style — a monochrome
line-only style against a framing that asks for a colour grade —
:data:`STYLE_FRAMING` swaps in a variant for that ``(style, asset_type)`` pair.

The ``style=None`` mode
-----------------------
``style=None`` names no style at all and hands that job to the attached images.
Because that inverts what the normal clauses say, it swaps in a parallel set so
nothing in the composed prompt contradicts it:

- style clause    -> :data:`FOLLOW_REFERENCES_CLAUSE`
- reference clause-> :data:`FOLLOW_REFERENCE_CLAUSES` (the normal ones say the
  style clause *overrides* the references — the exact opposite)
- framing         -> :data:`FOLLOW_FRAMING` where one exists (only the scene: its
  usual "one unified grade" sentence would fight per-element styling)

Being styleless it is meaningless without references, so :func:`build_prompt`
rejects that combination rather than spend a paid call on it. On disk these
renders are written under :data:`REFERENCE_STYLE_SLUG`, since the filename's
style slot still has to hold something the gallery can group on.
"""

from __future__ import annotations

from typing import Literal, Optional

AssetType = Literal["character", "object", "location", "scene"]

#: Asset type -> the subdirectory of ``img/`` its renders belong in.
ASSET_DIRS: dict[str, str] = {
    "character": "characters",
    "object": "objects",
    "location": "locations",
    "scene": "scenes",
}

#: Style slug -> the clause injected into the prompt. Every style is an animation
#: style; they differ in medium, linework, palette and lighting. These are written
#: long on purpose — a one-word style label ("anime") leaves the model to average
#: over decades of wildly different work and the output turns to mush.
STYLES: dict[str, str] = {
    "flat_2d": (
        "Modern flat 2D vector animation style: clean uniform-weight outlines, "
        "large areas of flat unshaded colour, simple geometric shape language, a "
        "limited bright palette of six to eight hues, no gradients and no texture."
    ),
    "anime_cel": (
        "Japanese cel-animation style: crisp dark ink outlines of varying weight, "
        "two-tone cel shading with hard-edged shadow shapes, saturated but "
        "naturalistic colour, expressive large eyes, subtle rim light on the "
        "silhouette."
    ),
    "pixar_3d": (
        "Polished 3D CG animated-feature style: soft rounded appealing forms, "
        "subsurface-scattering skin, physically based materials, warm cinematic "
        "three-point lighting with soft shadows, shallow depth of field, high "
        "render fidelity."
    ),
    "stop_motion_clay": (
        "Handmade stop-motion claymation style: visible fingerprints and tool "
        "marks in the plasticine, slightly lumpy hand-sculpted forms, matte clay "
        "surface, practical soft studio lighting with real contact shadows, "
        "tangible miniature-set feel."
    ),
    "watercolor_storybook": (
        "Hand-painted watercolour storybook style: soft wet-on-wet colour washes "
        "with visible pigment blooms and paper grain, loose graphite underdrawing "
        "showing through, muted earthy palette, gentle diffuse light, edges that "
        "fade rather than stop."
    ),
    "comic_ink": (
        "Bold inked comic-book style: heavy brush-inked contours, dense "
        "cross-hatching and spotted blacks for shadow, halftone dot texture in the "
        "midtones, punchy high-contrast primary colours, dramatic directional "
        "lighting."
    ),
    "retro_cartoon_1930s": (
        "1930s rubber-hose cartoon style: bendy limbs without visible joints, "
        "pie-cut eyes and white gloves, thick tapering ink lines, sepia and "
        "cream limited palette with soft film grain and subtle vignetting, "
        "vintage animation-cel look."
    ),
    "pixel_art": (
        "Hand-crafted pixel art style: low resolution grid with large crisp square "
        "pixels and no anti-aliasing, deliberate dithering for gradients, a tight "
        "indexed palette of about sixteen colours, strong readable silhouettes, "
        "16-bit era game-sprite look."
    ),
    "low_poly_3d": (
        "Stylised low-poly 3D style: faceted geometry with visible flat triangular "
        "planes, hard flat-shaded facets and no smoothing, untextured solid colour "
        "materials, clean studio lighting, crisp geometric silhouette."
    ),
    "paper_cutout": (
        "Layered paper cutout animation style: shapes cut from textured coloured "
        "card with visible fibrous torn and scissor-cut edges, distinct stacked "
        "depth layers casting small soft drop shadows onto the layer beneath, matte "
        "paper surface."
    ),
    "ligne_claire_color": (
        "Ligne claire children's book illustration style in the Tintin and Hergé "
        "tradition: bold uniform-weight black outlines around every object and "
        "shape, flat solid fills with no gradients, no soft shading, no painterly "
        "texture and no photorealistic lighting. Real locations and objects stay "
        "clearly recognisable in their proportions and layout but are rendered as "
        "clean illustration, with simplified textures — wood grain as a few clean "
        "lines, foliage as solid rounded masses, ground as one flat tone with "
        "minimal detail. Warm inviting palette, high contrast, evenly lit with no "
        "dramatic shadow work. Print-ready flat illustration, not a render."
    ),
    "ligne_claire_lineart": (
        "Pure ligne claire line art: black outlines only on a white background, "
        "with nothing filled in, no shading, no crosshatching and no gradients. "
        "Uniform line weight throughout. Every shape is defined entirely by clean "
        "confident black contour lines, so objects and locations stay clearly "
        "recognisable by silhouette and structure alone. Ready for print or "
        "colouring-book use."
    ),
}

#: Stands in for the :data:`STYLES` clause when ``style`` is ``None``. Not a
#: style key — see the module docstring.
FOLLOW_REFERENCES_CLAUSE = (
    "Do not apply any predetermined art style to this image. The art style is "
    "defined entirely by the attached reference images: match their medium, "
    "linework, shading, colour palette, level of detail and finish so closely "
    "that this image could sit in the same production as them. Invent no "
    "stylistic treatment of your own, and do not modernise, tidy up or raise "
    "the fidelity of what the references show."
)

#: What a ``style=None`` render is called on disk. Deliberately *not* a
#: :data:`STYLES` key.
REFERENCE_STYLE_SLUG = "follow_references"

#: The invariant part of a character prompt. These renders are turnaround sheets
#: used as identity references for later animation, so the pose and view order
#: must be identical every time.
CHARACTER_FRAMING = (
    "Render this as a character turnaround reference sheet. Pure solid white "
    "seamless background. Full body, head to feet, standing upright in a neutral "
    "relaxed A-pose with the arms held slightly away from the torso and the legs "
    "straight. Show exactly three views of the same character in a single image, "
    "arranged in one horizontal row, left to right: front view, side profile "
    "view, back view. All three views share the same character design, the same "
    "scale, the same height, and the same eye line. Even flat lighting with no "
    "cast shadow on the backdrop. No props, no accessories beyond the described "
    "costume, no scenery, no text, no labels, no borders or panel frames."
)

#: Object sheets mirror the character sheet: same white field, fixed views, but
#: orthographic — front and side only, which is what modelling and animation read
#: the form from. The negative clause earns its place: "reference sheet" alone
#: pulls these models back towards a three-view turnaround.
OBJECT_FRAMING = (
    "Render this as an object turnaround reference sheet. Pure solid white "
    "seamless background. Show exactly two orthographic views of the same object "
    "in a single image, arranged in one horizontal row, left to right: front view "
    "along the Z axis, side view along the X axis. Exactly two views and no "
    "others — no top view, no back view, no perspective view. Both views share "
    "the same object design, scale and lighting. The object is isolated and "
    "centred in each view. Even flat lighting, no cast shadow on the backdrop, no "
    "ground plane. No characters, no people, no hands holding the object, no "
    "text, no labels, no dimension lines, no borders."
)

#: Locations are background plates that characters get composited over later, so
#: the "no people" instruction is repeated several ways on purpose — it is the
#: single constraint these renders most often break. Split around its one
#: style-dependent sentence, the way the scene framing is: see
#: :data:`LOCATION_FRAMING_MONOCHROME`.
_LOCATION_COMPOSITION = (
    "Render this as an empty background plate for animation. The environment is "
    "completely unoccupied: no characters, no people, no figures, no crowds, no "
    "animals, and no foreground subject of any kind anywhere in the frame. Wide "
    "establishing view of the space itself with a consistent single-point "
    "perspective and a clear horizon. "
)
_LOCATION_TAIL = "No text, no signage lettering, no watermarks, no borders."

LOCATION_FRAMING = (
    _LOCATION_COMPOSITION
    + "Light the environment as a usable backdrop, readable across the whole "
    "frame with nothing blown out and nothing crushed to black. "
    + _LOCATION_TAIL
)

#: Scenes are finished frames rather than reference sheets, so the framing is
#: about composition and consistency instead of fixed views. Split around its one
#: style-dependent sentence: see :data:`SCENE_FRAMING_PER_ELEMENT`.
_SCENE_COMPOSITION = (
    "Render this as a single finished composed frame depicting the situation "
    "described above. Compose it cinematically with a clear focal subject, a "
    "readable staging of every element mentioned, and depth between foreground, "
    "midground and background. Keep the characters, objects and environment "
    "exactly consistent with their reference designs. "
)
_SCENE_TAIL = "No text, no captions, no borders."

SCENE_FRAMING = (
    _SCENE_COMPOSITION
    + "Unified lighting and colour grade across the whole frame. "
    + _SCENE_TAIL
)

#: The scene framing minus the unified-grade sentence, used only when ``style``
#: is ``None``. That case keeps every element in the look of its own reference,
#: so asking for one grade across the frame in the same prompt would be asking
#: for two opposite things at once — and a contradiction is worse than either
#: instruction alone. Every named style keeps the sentence.
SCENE_FRAMING_PER_ELEMENT = _SCENE_COMPOSITION + _SCENE_TAIL

FRAMING: dict[str, str] = {
    "character": CHARACTER_FRAMING,
    "object": OBJECT_FRAMING,
    "location": LOCATION_FRAMING,
    "scene": SCENE_FRAMING,
}

#: The sentence a monochrome line-only style puts where the colour framings talk
#: about lighting and grade. Both of those fight a black-line-on-white look head
#: on, and framing is composed *after* the style clause, so they would have the
#: last word — a contradiction is worse than either instruction alone.
_MONOCHROME_RENDERING = (
    "Describe the whole frame with black contour lines alone: depth and "
    "separation come from overlap, scale and line, never from tone, fill or "
    "shadow. "
)

#: :data:`LOCATION_FRAMING` with its lighting sentence swapped out — that one
#: asks for nothing crushed to black, which is exactly what solid black contours
#: on white are.
LOCATION_FRAMING_MONOCHROME = (
    _LOCATION_COMPOSITION + _MONOCHROME_RENDERING + _LOCATION_TAIL
)

#: :data:`SCENE_FRAMING` with its unified-grade sentence swapped out. Distinct
#: from :data:`SCENE_FRAMING_PER_ELEMENT`, which drops that sentence for the
#: opposite reason (per-element styling) and belongs to ``style=None``.
SCENE_FRAMING_MONOCHROME = (
    _SCENE_COMPOSITION + _MONOCHROME_RENDERING + _SCENE_TAIL
)

#: ``(style, asset_type)`` -> the framing that replaces :data:`FRAMING` for that
#: pair. Only the styles whose look contradicts a framing constant need an entry;
#: character and object sheets are already white-background and flat-lit, so they
#: fall through for every style.
STYLE_FRAMING: dict[tuple[str, str], str] = {
    ("ligne_claire_lineart", "location"): LOCATION_FRAMING_MONOCHROME,
    ("ligne_claire_lineart", "scene"): SCENE_FRAMING_MONOCHROME,
}

#: How the reference images are meant to be *used* — and this differs sharply by
#: asset type, so there is one clause per type rather than one shared clause.
#:
#: Characters, objects and locations treat references as **inspiration**: they
#: pull world, palette and mood across so the new asset belongs beside what it
#: was shown, while the style always comes from this prompt's style clause, never
#: from the reference image. Scenes treat references as **authority**: the scene
#: is the composer, so the designs it was handed are facts to reproduce.
REFERENCE_CLAUSES: dict[str, str] = {
    "character": (
        "Reference images are provided as inspiration, not as something to copy. "
        "Do not adopt the art style, rendering, linework or medium of the "
        "reference images — the style is defined by the style description above "
        "and overrides anything seen in the references. If a reference shows "
        "another character, do not reproduce or clone that character: take only "
        "cues such as the world it belongs to, its palette, its costume language "
        "and its level of stylisation, so the new character plausibly lives "
        "alongside it. If a reference shows an object or a place instead, read the "
        "colours, materials, era and mood from it and design a character who "
        "would inhabit that world and use those objects. The described character "
        "above is always the subject; the references only inform it."
    ),
    "object": (
        "Reference images are provided as inspiration, not as something to copy. "
        "Do not adopt the art style, rendering, linework or medium of the "
        "reference images — the style is defined by the style description above "
        "and overrides anything seen in the references. If a reference shows "
        "another object, take only cues such as its materials, wear, construction "
        "language and palette so the new object reads as belonging to the same "
        "world and the same maker, without duplicating it. If a reference shows a "
        "character or a place instead, extract the palette, mood, era and material "
        "vocabulary and design an object that would belong in that world or be "
        "carried and used by that character, scaled and shaped to suit them. The "
        "described object above is always the subject; the references only inform it."
    ),
    "location": (
        "Use the reference images as the source of the world: carry across their "
        "palette, mood, era, architecture, materials and recurring design "
        "elements. Build the described location as a spin-off of that world — a "
        "neighbouring, adjacent or related place, not a reproduction of any place "
        "shown. If a reference shows characters or objects, do not include them in "
        "the frame; instead treat them as the inhabitants this plate must suit, and "
        "build a background they could plausibly stand in or that those objects "
        "would be found in, matched to their scale and their world. The style is "
        "defined by the style description above and overrides the rendering of the "
        "references."
    ),
    "scene": (
        "Use the attached reference images as the authority for this frame. They "
        "are fact, not inspiration: reproduce the identity, design, proportions, "
        "costume, materials and colour palette of every subject they depict "
        "faithfully and consistently. Do not redesign, restyle, simplify or "
        "substitute them — a viewer must recognise each one as the same character, "
        "object and place. Where a reference shows an environment, keep its layout, "
        "architecture and palette as the setting of this frame. Ignore only the "
        "sheet layout of the references themselves (the multiple views and the "
        "blank backdrop); their designs are what carry over."
    ),
}


#: Character, object and location share one ``style=None`` clause: the per-type
#: differences in :data:`REFERENCE_CLAUSES` are all about what to *extract* from a
#: mismatched reference, and that question disappears once the references are
#: simply the source of the rendering.
_FOLLOW_SHEET_CLAUSE = (
    "The reference images are the authority for how this image is drawn: "
    "reproduce their medium, linework, shading, colour palette and level of "
    "detail exactly. They are not the authority for what is drawn — the subject "
    "described above is the subject, and must not be replaced by, or cloned from, "
    "anything a reference happens to depict. Where the references disagree with "
    "each other, follow the one whose subject is closest to the described one. "
    "The framing rules above still win over anything the references show: a "
    "background plate stays empty even if every reference is crowded with "
    "characters, and a turnaround sheet keeps its white backdrop and its fixed "
    "views even if the references are finished frames."
)

#: Scenes need their own: this is the case where "keep the style of each element"
#: bites, and it has to say so explicitly because SCENE_FRAMING asks for a
#: unified grade. Reference clauses are appended last, so this has the final word.
_FOLLOW_SCENE_CLAUSE = (
    "The reference images are the authority for this frame twice over: for the "
    "identity, design, proportions, costume and materials of every subject they "
    "depict, and for how each one is drawn. Reproduce each element in the art "
    "style of the reference it came from — its medium, linework, shading and "
    "palette — rather than restyling it. Do not unify the elements into a single "
    "house style or a single colour grade; where the references are drawn "
    "differently, that difference is kept in this frame. Share only the staging "
    "and the direction of the light, so the frame still reads as one image. "
    "Ignore only the sheet layout of the references themselves (the multiple "
    "views and the blank backdrop); their designs and their rendering carry over."
)

FOLLOW_REFERENCE_CLAUSES: dict[str, str] = {
    "character": _FOLLOW_SHEET_CLAUSE,
    "object": _FOLLOW_SHEET_CLAUSE,
    "location": _FOLLOW_SHEET_CLAUSE,
    "scene": _FOLLOW_SCENE_CLAUSE,
}

#: Framing overrides for ``style=None``. Only the scene needs one; the sheet
#: layouts are style-independent and fall through to :data:`FRAMING`.
FOLLOW_FRAMING: dict[str, str] = {"scene": SCENE_FRAMING_PER_ELEMENT}


def build_prompt(
    asset_type: AssetType,
    description: str,
    style: Optional[str],
    with_references: bool = False,
) -> str:
    """Compose the full prompt for one asset.

    ``description`` carries everything specific to this asset. For a character,
    object or location that is the subject description; for a scene it is the
    situation being depicted ("the fox hero holds the lantern up in the night
    market") — there is no separate situation argument.

    ``with_references`` appends this asset type's clause from
    :data:`REFERENCE_CLAUSES`; the caller sets it when it is actually attaching
    images. Character, object and location treat references as inspiration;
    scene treats them as authority.

    ``style=None`` takes the art style from the references instead of naming one,
    and so requires at least one — see the module docstring.
    """
    if asset_type not in FRAMING:
        raise ValueError(
            f"asset_type must be one of {sorted(FRAMING)}, got {asset_type!r}"
        )
    if style is not None and style not in STYLES:
        raise ValueError(
            f"style must be None or one of {sorted(STYLES)}, got {style!r}"
        )
    if not description or not description.strip():
        raise ValueError("description must not be empty")

    follow = style is None
    if follow and not with_references:
        raise ValueError(
            "style None takes its style from the reference images, so at least "
            "one reference image is required"
        )

    framing = (
        FOLLOW_FRAMING.get(asset_type)
        if follow
        else STYLE_FRAMING.get((style, asset_type))
    )
    style_clause = FOLLOW_REFERENCES_CLAUSE if follow else STYLES[style]
    parts = [description.strip(), style_clause, framing or FRAMING[asset_type]]
    if with_references:
        clauses = FOLLOW_REFERENCE_CLAUSES if follow else REFERENCE_CLAUSES
        parts.append(clauses[asset_type])
    return "\n\n".join(parts)
