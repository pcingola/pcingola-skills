"""Copy slides from a source presentation into a target presentation."""

import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

from pptx import Presentation

from .cmd_select_slides import clone_slide_to_presentation
from .common import parse_indices, require_file
from .exceptions import PptxError, SlidePositionError

INVALID_INDICES_MESSAGE = "Invalid source indices. Use comma-separated integers (e.g., 0,2,3)"


@dataclass(frozen=True)
class CopiedSlide:
    """One copied slide: its index in the source deck and where it landed in the output."""
    source_index: int
    position: int


@dataclass(frozen=True)
class CopiedSlides:
    """What `copy_slides` did: the copies in order, the output path and its slide count."""
    slides: list[CopiedSlide]
    output_path: Path
    total: int


def _require_decks(source_path: Path, target_path: Path) -> None:
    require_file(source_path, f"Source file not found: {source_path}")
    require_file(target_path, f"Target file not found: {target_path}")


def copy_slides(source_path: Path, target_path: Path, output_path: Path, source_indices: list[int],
                position: int | None = None) -> CopiedSlides:
    """Copy the source slides at `source_indices` into the target deck, at `position` (default: the
    end), and save it to output_path. An insert position out of range raises SlidePositionError."""
    _require_decks(source_path, target_path)
    source_prs = Presentation(str(source_path))
    target_prs = Presentation(str(target_path))

    total_source = len(source_prs.slides)
    for idx in source_indices:
        if not 0 <= idx < total_source:
            raise PptxError(f"Source slide index {idx} out of range (0-{total_source - 1})")

    # Each slide lands one further along than the last so a multi-slide copy
    # keeps its source order at the insertion point.
    append_at = len(target_prs.slides)
    copied = []
    for i, src_idx in enumerate(source_indices):
        try:
            clone_slide_to_presentation(
                source_prs, target_prs, src_idx,
                position=None if position is None else position + i,
            )
        except ValueError as e:
            raise SlidePositionError(str(e)) from None
        copied.append(CopiedSlide(src_idx, (append_at + i) if position is None else (position + i)))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='Duplicate name:')
        target_prs.save(str(output_path))
    return CopiedSlides(copied, output_path, len(target_prs.slides))


def print_copied_slides(result: CopiedSlides) -> None:
    """Print the copy-slide report: one line per copied slide, then the saved path and slide count."""
    for slide in result.slides:
        print(f"  Copied source slide {slide.source_index} to position {slide.position}")
    print(f"Saved to: {result.output_path} ({result.total} slides)")


def print_copy_slide_failure(exc: Exception) -> bool:
    """Print a SlidePositionError as `Error: <message>` on stderr and return True; return False for
    any other exception (a PptxError prints in the standard format, on stdout)."""
    if not isinstance(exc, SlidePositionError):
        return False
    print(f"Error: {exc}", file=sys.stderr)
    return True


def run_copy_slide(args) -> int:
    """Entry point from CLI dispatcher."""
    source_path = Path(args.source)
    target_path = Path(args.target)
    # The file checks come before the index parse, as the CLI reports the first of the errors.
    _require_decks(source_path, target_path)
    indices = parse_indices(args.source_indices, INVALID_INDICES_MESSAGE)
    try:
        result = copy_slides(source_path, target_path, Path(args.output), indices, args.position)
    except Exception as e:
        if print_copy_slide_failure(e):
            return 1
        raise
    print_copied_slides(result)
    return 0
