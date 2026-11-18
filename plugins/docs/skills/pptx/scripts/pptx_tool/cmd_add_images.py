"""Insert images into PowerPoint presentation placeholders."""

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from pptx import Presentation

from .common import require_file
from .exceptions import PptxError


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


def insert_images_in_placeholders(slide, image_paths: list[Path], placeholder_type: int,
                                  warnings: list[str]) -> int:
    """Insert multiple images into placeholders on a slide, left to right.

    Index 0 every time, not `i`: each insert *removes* the placeholder it fills,
    so the list shrinks under us. Walking it with an incrementing index skipped
    every second slot and ran off the end after the first image — the second
    image was silently dropped and the command still exited 0.

    An image that cannot be inserted stops the run and appends a line to `warnings`.
    """
    count = 0
    for image_path in image_paths:
        try:
            if insert_image_in_placeholder(slide, image_path, placeholder_type, 0):
                count += 1
            else:
                break
        except (IndexError, FileNotFoundError) as e:
            warnings.append(f"Warning: Could not insert image {image_path}: {e}")
            break
    return count


@dataclass
class ImagesAdded:
    """What `add_images` did: images inserted out of those given, and warning lines for stderr."""
    inserted: int
    requested: int
    warnings: list[str] = field(default_factory=list)


def add_images(input_path: Path, output_path: Path, slide_index: int, image_paths: list[Path],
               placeholder_type: str = "PICTURE", index: int | None = None) -> ImagesAdded:
    """Insert images into the `placeholder_type` placeholders (a PlaceholderType name, any case) of
    one slide and save the deck to output_path.

    One image goes into the placeholder at `index` (default 0); several fill the placeholders left
    to right, and fewer placeholders than images gives a warning.
    """
    require_file(input_path, f"Input file not found: {input_path}")
    for img_path in image_paths:
        require_file(img_path, f"Image file not found: {img_path}")
    try:
        placeholder_type_value = getattr(PlaceholderType, placeholder_type.upper()).value
    except AttributeError:
        raise PptxError(f"Invalid placeholder type '{placeholder_type}'; valid types: PICTURE, OBJECT, MEDIA") from None

    prs = Presentation(str(input_path))
    if not 0 <= slide_index < len(prs.slides):
        raise PptxError(f"Slide index {slide_index} out of range (0-{len(prs.slides)-1})")
    slide = prs.slides[slide_index]

    result = ImagesAdded(0, len(image_paths))
    if len(image_paths) == 1:
        try:
            success = insert_image_in_placeholder(slide, image_paths[0], placeholder_type_value,
                                                  index if index is not None else 0)
        except IndexError as e:
            raise PptxError(str(e)) from None
        if not success:
            raise PptxError(f"No {placeholder_type} placeholder found on slide {slide_index}")
        result.inserted = 1
    else:
        result.inserted = insert_images_in_placeholders(slide, image_paths, placeholder_type_value, result.warnings)
        if result.inserted < len(image_paths):
            result.warnings.append(f"Warning: Only {result.inserted} {placeholder_type} placeholders available")

    prs.save(str(output_path))
    return result


def run_add_images(args) -> int:
    """Entry point from CLI dispatcher. Any error prints as `Error: <message>` on stderr."""
    image_paths = [Path(p.strip()) for p in args.images.split(',')]
    try:
        result = add_images(Path(args.input), Path(args.output), args.slide, image_paths,
                            args.placeholder_type, args.index)
    except PptxError:
        raise
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    if len(image_paths) == 1:
        print(f"Inserted {image_paths[0].name} into slide {args.slide}")
    else:
        print(f"Inserted {result.inserted} of {len(image_paths)} images into slide {args.slide}")
    for line in result.warnings:
        print(line, file=sys.stderr)
    print(f"Saved presentation to: {args.output}")
    return 0
