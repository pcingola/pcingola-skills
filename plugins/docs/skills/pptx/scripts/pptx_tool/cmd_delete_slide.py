"""Remove slides from a presentation by index."""

import sys
import warnings
from pathlib import Path

from pptx import Presentation

from .cmd_select_slides import remove_slide


def run_delete_slide(args) -> None:
    """Entry point from CLI dispatcher."""
    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    # Parse indices
    try:
        indices = sorted(set(int(x.strip()) for x in args.indices.split(",")), reverse=True)
    except ValueError:
        print("Error: Invalid indices format. Use comma-separated integers (e.g., 0,5)")
        sys.exit(1)

    prs = Presentation(str(input_path))
    total = len(prs.slides)

    for idx in indices:
        if not 0 <= idx < total:
            print(f"Error: Slide index {idx} out of range (0-{total - 1})")
            sys.exit(1)

    # Remove in reverse order so indices stay valid
    for idx in indices:
        remove_slide(prs, idx)
        print(f"  Removed slide {idx}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='Duplicate name:')
        prs.save(str(output_path))

    print(f"Saved to: {output_path} ({len(prs.slides)} slides remaining)")
