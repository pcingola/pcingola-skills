"""Create a blank presentation to draw on.

Produces a plain white deck (default python-pptx template, Calibri) with N blank
slides (layout index 6). Intended as a canvas for `add-shapes`.
"""

from dataclasses import dataclass
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches

from .exceptions import PptxError, ValidationError
from .pptx import print_unexpected_error


# name -> (width_in, height_in)
SIZE_MAP = {
    "16:9": (13.333, 7.5),
    "4:3": (10.0, 7.5),
}


@dataclass(frozen=True)
class NewDeck:
    """A deck written by `create_deck`: its path, slide count, aspect ratio name and size in inches."""
    output_path: Path
    slides: int
    size: str
    width_in: float
    height_in: float


def create_deck(output_path: Path | str, slides: int, size: str) -> NewDeck:
    """Create a blank deck with `slides` blank slides at the given aspect ratio."""
    if slides < 1:
        raise ValidationError(f"--slides must be >= 1 (got {slides})")

    if size not in SIZE_MAP:
        valid = ", ".join(sorted(SIZE_MAP))
        raise ValidationError(f"Unknown --size '{size}'. Valid: {valid}")

    width_in, height_in = SIZE_MAP[size]

    prs = Presentation()
    prs.slide_width = Inches(width_in)
    prs.slide_height = Inches(height_in)

    blank_layout = prs.slide_layouts[6]
    for _ in range(slides):
        prs.slides.add_slide(blank_layout)

    prs.save(str(output_path))
    return NewDeck(Path(output_path), slides, size, width_in, height_in)


def run_new_deck(args) -> int:
    """Entry point from CLI dispatcher."""
    output = str(Path(args.output))
    try:
        deck = create_deck(output, args.slides, args.size)
    except PptxError:
        raise
    except Exception as e:
        return print_unexpected_error(e)
    print(f"Saved presentation to: {output}")
    print(f"Slides: {deck.slides}")
    print(f"Size: {deck.size} ({deck.width_in} x {deck.height_in} in)")
    return 0
