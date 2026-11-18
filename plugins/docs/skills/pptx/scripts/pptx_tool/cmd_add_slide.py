"""Add new slides to a deck from its own slide layouts, by layout name.

A template with layouts but no example slides (such as a brand's presentation
template) is filled this way: each new slide gets the layout's placeholders,
empty, ready for `add-text`, `add-table`, `add-chart` and `add-images`.
"""

import warnings
from dataclasses import dataclass
from pathlib import Path

from pptx import Presentation

from .cmd_select_slides import _next_available_slide_partname
from .common import require_file
from .exceptions import PptxError


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


@dataclass(frozen=True)
class AddedSlide:
    """One slide `add-slide` added: its 0-based index and its layout name."""
    index: int
    layout: str


@dataclass(frozen=True)
class AddedSlides:
    """What `add_slides_to_file` did: the new slides in order, the output path and its slide count."""
    slides: list[AddedSlide]
    output_path: Path
    total: int


def add_slides_to_file(input_path: Path, output_path: Path, names: list[str], position: int | None) -> AddedSlides:
    """Add one slide per layout name to the deck at input_path and save it to output_path. The edit
    command passes its layout list here, so a layout name may contain a comma."""
    require_file(input_path, f"Input file not found: {input_path}")
    if not names:
        raise PptxError("No layout name given")

    prs = Presentation(str(input_path))
    try:
        landed = add_slides(prs, names, position)
    except ValueError as exc:
        raise PptxError(str(exc)) from None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='Duplicate name:')
        prs.save(str(output_path))
    return AddedSlides([AddedSlide(i, n) for n, i in zip(names, landed)], output_path, len(prs.slides))


def print_added_slides(result: AddedSlides) -> None:
    """Print the add-slide report: one line per new slide, then the saved path and slide count."""
    for slide in result.slides:
        print(f"  Added slide {slide.index}: {slide.layout}")
    print(f"Saved to: {result.output_path} ({result.total} slides)")


def run_add_slide(args) -> None:
    """Entry point from CLI dispatcher."""
    names = [n.strip() for n in args.layouts.split(",") if n.strip()]
    print_added_slides(add_slides_to_file(Path(args.input), Path(args.output), names, args.position))
