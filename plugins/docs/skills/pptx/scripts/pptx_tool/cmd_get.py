"""Read a single shape's text content by slide-N/shape-N path, or a slide's
speaker notes by slide-N/notes."""

import sys
from pathlib import Path

from pptx import Presentation

from .cmd_extract_shapes import extract_text


def _run_get_notes(input_path: Path, slide_key: str) -> None:
    prs = Presentation(str(input_path))
    try:
        slide_index = int(slide_key.split("-")[1])
    except (IndexError, ValueError):
        print(f"Error: Invalid slide key '{slide_key}'")
        sys.exit(1)

    if slide_index < 0 or slide_index >= len(prs.slides):
        print(f"Error: Slide index {slide_index} out of range (0-{len(prs.slides) - 1})")
        sys.exit(1)

    slide = prs.slides[slide_index]
    if not slide.has_notes_slide:
        return
    print(slide.notes_slide.notes_text_frame.text)


def run_get(args) -> None:
    """Entry point from CLI dispatcher."""
    input_path = Path(args.input)

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    # Parse shape_path like "slide-0/shape-2" or "slide-0/notes"
    invalid_path_msg = (
        f"Error: Invalid path '{args.shape_path}'. Expected format: slide-N/shape-N or slide-N/notes"
    )
    parts = args.shape_path.split("/")
    if len(parts) != 2 or not parts[0].startswith("slide-"):
        print(invalid_path_msg)
        sys.exit(1)

    slide_key, target = parts

    if target == "notes":
        _run_get_notes(input_path, slide_key)
        return

    if not target.startswith("shape-"):
        print(invalid_path_msg)
        sys.exit(1)

    shape_key = target

    extracted = extract_text(input_path)

    if slide_key not in extracted:
        print(f"Error: {slide_key} not found (available: {', '.join(sorted(extracted.keys()))})")
        sys.exit(1)

    if shape_key not in extracted[slide_key]:
        print(f"Error: {shape_key} not found on {slide_key} (available: {', '.join(sorted(extracted[slide_key].keys()))})")
        sys.exit(1)

    shape_data = extracted[slide_key][shape_key]
    for para in shape_data.paragraphs:
        print(para.text)
