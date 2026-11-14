"""Insert images into PowerPoint presentation placeholders."""

import sys
from enum import Enum
from pathlib import Path

from pptx import Presentation


class PlaceholderType(Enum):
    """PowerPoint placeholder types."""
    OBJECT = 7
    CHART = 8
    DIAGRAM = 11
    MEDIA = 12
    SLIDE_IMAGE = 13
    PICTURE = 18


def insert_image_in_placeholder(slide, image_path: Path, placeholder_type: int, placeholder_index: int = 0) -> bool:
    """Insert an image into a placeholder on a slide."""
    placeholders = []
    for shape in slide.shapes:
        try:
            if shape.is_placeholder and shape.placeholder_format.type == placeholder_type:
                placeholders.append(shape)
        except (AttributeError, ValueError):
            continue

    if not placeholders:
        return False

    if placeholder_index >= len(placeholders):
        raise IndexError(f"Placeholder index {placeholder_index} out of range. Found {len(placeholders)} placeholders of type {placeholder_type}.")

    placeholder = placeholders[placeholder_index]
    left = placeholder.left
    top = placeholder.top
    width = placeholder.width
    height = placeholder.height

    sp = placeholder._element
    sp.getparent().remove(sp)

    slide.shapes.add_picture(str(image_path), left, top, width, height)
    return True


def insert_images_in_placeholders(slide, image_paths: list[Path], placeholder_type: int) -> int:
    """Insert multiple images into placeholders on a slide, left to right.

    Index 0 every time, not `i`: each insert *removes* the placeholder it fills,
    so the list shrinks under us. Walking it with an incrementing index skipped
    every second slot and ran off the end after the first image — the second
    image was silently dropped and the command still exited 0.
    """
    count = 0
    for image_path in image_paths:
        try:
            if insert_image_in_placeholder(slide, image_path, placeholder_type, 0):
                count += 1
            else:
                break
        except (IndexError, FileNotFoundError) as e:
            print(f"Warning: Could not insert image {image_path}: {e}", file=sys.stderr)
            break
    return count


def run_add_images(args) -> None:
    """Entry point from CLI dispatcher."""
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    image_paths_str = [p.strip() for p in args.images.split(',')]
    image_paths = [Path(p) for p in image_paths_str]

    for img_path in image_paths:
        if not img_path.exists():
            print(f"Error: Image file not found: {img_path}", file=sys.stderr)
            sys.exit(1)

    try:
        placeholder_type_value = getattr(PlaceholderType, args.placeholder_type.upper()).value
    except AttributeError:
        print(f"Error: Invalid placeholder type '{args.placeholder_type}'; valid types: PICTURE, OBJECT, MEDIA",
              file=sys.stderr)
        sys.exit(1)

    try:
        prs = Presentation(str(input_path))

        if not 0 <= args.slide < len(prs.slides):
            print(f"Error: Slide index {args.slide} out of range (0-{len(prs.slides)-1})", file=sys.stderr)
            sys.exit(1)

        slide = prs.slides[args.slide]

        if len(image_paths) == 1:
            index = args.index if args.index is not None else 0
            success = insert_image_in_placeholder(slide, image_paths[0], placeholder_type_value, index)
            if not success:
                print(f"Error: No {args.placeholder_type} placeholder found on slide {args.slide}", file=sys.stderr)
                sys.exit(1)
            print(f"Inserted {image_paths[0].name} into slide {args.slide}")
        else:
            count = insert_images_in_placeholders(slide, image_paths, placeholder_type_value)
            print(f"Inserted {count} of {len(image_paths)} images into slide {args.slide}")
            if count < len(image_paths):
                print(f"Warning: Only {count} {args.placeholder_type} placeholders available", file=sys.stderr)

        prs.save(str(args.output))
        print(f"Saved presentation to: {args.output}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
