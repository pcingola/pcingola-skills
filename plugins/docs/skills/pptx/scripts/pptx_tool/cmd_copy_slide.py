"""Copy slides from a source presentation into a target presentation."""

import sys
import warnings
from pathlib import Path

from pptx import Presentation

from .cmd_select_slides import clone_slide_to_presentation


def run_copy_slide(args) -> None:
    """Entry point from CLI dispatcher."""
    source_path = Path(args.source)
    target_path = Path(args.target)
    output_path = Path(args.output)

    if not source_path.exists():
        print(f"Error: Source file not found: {source_path}")
        sys.exit(1)
    if not target_path.exists():
        print(f"Error: Target file not found: {target_path}")
        sys.exit(1)

    # Parse source indices
    try:
        source_indices = [int(x.strip()) for x in args.source_indices.split(",")]
    except ValueError:
        print("Error: Invalid source indices. Use comma-separated integers (e.g., 0,2,3)")
        sys.exit(1)

    source_prs = Presentation(str(source_path))
    target_prs = Presentation(str(target_path))

    total_source = len(source_prs.slides)
    for idx in source_indices:
        if not 0 <= idx < total_source:
            print(f"Error: Source slide index {idx} out of range (0-{total_source - 1})")
            sys.exit(1)

    # Determine insertion position. Each slide lands one further along than the
    # last so a multi-slide copy keeps its source order at the insertion point.
    append_at = len(target_prs.slides)
    position = args.position

    for i, src_idx in enumerate(source_indices):
        try:
            clone_slide_to_presentation(
                source_prs, target_prs, src_idx,
                position=None if position is None else position + i,
            )
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        landed = (append_at + i) if position is None else (position + i)
        print(f"  Copied source slide {src_idx} to position {landed}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='Duplicate name:')
        target_prs.save(str(output_path))

    print(f"Saved to: {output_path} ({len(target_prs.slides)} slides)")
