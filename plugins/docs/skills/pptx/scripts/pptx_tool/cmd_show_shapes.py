"""Show a compact human-readable summary of an extracted-shapes JSON file.

Reads the JSON output of ``extract-shapes`` and prints shape type,
position, dimensions, and a text preview for each shape on each slide.
"""

import json
from pathlib import Path

from .exceptions import PptxError

TEXT_PREVIEW_LEN = 60


def _first_text(shape: dict) -> str:
    """Return a short text preview from the first paragraph."""
    paragraphs = shape.get("paragraphs", [])
    if not paragraphs:
        return ""
    text = paragraphs[0].get("text", "")
    if len(text) > TEXT_PREVIEW_LEN:
        text = text[:TEXT_PREVIEW_LEN] + "..."
    return text


def _issue_flags(shape: dict) -> list[str]:
    """Return short flag strings for any detected issues."""
    flags = []
    overflow = shape.get("overflow", {})
    if "frame" in overflow:
        flags.append("OVERFLOW")
    if "slide" in overflow:
        flags.append("OFF-SLIDE")
    if shape.get("overlap"):
        flags.append("OVERLAP")
    if shape.get("warnings"):
        flags.append("WARN")
    return flags


def format_shapes(data: dict) -> str:
    """Format extracted-shapes JSON data as a compact human-readable summary."""
    if not data:
        return "No shapes found in JSON."

    lines = []
    for slide_key in sorted(data, key=lambda k: int(k.split("-")[1])):
        slide = data[slide_key]
        # A slide entry holds shape-N keys plus, when the slide has speaker
        # notes, a "notes" string. Only the former are shapes.
        shape_keys = sorted(
            (k for k in slide if k.startswith("shape-")),
            key=lambda k: int(k.split("-")[1]),
        )
        lines.append(f"{slide_key}: ({len(shape_keys)} shapes)")

        for shape_key in shape_keys:
            shape = slide[shape_key]
            ptype = shape.get("placeholder_type", "TEXT")
            left = shape.get("left", 0)
            top = shape.get("top", 0)
            width = shape.get("width", 0)
            height = shape.get("height", 0)

            preview = _first_text(shape)
            flags = _issue_flags(shape)
            flags_str = f"  [{', '.join(flags)}]" if flags else ""

            pos = f"{left}\",{top}\" {width}\"x{height}\""
            text_str = f'  "{preview}"' if preview else ""
            lines.append(f"  {shape_key}: {ptype} @ {pos}{flags_str}{text_str}")

        notes = slide.get("notes")
        if notes:
            preview = notes if len(notes) <= TEXT_PREVIEW_LEN else notes[:TEXT_PREVIEW_LEN] + "..."
            lines.append(f'  notes: "{preview}"')

        lines.append("")

    return "\n".join(lines)


def show_shapes(input_path: Path) -> str:
    """Compact summary of the extracted-shapes JSON file at `input_path`."""
    if not input_path.exists():
        raise PptxError(f"File not found: {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return format_shapes(data)


def run_show_shapes(args) -> None:
    """Entry point from CLI dispatcher."""
    print(show_shapes(Path(args.input)))
