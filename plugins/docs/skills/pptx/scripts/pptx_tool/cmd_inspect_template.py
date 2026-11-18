"""Unified template inspection with inventory-compatible structure.

Creates a single JSON file with all template information using the same
slide-N/shape-N structure as inventory and replacement JSON files.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches

from .cmd_extract_shapes import (
    ShapeData,
    collect_shapes_with_absolute_positions,
    sort_shapes_by_position,
)
from .exceptions import PptxError


def get_placeholder_metadata(shape) -> dict:
    """Extract placeholder metadata (type and idx) from a shape."""
    metadata = {}

    if hasattr(shape, "is_placeholder") and shape.is_placeholder:
        if hasattr(shape, "placeholder_format") and shape.placeholder_format:
            # Get placeholder type
            if shape.placeholder_format.type:
                placeholder_type = str(shape.placeholder_format.type)
                metadata["placeholder_type"] = placeholder_type.split(".")[-1].split(" ")[0]

            # Get placeholder idx
            if hasattr(shape.placeholder_format, "idx"):
                metadata["placeholder_idx"] = shape.placeholder_format.idx

    return metadata


def create_picture_shape_dict(shape) -> dict:
    """Create a dictionary representation of a PICTURE placeholder."""
    shape_dict = {
        "left": round(shape.left / Inches(1), 2),
        "top": round(shape.top / Inches(1), 2),
        "width": round(shape.width / Inches(1), 2),
        "height": round(shape.height / Inches(1), 2),
    }

    # Add placeholder metadata
    placeholder_meta = get_placeholder_metadata(shape)
    if placeholder_meta:
        shape_dict.update(placeholder_meta)

    # Add a clear indicator that this is for images, not text
    shape_dict["content_type"] = "image"
    shape_dict["note"] = "This placeholder is for images. Use pptx.sh add-images to insert images here."

    return shape_dict


def create_unified_template_summary(template_path: Path) -> dict:
    """Create a unified template summary with inventory-compatible structure."""
    prs = Presentation(str(template_path))

    # Get slide dimensions
    template_summary = {
        "slide_dimensions": {
            "width_inches": round(prs.slide_width / Inches(1), 2),
            "height_inches": round(prs.slide_height / Inches(1), 2)
        },
        "slides": {}
    }

    # Process each slide in the template
    for slide_idx, slide in enumerate(prs.slides):
        slide_key = f"slide-{slide_idx}"

        # Get layout name
        layout_name = slide.slide_layout.name if hasattr(slide, "slide_layout") else "Unknown"

        # Collect all shapes with text using inventory logic
        text_shapes = []
        for shape in slide.shapes:
            text_shapes.extend(collect_shapes_with_absolute_positions(shape))

        # Also collect PICTURE placeholders (they don't have text but need to be documented)
        picture_shapes = []
        for shape in slide.shapes:
            if hasattr(shape, "is_placeholder") and shape.is_placeholder:
                if hasattr(shape, "placeholder_format") and shape.placeholder_format:
                    placeholder_type = str(shape.placeholder_format.type)
                    if "PICTURE" in placeholder_type:
                        picture_shapes.append(shape)

        if not text_shapes and not picture_shapes:
            continue

        # Convert text shapes to ShapeData objects
        text_shape_data_list = [
            ShapeData(
                swp.shape,
                swp.absolute_left,
                swp.absolute_top,
                slide,
            )
            for swp in text_shapes
        ]

        # Sort text shapes by visual position
        sorted_text_shapes = sort_shapes_by_position(text_shape_data_list)

        # Create a combined list with position info for sorting
        all_shapes_for_sorting = []

        # Add text shapes
        for shape_data in sorted_text_shapes:
            shape_info = shape_data.to_dict()
            placeholder_meta = get_placeholder_metadata(shape_data.shape)
            if placeholder_meta:
                ordered_info = {
                    "left": shape_info["left"],
                    "top": shape_info["top"],
                    "width": shape_info["width"],
                    "height": shape_info["height"],
                }
                ordered_info.update(placeholder_meta)
                for key, value in shape_info.items():
                    if key not in ordered_info:
                        ordered_info[key] = value
                shape_info = ordered_info

            all_shapes_for_sorting.append((
                shape_info["top"],
                shape_info["left"],
                shape_info,
                False
            ))

        # Add picture shapes
        for picture_shape in picture_shapes:
            picture_dict = create_picture_shape_dict(picture_shape)
            all_shapes_for_sorting.append((
                picture_dict["top"],
                picture_dict["left"],
                picture_dict,
                True
            ))

        # Sort all shapes by position (top, then left)
        all_shapes_for_sorting.sort(key=lambda x: (x[0], x[1]))

        # Build shapes dictionary for this slide
        shapes_dict = {}
        for idx, (_, _, shape_info, is_picture) in enumerate(all_shapes_for_sorting):
            shape_key = f"shape-{idx}"
            shapes_dict[shape_key] = shape_info

        # Add slide to template summary
        template_summary["slides"][slide_key] = {
            "layout_name": layout_name,
            "shapes": shapes_dict
        }

    return template_summary


@dataclass(frozen=True)
class TemplateInspection:
    """Counts of what `inspect_template` wrote to its JSON file."""
    slide_count: int
    shape_count: int
    picture_count: int

    @property
    def text_count(self) -> int:
        return self.shape_count - self.picture_count


def inspect_template(template_path: Path, output_path: Path) -> TemplateInspection:
    """Write the unified template summary of `template_path` as JSON to `output_path`."""
    if not template_path.exists():
        raise PptxError(f"Template file not found at {template_path}")

    template_summary = create_unified_template_summary(template_path)
    slides = template_summary["slides"].values()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(template_summary, f, indent=2, ensure_ascii=False)

    return TemplateInspection(
        slide_count=len(slides),
        shape_count=sum(len(slide_data["shapes"]) for slide_data in slides),
        picture_count=sum(
            1 for slide_data in slides
            for shape_data in slide_data["shapes"].values()
            if shape_data.get("content_type") == "image"
        ),
    )


def run_inspect_template(args) -> None:
    """Entry point from CLI dispatcher."""
    template_path = Path(args.template)
    output_path = Path(args.output)
    result = inspect_template(template_path, output_path)
    print(f"Inspecting template: {template_path}")
    print(f"Found {result.slide_count} slides with {result.shape_count} shapes "
          f"({result.text_count} text, {result.picture_count} image)")
    print(f"Output saved to: {output_path}")
