"""`validate` subcommand — walk a deck and report per-slide issues.

Reports:
- text overflow / overlap / formatting warnings (delegates to extractor issue detection)
- empty text placeholders
- unfilled PICTURE / OBJECT placeholders (the visual slot is still an empty placeholder)
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from pptx import Presentation

from .cmd_extract_shapes import extract_text, filter_issues_only, shapes_data_to_json
from .exceptions import PptxError

# Exit code of `validate` when the report lists a problem.
PROBLEMS_EXIT_CODE = 2

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


@dataclass(frozen=True)
class PlaceholderIssue:
    """A placeholder that `validate` reports: slide index, placeholder type, shape name."""
    slide: int
    placeholder_type: str
    shape_name: str


@dataclass(frozen=True)
class ValidationReport:
    """What `validate` found in a deck. `text_issues` is the extract-shapes JSON of the shapes with issues."""
    slide_count: int
    text_issues: dict
    empty_text_placeholders: list[PlaceholderIssue]
    unfilled_visual_placeholders: list[PlaceholderIssue]

    @property
    def has_problems(self) -> bool:
        return bool(self.text_issues or self.empty_text_placeholders or self.unfilled_visual_placeholders)

    def to_json(self) -> str:
        """The report as the indented JSON the CLI prints or writes."""
        return json.dumps(asdict(self), indent=2, ensure_ascii=False)


def _collect_unfilled_visuals(input_path: Path) -> list[PlaceholderIssue]:
    """Find PICTURE/OBJECT/etc. placeholders that are genuinely empty."""
    prs = Presentation(str(input_path))
    unfilled: list[PlaceholderIssue] = []
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
            unfilled.append(PlaceholderIssue(slide_idx, type_name, shape.name))
    return unfilled


def _collect_empty_text(input_path: Path) -> list[PlaceholderIssue]:
    """Find TITLE/BODY placeholders with no text content."""
    prs = Presentation(str(input_path))
    empties: list[PlaceholderIssue] = []
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
            empties.append(PlaceholderIssue(slide_idx, type_name, shape.name))
    return empties


def validate_deck(input_path: Path) -> ValidationReport:
    """Report text issues, empty text placeholders and unfilled visual placeholders of a deck."""
    if not input_path.exists():
        raise PptxError(f"Input file '{input_path}' not found")
    if input_path.suffix.lower() not in (".pptx", ".ppt"):
        raise PptxError("Input file must be a .pptx or .ppt file")

    issues = filter_issues_only(extract_text(input_path))
    return ValidationReport(
        slide_count=len(Presentation(str(input_path)).slides),
        text_issues=shapes_data_to_json(issues) if issues else {},
        empty_text_placeholders=_collect_empty_text(input_path),
        unfilled_visual_placeholders=_collect_unfilled_visuals(input_path),
    )


def run_validate(args) -> int:
    report = validate_deck(Path(args.input))
    payload = report.to_json()

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
        print(f"Validation report saved to: {out}")
    else:
        print(payload)

    return PROBLEMS_EXIT_CODE if report.has_problems else 0
