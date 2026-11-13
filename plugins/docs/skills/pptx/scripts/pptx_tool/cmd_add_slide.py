"""Add new slides to a deck from its own slide layouts, by layout name.

A template with layouts but no example slides (such as a brand's presentation
template) is filled this way: each new slide gets the layout's placeholders,
empty, ready for `add-text`, `add-table`, `add-chart` and `add-images`.
"""

import sys
import warnings
from pathlib import Path

from pptx import Presentation

from .cmd_select_slides import _next_available_slide_partname


def _layouts_by_name(prs) -> dict:
    """Map each layout name to its layout; the first layout of a name wins."""
    found = {}
    for master in prs.slide_masters:
        for layout in master.slide_layouts:
            found.setdefault(layout.name, layout)
    return found


def add_slides(prs, layout_names: list[str], position: int | None) -> list[int]:
    """Add one slide per layout name; return the 0-based index of each new slide."""
    layouts = _layouts_by_name(prs)
    missing = [n for n in layout_names if n not in layouts]
    if missing:
        raise ValueError(f"Unknown layout(s) {missing}. Layouts in the deck: {sorted(layouts)}")
    total = len(prs.slides)
    if position is not None and not 0 <= position <= total:
        raise ValueError(f"Position {position} out of range (0-{total})")

    sld_id_lst = prs.slides._sldIdLst
    landed = []
    for i, name in enumerate(layout_names):
        partname = _next_available_slide_partname(prs.part.package)
        slide = prs.slides.add_slide(layouts[name])
        slide.part.partname = partname
        if position is None:
            landed.append(len(prs.slides) - 1)
            continue
        sld_id = sld_id_lst[-1]
        sld_id_lst.remove(sld_id)
        sld_id_lst.insert(position + i, sld_id)
        landed.append(position + i)
    return landed


def run_add_slide(args) -> None:
    """Entry point from CLI dispatcher."""
    input_path = Path(args.input)
    output_path = Path(args.output)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)
    names = [n.strip() for n in args.layouts.split(",") if n.strip()]
    add_slides_to_file(input_path, output_path, names, args.position)


def add_slides_to_file(input_path: Path, output_path: Path, names: list[str], position: int | None) -> None:
    """Add one slide per layout name to the deck at input_path and save it to output_path. The edit
    command passes its layout list here, so a layout name may contain a comma."""
    if not names:
        print("Error: No layout name given")
        sys.exit(1)

    prs = Presentation(str(input_path))
    try:
        landed = add_slides(prs, names, position)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)
    for name, idx in zip(names, landed):
        print(f"  Added slide {idx}: {name}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='Duplicate name:')
        prs.save(str(output_path))
    print(f"Saved to: {output_path} ({len(prs.slides)} slides)")
