"""Helpers for working with OBJECT placeholders in python-pptx slides."""

from pptx.shapes.base import BaseShape
from pptx.slide import Slide
from pptx.util import Length

OBJECT_PLACEHOLDER_TYPE = 7


def find_object_placeholders(slide: Slide) -> list[BaseShape]:
    """Return all OBJECT placeholders on the slide, in order."""
    result: list[BaseShape] = []
    for shape in slide.shapes:
        try:
            if shape.is_placeholder and shape.placeholder_format.type == OBJECT_PLACEHOLDER_TYPE:
                result.append(shape)
        except (AttributeError, ValueError):
            continue
    return result


def get_placeholder_geometry(placeholder_shape: BaseShape) -> tuple[Length, Length, Length, Length]:
    """Return (left, top, width, height) for a placeholder shape."""
    return (
        placeholder_shape.left,
        placeholder_shape.top,
        placeholder_shape.width,
        placeholder_shape.height,
    )


def remove_shape(slide: Slide, shape: BaseShape) -> None:
    """Remove a shape element from the slide's shape tree."""
    sp = shape._element
    sp.getparent().remove(sp)
