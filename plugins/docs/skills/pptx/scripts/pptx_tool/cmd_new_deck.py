"""Create a blank presentation to draw on.

Produces a plain white deck (default python-pptx template, Calibri) with N blank
slides (layout index 6). Intended as a canvas for `add-shapes`.
"""

import sys
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches

from .exceptions import ValidationError


# name -> (width_in, height_in)
SIZE_MAP = {
    "16:9": (13.333, 7.5),
    "4:3": (10.0, 7.5),
}


def create_deck(output_path: str, slides: int, size: str) -> None:
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

    prs.save(output_path)

    print(f"Saved presentation to: {output_path}")
    print(f"Slides: {slides}")
    print(f"Size: {size} ({width_in} x {height_in} in)")


def run_new_deck(args) -> None:
    """Entry point from CLI dispatcher."""
    try:
        create_deck(str(Path(args.output)), args.slides, args.size)
    except ValidationError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
