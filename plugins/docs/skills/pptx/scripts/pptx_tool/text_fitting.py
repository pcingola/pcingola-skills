"""Text fitting utilities for preventing overflow in PowerPoint shapes.

This module provides functionality to calculate text dimensions and find
optimal font sizes that fit within shape boundaries.
"""

from dataclasses import dataclass

from .measure import DPI, _MEASURE_DRAW, load_font, measure_text_lines, text_width  # noqa: F401

# Constants
EMU_PER_INCH = 914400
POINTS_PER_INCH = 72
MIN_FONT_SIZE = 12.0
FONT_SIZE_STEP = 2.0
DEFAULT_FONT_SIZE = 18.0
DEFAULT_TITLE_FONT_SIZE = 32.0
SAFETY_MARGIN = 0.95  # Use 95% of available height for safety


@dataclass
class FittingResult:
    """Result of text fitting calculation for a shape."""
    fits: bool
    reduction: float  # Amount to reduce each font size by (0 = no change)
    shape_key: str
    slide_key: str
    overflow_inches: float | None = None

    @property
    def adjusted(self) -> bool:
        return self.reduction > 0

    def __str__(self) -> str:
        if self.adjusted:
            return f"{self.slide_key}/{self.shape_key}: reduced by {self.reduction}pt"
        return f"{self.slide_key}/{self.shape_key}: no change needed"


class TextFitter:
    """Calculates text dimensions and finds optimal font sizes for shapes."""

    def __init__(self, min_font_size: float = MIN_FONT_SIZE, font_size_step: float = FONT_SIZE_STEP):
        self.min_font_size = min_font_size
        self.font_size_step = font_size_step

    def calculate_usable_dimensions(self, shape_data: dict) -> tuple[float, float]:
        """Calculate usable width and height inside a shape after margins.

        Args:
            shape_data: Shape data dictionary with width, height in inches

        Returns:
            Tuple of (usable_width, usable_height) in inches
        """
        width = shape_data.get("width", 0)
        height = shape_data.get("height", 0)

        # Default margins (approximate PowerPoint defaults)
        margin_left = 0.1
        margin_right = 0.1
        margin_top = 0.05
        margin_bottom = 0.05

        usable_width = max(0, width - margin_left - margin_right)
        usable_height = max(0, height - margin_top - margin_bottom)

        # Apply safety margin
        usable_height *= SAFETY_MARGIN

        return usable_width, usable_height

    def calculate_text_height_with_sizes(self, paragraphs: list[dict], font_sizes: list[float], usable_width: float) -> float:
        """Calculate total height needed for paragraphs with individual font sizes.

        Args:
            paragraphs: List of paragraph dictionaries with text and formatting
            font_sizes: List of font sizes (one per paragraph)
            usable_width: Available width in inches

        Returns:
            Total height in inches
        """
        total_height = 0.0
        line_height_multiplier = 1.4  # Typical line height multiplier

        for para, font_size in zip(paragraphs, font_sizes):
            text = para.get("text", "")
            if not text:
                # Empty paragraph still takes some space
                total_height += (font_size * line_height_multiplier) / POINTS_PER_INCH
                continue

            # Get font name for measurement
            font_name = para.get("font_name", "Arial")
            is_bullet = para.get("bullet", False)

            # Adjust width for bullets
            effective_width = usable_width
            if is_bullet:
                bullet_indent = 0.4  # Approximate bullet indentation
                effective_width = max(0.5, usable_width - bullet_indent)

            # Calculate number of lines needed
            num_lines = measure_text_lines(text, font_name, font_size, effective_width)

            # Calculate paragraph height
            line_spacing = para.get("line_spacing", font_size * line_height_multiplier)
            para_height = num_lines * (line_spacing / POINTS_PER_INCH)

            # Add spacing before/after
            space_before = para.get("space_before", 0)
            space_after = para.get("space_after", 3.0 if is_bullet else 0)
            para_height += (space_before + space_after) / POINTS_PER_INCH

            total_height += para_height

        return total_height

    def find_fitting_reduction(self, shape_data: dict, paragraphs: list[dict], slide_key: str, shape_key: str) -> FittingResult:
        """Find the minimum reduction needed to fit text within shape boundaries.

        Each paragraph keeps its own font size (or default), and we reduce all
        font sizes by the same amount until text fits.

        Args:
            shape_data: Shape data dictionary with dimensions and placeholder_type
            paragraphs: List of paragraph dictionaries (may contain font_size)
            slide_key: Slide identifier for reporting
            shape_key: Shape identifier for reporting

        Returns:
            FittingResult with fitting status and reduction amount
        """
        usable_width, usable_height = self.calculate_usable_dimensions(shape_data)

        if usable_width <= 0 or usable_height <= 0:
            return FittingResult(
                fits=False,
                reduction=0,
                slide_key=slide_key,
                shape_key=shape_key,
                overflow_inches=None
            )

        # Get base font sizes for each paragraph
        placeholder_type = shape_data.get("placeholder_type")
        default_size = shape_data.get("inherited_font_size") or get_default_font_size_for_placeholder(placeholder_type)

        base_font_sizes = []
        for para in paragraphs:
            if "font_size" in para:
                base_font_sizes.append(para["font_size"])
            else:
                base_font_sizes.append(default_size)

        # Try with no reduction first
        reduction = 0.0

        while True:
            # Calculate current font sizes with reduction
            current_sizes = [max(self.min_font_size, size - reduction) for size in base_font_sizes]

            # Check if any font would go below minimum
            min_current = min(current_sizes)

            # Calculate height with current sizes
            text_height = self.calculate_text_height_with_sizes(paragraphs, current_sizes, usable_width)

            if text_height <= usable_height:
                return FittingResult(
                    fits=True,
                    reduction=reduction,
                    slide_key=slide_key,
                    shape_key=shape_key
                )

            # If we've hit minimum on all fonts and still overflow, fail
            if min_current <= self.min_font_size:
                # Calculate final overflow
                final_sizes = [max(self.min_font_size, size - reduction) for size in base_font_sizes]
                text_height = self.calculate_text_height_with_sizes(paragraphs, final_sizes, usable_width)
                overflow = text_height - usable_height

                return FittingResult(
                    fits=False,
                    reduction=reduction,
                    slide_key=slide_key,
                    shape_key=shape_key,
                    overflow_inches=round(overflow, 2)
                )

            reduction += self.font_size_step


TITLE_PLACEHOLDER_TYPES = {"TITLE", "CENTER_TITLE"}
BODY_PLACEHOLDER_TYPES = {"BODY", "SUBTITLE", "OBJECT", "VERTICAL_BODY", "VERTICAL_OBJECT"}


def get_default_font_size_for_placeholder(placeholder_type: str | None) -> float:
    """Get default font size based on placeholder type."""
    if placeholder_type in TITLE_PLACEHOLDER_TYPES:
        return DEFAULT_TITLE_FONT_SIZE
    return DEFAULT_FONT_SIZE


def _lvl1_size(element, path: str) -> float | None:
    """The level-1 default run size in points under `element` at `path` (an lstStyle or a txStyles
    child), or None when it sets none."""
    if element is None:
        return None
    found = element.xpath(f"{path}/a:lvl1pPr/a:defRPr/@sz")
    return int(found[0]) / 100 if found else None


def _shape_lst_style_size(shape) -> float | None:
    return _lvl1_size(shape._element, "./p:txBody/a:lstStyle")


def inherited_font_size(shape, placeholder_type: str | None) -> float | None:
    """The level-1 font size a run without `sz` inherits in `shape`, in points, or None when the
    chain sets none.

    The chain is the shape's own lstStyle, then for a placeholder the layout and master placeholder
    lstStyles and the master titleStyle (TITLE, CENTER_TITLE), bodyStyle (BODY, SUBTITLE, OBJECT)
    or otherStyle; for any other shape the presentation defaultTextStyle."""
    try:
        size = _shape_lst_style_size(shape)
        if size is not None:
            return size
        if getattr(shape, "is_placeholder", False):
            base = getattr(shape, "_base_placeholder", None)
            while base is not None:
                size = _shape_lst_style_size(base)
                if size is not None:
                    return size
                base = getattr(base, "_base_placeholder", None)
            master = shape.part.slide.slide_layout.slide_master._element
            if placeholder_type in TITLE_PLACEHOLDER_TYPES:
                style = "titleStyle"
            elif placeholder_type in BODY_PLACEHOLDER_TYPES:
                style = "bodyStyle"
            else:
                style = "otherStyle"
            return _lvl1_size(master, f"./p:txStyles/p:{style}")
        presentation = shape.part.package.presentation_part._element
        return _lvl1_size(presentation, "./p:defaultTextStyle")
    except (AttributeError, KeyError, ValueError):
        return None
