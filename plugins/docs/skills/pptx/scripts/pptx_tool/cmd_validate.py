"""`validate` subcommand — walk a deck and report per-slide issues.

Reports:
- text overflow / overlap / formatting warnings (delegates to extractor issue detection)
- empty text placeholders
- unfilled PICTURE / OBJECT placeholders (the visual slot is still an empty placeholder)
"""

import json
import sys
from pathlib import Path

from pptx import Presentation

from .cmd_extract_shapes import extract_text, filter_issues_only, shapes_data_to_json

_VISUAL_PLACEHOLDER_TYPES = {"PICTURE", "OBJECT", "CHART", "MEDIA", "SLIDE_IMAGE"}


def _placeholder_has_content(shape) -> bool:
    """Return True when a visual placeholder already carries user content.

    `add-images`/`add-chart`/`add-table` replace the placeholder XML with a real
    shape, so anything still `is_placeholder=True` on a visual slot hasn't had
    those actions applied. But an OBJECT placeholder can also be legitimately
    filled with text (column layouts, heading lists, value points), so we treat
    non-empty text as a filled state too.
    """
    if not shape.has_text_frame:
        return False
    return bool(shape.text_frame.text.strip())


def _collect_unfilled_visuals(input_path: Path) -> list[dict]:
    """Find PICTURE/OBJECT/etc. placeholders that are genuinely empty."""
    prs = Presentation(str(input_path))
    unfilled: list[dict] = []
    for slide_idx, slide in enumerate(prs.slides):
        for shape in slide.shapes:
            if not shape.is_placeholder:
                continue
            try:
                ph_type = shape.placeholder_format.type
            except (AttributeError, ValueError):
                continue
            if ph_type is None:
                continue
            type_name = getattr(ph_type, "name", str(ph_type))
            if type_name not in _VISUAL_PLACEHOLDER_TYPES:
                continue
            if _placeholder_has_content(shape):
                continue
            unfilled.append({"slide": slide_idx, "placeholder_type": type_name, "shape_name": shape.name})
    return unfilled


def _collect_empty_text(input_path: Path) -> list[dict]:
    """Find TITLE/BODY placeholders with no text content."""
    prs = Presentation(str(input_path))
    empties: list[dict] = []
    for slide_idx, slide in enumerate(prs.slides):
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            if not shape.is_placeholder:
                continue
            try:
                type_name = getattr(shape.placeholder_format.type, "name", "")
            except (AttributeError, ValueError):
                continue
            if type_name in _VISUAL_PLACEHOLDER_TYPES:
                continue
            if shape.text_frame.text.strip():
                continue
            empties.append({"slide": slide_idx, "placeholder_type": type_name, "shape_name": shape.name})
    return empties


def run_validate(args) -> None:
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file '{input_path}' not found", file=sys.stderr)
        sys.exit(1)
    if input_path.suffix.lower() not in (".pptx", ".ppt"):
        print("Error: Input file must be a .pptx or .ppt file", file=sys.stderr)
        sys.exit(1)

    extracted = extract_text(input_path)
    issues = filter_issues_only(extracted)

    report = {
        "slide_count": len(Presentation(str(input_path)).slides),
        "text_issues": shapes_data_to_json(issues) if issues else {},
        "empty_text_placeholders": _collect_empty_text(input_path),
        "unfilled_visual_placeholders": _collect_unfilled_visuals(input_path),
    }
    payload = json.dumps(report, indent=2, ensure_ascii=False)

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
        print(f"Validation report saved to: {out}")
    else:
        print(payload)

    has_problems = bool(
        report["text_issues"] or report["empty_text_placeholders"] or report["unfilled_visual_placeholders"]
    )
    if has_problems:
        sys.exit(2)
