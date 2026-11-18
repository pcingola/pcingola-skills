"""Remove slides from a presentation by index."""

import warnings
from dataclasses import dataclass
from pathlib import Path

from pptx import Presentation

from .cmd_select_slides import remove_slide
from .common import parse_indices, require_file
from .exceptions import PptxError

INVALID_INDICES_MESSAGE = "Invalid indices format. Use comma-separated integers (e.g., 0,5)"


@dataclass(frozen=True)
class DeletedSlides:
    """What `delete_slides` did: removed indices in removal order (descending), output path, slides left."""
    removed: list[int]
    output_path: Path
    remaining: int


def delete_slides(input_path: Path, output_path: Path, indices: list[int]) -> DeletedSlides:
    """Remove the slides at `indices` (0-based, duplicates ignored) and save the deck to output_path."""
    require_file(input_path, f"Input file not found: {input_path}")
    removed = sorted(set(indices), reverse=True)

    prs = Presentation(str(input_path))
    total = len(prs.slides)
    for idx in removed:
        if not 0 <= idx < total:
            raise PptxError(f"Slide index {idx} out of range (0-{total - 1})")

    # Remove in reverse order so indices stay valid
    for idx in removed:
        remove_slide(prs, idx)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='Duplicate name:')
        prs.save(str(output_path))
    return DeletedSlides(removed, output_path, len(prs.slides))


def run_delete_slide(args) -> None:
    """Entry point from CLI dispatcher."""
    input_path = Path(args.input)
    # The input check comes before the index parse, as the CLI reports the first of the two errors.
    require_file(input_path, f"Input file not found: {input_path}")
    result = delete_slides(input_path, Path(args.output), parse_indices(args.indices, INVALID_INDICES_MESSAGE))
    for idx in result.removed:
        print(f"  Removed slide {idx}")
    print(f"Saved to: {result.output_path} ({result.remaining} slides remaining)")
