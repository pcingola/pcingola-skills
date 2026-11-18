"""Read a single shape's text content by slide-N/shape-N path, or a slide's
speaker notes by slide-N/notes."""

from pathlib import Path

from pptx import Presentation

from .cmd_extract_shapes import extract_text
from .exceptions import PptxError


def _get_notes(input_path: Path, slide_key: str) -> list[str]:
    """Speaker notes of the slide named by `slide_key` (slide-N): one string, or none."""
    prs = Presentation(str(input_path))
    try:
        slide_index = int(slide_key.split("-")[1])
    except (IndexError, ValueError):
        raise PptxError(f"Invalid slide key '{slide_key}'") from None

    if slide_index < 0 or slide_index >= len(prs.slides):
        raise PptxError(f"Slide index {slide_index} out of range (0-{len(prs.slides) - 1})")

    slide = prs.slides[slide_index]
    if not slide.has_notes_slide:
        return []
    return [slide.notes_slide.notes_text_frame.text]


def get_text(input_path: Path, shape_path: str) -> list[str]:
    """Text at `shape_path` (slide-N/shape-N or slide-N/notes), one string per line printed.

    A shape gives one string per paragraph; notes give one string (which may hold
    newlines), or an empty list when the slide has no notes.
    """
    if not input_path.exists():
        raise PptxError(f"Input file not found: {input_path}")

    invalid_path_msg = (
        f"Invalid path '{shape_path}'. Expected format: slide-N/shape-N or slide-N/notes"
    )
    parts = shape_path.split("/")
    if len(parts) != 2 or not parts[0].startswith("slide-"):
        raise PptxError(invalid_path_msg)

    slide_key, target = parts

    if target == "notes":
        return _get_notes(input_path, slide_key)

    if not target.startswith("shape-"):
        raise PptxError(invalid_path_msg)

    shape_key = target
    extracted = extract_text(input_path)

    if slide_key not in extracted:
        raise PptxError(f"{slide_key} not found (available: {', '.join(sorted(extracted.keys()))})")

    if shape_key not in extracted[slide_key]:
        raise PptxError(
            f"{shape_key} not found on {slide_key} (available: {', '.join(sorted(extracted[slide_key].keys()))})"
        )

    return [para.text for para in extracted[slide_key][shape_key].paragraphs]


def run_get(args) -> None:
    """Entry point from CLI dispatcher."""
    for line in get_text(Path(args.input), args.shape_path):
        print(line)
