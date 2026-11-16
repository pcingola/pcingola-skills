"""Extract text content from PowerPoint presentations to structured JSON.

This module provides functionality to extract all text content from PowerPoint
presentations, including complete formatting information, positioning data, and
detection of layout issues like text overflow and shape overlaps.

Output:
    JSON file with slide-N/shape-N structure containing text and formatting data
"""

import argparse
import json

import sys
from dataclasses import dataclass, field
from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Inches

from .text_metrics import frame_overflow, get_placeholder_type

# Type alias for extracted shapes data structure
ExtractedShapesData = dict[str, dict[str, "ShapeData"]]

# Constants
EMU_PER_INCH = 914400
ROW_TOLERANCE_INCHES = 0.5
OVERLAP_TOLERANCE_INCHES = 0.05
SLIDE_OVERFLOW_TOLERANCE_INCHES = 0.01


@dataclass
class ParagraphData:
    """Holds formatting properties for a single paragraph."""

    text: str
    bullet: bool | None = None
    level: int | None = None
    alignment: str | None = None
    space_before: float | None = None
    space_after: float | None = None
    font_name: str | None = None
    font_size: float | None = None
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    strikethrough: bool | None = None
    superscript: bool | None = None
    subscript: bool | None = None
    all_caps: bool | None = None
    small_caps: bool | None = None
    char_spacing: float | None = None  # points
    theme_color: str | None = None
    color: str | None = None  # explicit RGB hex e.g. "#RRGGBB"
    line_spacing: float | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary, excluding None values."""
        result = {"text": self.text}

        for key, value in [
            ("bullet", self.bullet),
            ("level", self.level),
            ("alignment", self.alignment),
            ("space_before", self.space_before),
            ("space_after", self.space_after),
            ("font_name", self.font_name),
            ("font_size", self.font_size),
            ("bold", self.bold),
            ("italic", self.italic),
            ("underline", self.underline),
            ("strikethrough", self.strikethrough),
            ("superscript", self.superscript),
            ("subscript", self.subscript),
            ("all_caps", self.all_caps),
            ("small_caps", self.small_caps),
            ("char_spacing", self.char_spacing),
            ("theme_color", self.theme_color),
            ("color", self.color),
            ("line_spacing", self.line_spacing),
        ]:
            if value is not None:
                result[key] = value

        return result


@dataclass
class ShapeWithPosition:
    """Temporary structure holding shape and its absolute position."""

    shape: any
    absolute_left: int  # in EMUs
    absolute_top: int   # in EMUs


@dataclass
class ShapeData:
    """Holds position, dimensions, and text content for a shape."""

    shape: any
    left_emu: int
    top_emu: int
    slide: any
    shape_id: str | None = None
    warnings: list[str] = field(default_factory=list)
    overlapping_shapes: dict[str, float] = field(default_factory=dict)
    frame_overflow_bottom: float | None = None
    slide_overflow_right: float | None = None
    slide_overflow_bottom: float | None = None
    _paragraphs: list[ParagraphData] | None = None
    # Table data (populated when shape is a table)
    table_data: dict | None = None
    # Shape-level properties
    fill_type: str | None = None
    fill_color: str | None = None
    fill_theme_color: str | None = None
    border_visible: bool | None = None
    border_color: str | None = None
    border_theme_color: str | None = None
    border_weight_pt: float | None = None
    border_dash: str | None = None
    shadow: bool | None = None
    word_wrap: bool | None = None
    autofit: str | None = None
    text_margin_top: float | None = None
    text_margin_left: float | None = None
    text_margin_bottom: float | None = None
    text_margin_right: float | None = None
    vertical_alignment: str | None = None
    rotation: float | None = None
    z_order: int | None = None

    @property
    def left(self) -> float:
        """Position from left edge in inches."""
        return round(self.left_emu / EMU_PER_INCH, 2)

    @property
    def top(self) -> float:
        """Position from top edge in inches."""
        return round(self.top_emu / EMU_PER_INCH, 2)

    @property
    def width(self) -> float:
        """Width in inches."""
        return round(self.shape.width / EMU_PER_INCH, 2)

    @property
    def height(self) -> float:
        """Height in inches."""
        return round(self.shape.height / EMU_PER_INCH, 2)

    @property
    def paragraphs(self) -> list[ParagraphData]:
        """Extract paragraph data on demand."""
        if self._paragraphs is None:
            self._paragraphs = extract_paragraph_data(self.shape)
        return self._paragraphs

    @property
    def has_issues(self) -> bool:
        """Check if shape has any detected issues."""
        return bool(
            self.frame_overflow_bottom is not None
            or self.slide_overflow_right is not None
            or self.slide_overflow_bottom is not None
            or self.overlapping_shapes
            or self.warnings
        )

    def __post_init__(self):
        """Calculate overflow and warnings during initialization."""
        self._detect_overflow()
        if is_valid_table_shape(self.shape):
            try:
                self.table_data = extract_table_data(self.shape)
            except Exception:
                pass
        else:
            self._detect_warnings()
        self._extract_shape_properties()

    def _extract_shape_properties(self):
        """Extract fill, border, text frame, rotation, and z-order properties."""
        shape = self.shape

        # Fill
        try:
            fill = shape.fill
            if fill.type is not None:
                self.fill_type = str(fill.type).split(".")[-1].split(" ")[0]
                if self.fill_type == "SOLID":
                    try:
                        self.fill_color = f"#{fill.fore_color.rgb}"
                    except Exception:
                        try:
                            tc = fill.fore_color.theme_color
                            self.fill_theme_color = str(tc).split(".")[-1].split(" ")[0]
                        except Exception:
                            pass
            else:
                self.fill_type = "BACKGROUND"
        except Exception:
            pass

        # Border / line
        try:
            line = shape.line
            if line.fill.type is None:
                self.border_visible = False
            else:
                self.border_visible = True
                try:
                    self.border_color = f"#{line.color.rgb}"
                except Exception:
                    try:
                        tc = line.color.theme_color
                        self.border_theme_color = str(tc).split(".")[-1].split(" ")[0]
                    except Exception:
                        pass
                try:
                    if line.width:
                        self.border_weight_pt = round(line.width.pt, 2)
                except Exception:
                    pass
                try:
                    self.border_dash = str(line.dash_style).split(".")[-1].split(" ")[0]
                except Exception:
                    pass
        except Exception:
            pass

        # Shadow
        try:
            ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
            spPr = shape._element.spPr
            if spPr is not None:
                effectLst = spPr.find(f"{{{ns}}}effectLst")
                self.shadow = effectLst is not None and len(effectLst) > 0
        except Exception:
            pass

        # Text frame properties
        if hasattr(shape, "text_frame") and shape.has_text_frame:
            try:
                tf = shape.text_frame
                self.word_wrap = tf.word_wrap
            except Exception:
                pass
            try:
                from pptx.enum.text import MSO_AUTO_SIZE
                autosize = shape.text_frame.auto_size
                if autosize is None or autosize == MSO_AUTO_SIZE.NONE:
                    self.autofit = "NONE"
                elif autosize == MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE:
                    self.autofit = "TEXT_TO_FIT_SHAPE"
                elif autosize == MSO_AUTO_SIZE.SHAPE_TO_FIT_TEXT:
                    self.autofit = "SHAPE_TO_FIT_TEXT"
            except Exception:
                pass
            try:
                tf = shape.text_frame
                if tf.margin_top is not None:
                    self.text_margin_top = round(tf.margin_top / EMU_PER_INCH, 4)
                if tf.margin_left is not None:
                    self.text_margin_left = round(tf.margin_left / EMU_PER_INCH, 4)
                if tf.margin_bottom is not None:
                    self.text_margin_bottom = round(tf.margin_bottom / EMU_PER_INCH, 4)
                if tf.margin_right is not None:
                    self.text_margin_right = round(tf.margin_right / EMU_PER_INCH, 4)
            except Exception:
                pass
            try:
                va = shape.text_frame.vertical_anchor
                if va is not None:
                    self.vertical_alignment = str(va).split(".")[-1].split(" ")[0]
            except Exception:
                pass

        # Rotation
        try:
            if shape.rotation is not None:
                r = round(shape.rotation, 2)
                if r != 0:
                    self.rotation = r
        except Exception:
            pass

    def _detect_overflow(self):
        """Detect text overflow within frame and slide boundaries."""
        # Frame overflow (text shapes only)
        if not is_valid_table_shape(self.shape):
            overflow = calculate_frame_overflow(self.shape)
            if overflow is not None:
                self.frame_overflow_bottom = round(overflow, 2)

        # Slide overflow
        if self.slide:
            # Get slide dimensions from the presentation
            try:
                prs = self.slide.part.package.presentation_part.presentation
                slide_width = prs.slide_width
                slide_height = prs.slide_height
            except Exception:
                # Fallback to standard dimensions if unable to get from presentation
                slide_width = Inches(10)
                slide_height = Inches(7.5)

            right_edge = self.left_emu + self.shape.width
            bottom_edge = self.top_emu + self.shape.height

            overflow_right = (right_edge - slide_width) / EMU_PER_INCH
            overflow_bottom = (bottom_edge - slide_height) / EMU_PER_INCH

            if overflow_right > SLIDE_OVERFLOW_TOLERANCE_INCHES:
                self.slide_overflow_right = round(overflow_right, 2)
            if overflow_bottom > SLIDE_OVERFLOW_TOLERANCE_INCHES:
                self.slide_overflow_bottom = round(overflow_bottom, 2)

    def _detect_warnings(self):
        """Detect formatting warnings."""
        for para in self.paragraphs:
            if para.text.startswith(("\u2022 ", "\u25cf ", "\u25cb ")):
                self.warnings.append("manual_bullet_symbol: use proper bullet formatting")
                break

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }

        # Add placeholder type if applicable
        placeholder_type = get_placeholder_type(self.shape)
        if placeholder_type:
            result["placeholder_type"] = placeholder_type

        # Add paragraphs (or table data for table shapes)
        if self.table_data is not None:
            result["table"] = self.table_data
        else:
            result["paragraphs"] = [p.to_dict() for p in self.paragraphs]

        # Add overflow information
        overflow = {}
        if self.frame_overflow_bottom is not None:
            overflow["frame"] = {"overflow_bottom": self.frame_overflow_bottom}

        slide_overflow = {}
        if self.slide_overflow_right is not None:
            slide_overflow["overflow_right"] = self.slide_overflow_right
        if self.slide_overflow_bottom is not None:
            slide_overflow["overflow_bottom"] = self.slide_overflow_bottom
        if slide_overflow:
            overflow["slide"] = slide_overflow

        if overflow:
            result["overflow"] = overflow

        # Add overlap information
        if self.overlapping_shapes:
            result["overlap"] = {"overlapping_shapes": self.overlapping_shapes}

        # Add shape-level properties
        for key, value in [
            ("fill_type", self.fill_type),
            ("fill_color", self.fill_color),
            ("fill_theme_color", self.fill_theme_color),
            ("border_visible", self.border_visible),
            ("border_color", self.border_color),
            ("border_theme_color", self.border_theme_color),
            ("border_weight_pt", self.border_weight_pt),
            ("border_dash", self.border_dash),
            ("shadow", self.shadow),
            ("word_wrap", self.word_wrap),
            ("autofit", self.autofit),
            ("text_margin_top", self.text_margin_top),
            ("text_margin_left", self.text_margin_left),
            ("text_margin_bottom", self.text_margin_bottom),
            ("text_margin_right", self.text_margin_right),
            ("vertical_alignment", self.vertical_alignment),
            ("rotation", self.rotation),
            ("z_order", self.z_order),
        ]:
            if value is not None:
                result[key] = value

        # Add warnings
        if self.warnings:
            result["warnings"] = self.warnings

        return result


# Placeholder types listed even when empty: a slide added from a layout has
# only empty placeholders, and add-text needs their keys to fill them.
FILLABLE_EMPTY_PLACEHOLDERS = {"TITLE", "CENTER_TITLE", "SUBTITLE", "BODY", "OBJECT"}


def is_valid_text_shape(shape) -> bool:
    """Check if shape should be included in inventory."""
    if not hasattr(shape, "text_frame") or not shape.text_frame:
        return False

    placeholder_type = get_placeholder_type(shape)
    if not shape.text_frame.text.strip():
        return placeholder_type in FILLABLE_EMPTY_PLACEHOLDERS

    # Skip slide number placeholders
    if placeholder_type == "SLIDE_NUMBER":
        return False

    # Skip numeric-only footers
    if placeholder_type == "FOOTER":
        if shape.text_frame.text.strip().isdigit():
            return False

    return True


def is_valid_table_shape(shape) -> bool:
    """Check if shape is a non-empty table."""
    try:
        return shape.has_table and len(shape.table.rows) > 0
    except Exception:
        return False


def extract_cell_borders(cell) -> dict | None:
    """Extract border style for each edge of a table cell (top/right/bottom/left).

    Returns a dict with keys 'top', 'right', 'bottom', 'left', each containing
    {'visible': bool, 'style': str, 'width_pt': float, 'color': str}.
    Only non-default edges are included; returns None if no border data found.
    """
    ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
    try:
        tc = cell._tc
    except Exception:
        return None

    tcPr = tc.find(f"{{{ns}}}tcPr")
    if tcPr is None:
        return None

    edge_tags = {
        "top": f"{{{ns}}}lnT",
        "right": f"{{{ns}}}lnR",
        "bottom": f"{{{ns}}}lnB",
        "left": f"{{{ns}}}lnL",
    }

    borders: dict = {}
    for edge, tag in edge_tags.items():
        ln = tcPr.find(tag)
        if ln is None:
            continue
        edge_info: dict = {}

        # No-line element means explicitly invisible
        noFill = ln.find(f"{{{ns}}}noFill")
        if noFill is not None:
            edge_info["visible"] = False
            borders[edge] = edge_info
            continue

        # Width
        w_attr = ln.get("w")
        if w_attr is not None:
            try:
                edge_info["width_pt"] = round(int(w_attr) / 12700, 2)  # EMU → pt
            except Exception:
                pass

        # Line style (cmpd attribute: sng=single, dbl=double, thickThin, thinThick, tri)
        cmpd = ln.get("cmpd", "sng")
        style_map = {
            "sng": "single", "dbl": "double",
            "thickThin": "thick-thin", "thinThick": "thin-thick", "tri": "triple",
        }
        edge_info["style"] = style_map.get(cmpd, cmpd)

        # Dash style
        prstDash = ln.find(f"{{{ns}}}prstDash")
        if prstDash is not None:
            val = prstDash.get("val", "")
            if val and val != "solid":
                edge_info["dash"] = val

        # Color
        solidFill = ln.find(f"{{{ns}}}solidFill")
        if solidFill is not None:
            srgbClr = solidFill.find(f"{{{ns}}}srgbClr")
            if srgbClr is not None:
                edge_info["color"] = f"#{srgbClr.get('val', '').upper()}"
            schemeClr = solidFill.find(f"{{{ns}}}schemeClr")
            if schemeClr is not None:
                edge_info["theme_color"] = schemeClr.get("val", "")

        edge_info["visible"] = True
        borders[edge] = edge_info

    return borders if borders else None


def extract_table_data(shape) -> dict:
    """Extract table structure, cell text, and header/body formatting."""
    table = shape.table
    num_rows = len(table.rows)
    num_cols = len(table.columns) if table.columns else (len(table.rows[0].cells) if num_rows else 0)

    rows_data = []
    for row_idx, row in enumerate(table.rows):
        row_height = round(row.height / EMU_PER_INCH, 3) if row.height else None
        cells_data = []
        for col_idx, cell in enumerate(row.cells):
            # Detect merged cells (non-origin cells of a merge share the same tc element)
            is_spanned = getattr(cell, "is_spanned", False)
            cell_dict: dict = {}
            if is_spanned:
                cell_dict["merged"] = True
            else:
                paragraphs = []
                if cell.text_frame:
                    for para in cell.text_frame.paragraphs:
                        text = para.text.strip()
                        if not text:
                            continue
                        para_data = ParagraphData(text=text)
                        # Bullet
                        if has_bullet(para):
                            para_data.bullet = True
                            para_data.level = para.level if hasattr(para, "level") else 0
                        # Alignment
                        if hasattr(para, "alignment") and para.alignment is not None:
                            alignment_name = str(para.alignment).split(".")[-1].split(" ")[0]
                            if alignment_name != "LEFT":
                                para_data.alignment = alignment_name
                        # Font from first run
                        if para.runs:
                            run = para.runs[0]
                            font = run.font
                            if font.name:
                                para_data.font_name = font.name
                            if font.size:
                                para_data.font_size = round(font.size.pt, 2)
                            if font.bold:
                                para_data.bold = True
                            if font.italic:
                                para_data.italic = True
                            if font.underline:
                                para_data.underline = True
                            try:
                                rgb = font.color.rgb
                                para_data.color = f"#{rgb}"
                            except Exception:
                                try:
                                    if font.color.theme_color is not None:
                                        tc = str(font.color.theme_color)
                                        para_data.theme_color = tc.split(".")[-1].split(" ")[0]
                                except Exception:
                                    pass
                        paragraphs.append(para_data.to_dict())

                cell_dict["text"] = cell.text.strip().replace("\v", "\n")
                if paragraphs:
                    cell_dict["paragraphs"] = paragraphs

                # Cell fill
                try:
                    fill = cell.fill
                    if fill.type is not None:
                        fill_type = str(fill.type).split(".")[-1].split(" ")[0]
                        cell_dict["fill_type"] = fill_type
                        if fill_type == "SOLID":
                            try:
                                cell_dict["fill_color"] = f"#{fill.fore_color.rgb}"
                            except Exception:
                                try:
                                    tc = fill.fore_color.theme_color
                                    cell_dict["fill_theme_color"] = str(tc).split(".")[-1].split(" ")[0]
                                except Exception:
                                    pass
                except Exception:
                    pass

                # Cell borders
                cell_borders = extract_cell_borders(cell)
                if cell_borders:
                    cell_dict["borders"] = cell_borders

            cells_data.append(cell_dict)

        row_dict: dict = {"cells": cells_data}
        if row_height is not None:
            row_dict["height"] = row_height
        rows_data.append(row_dict)

    col_widths = []
    try:
        for col in table.columns:
            col_widths.append(round(col.width / EMU_PER_INCH, 3))
    except Exception:
        pass

    result: dict = {
        "num_rows": num_rows,
        "num_cols": num_cols,
        "rows": rows_data,
    }
    if col_widths:
        result["col_widths"] = col_widths
    return result


def collect_shapes_with_absolute_positions(shape, parent_left=0, parent_top=0) -> list[ShapeWithPosition]:
    """Recursively collect shapes with absolute positions, handling nested groups."""
    results = []

    absolute_left = parent_left + shape.left
    absolute_top = parent_top + shape.top

    # Check if this is a group shape
    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        # Recursively process children
        for child_shape in shape.shapes:
            results.extend(
                collect_shapes_with_absolute_positions(
                    child_shape, absolute_left, absolute_top
                )
            )
    elif is_valid_table_shape(shape):
        results.append(ShapeWithPosition(shape, absolute_left, absolute_top))
    elif is_valid_text_shape(shape):
        results.append(ShapeWithPosition(shape, absolute_left, absolute_top))

    return results


def sort_shapes_by_position(shapes: list[ShapeData]) -> list[ShapeData]:
    """Sort shapes by visual position (top-to-bottom, left-to-right)."""
    def sort_key(shape_data: ShapeData):
        # Group shapes into rows (within ROW_TOLERANCE_INCHES vertically)
        row = int(shape_data.top / ROW_TOLERANCE_INCHES)
        return (row, shape_data.top, shape_data.left)

    return sorted(shapes, key=sort_key)


def extract_paragraph_data(shape) -> list[ParagraphData]:
    """Extract paragraph-level text and formatting from a shape."""
    paragraphs = []

    if not hasattr(shape, "text_frame") or not shape.text_frame:
        return paragraphs

    for para in shape.text_frame.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        para_data = ParagraphData(text=text)

        # Bullet detection
        if has_bullet(para):
            para_data.bullet = True
            para_data.level = para.level if hasattr(para, "level") else 0

        # Alignment (only if not LEFT)
        if hasattr(para, "alignment") and para.alignment is not None:
            alignment_name = str(para.alignment).split(".")[-1].split(" ")[0]
            if alignment_name != "LEFT":
                para_data.alignment = alignment_name

        # Spacing
        if hasattr(para, "space_before") and para.space_before is not None:
            para_data.space_before = round(para.space_before.pt, 2)
        if hasattr(para, "space_after") and para.space_after is not None:
            para_data.space_after = round(para.space_after.pt, 2)
        if hasattr(para, "line_spacing") and para.line_spacing is not None:
            ls = para.line_spacing
            para_data.line_spacing = round(ls.pt, 2) if hasattr(ls, "pt") else round(ls, 4)

        # Font properties from first run
        if para.runs:
            run = para.runs[0]
            if hasattr(run, "font"):
                font = run.font

                if font.name:
                    para_data.font_name = font.name
                if font.size:
                    para_data.font_size = round(font.size.pt, 2)
                if font.bold:
                    para_data.bold = True
                if font.italic:
                    para_data.italic = True
                if font.underline:
                    para_data.underline = True

                # Color — explicit RGB first, then theme
                try:
                    rgb = font.color.rgb
                    para_data.color = f"#{rgb}"
                except Exception:
                    try:
                        if hasattr(font.color, "theme_color") and font.color.theme_color is not None:
                            theme_color = str(font.color.theme_color)
                            para_data.theme_color = theme_color.split(".")[-1].split(" ")[0]
                    except Exception:
                        pass

                # Strikethrough
                try:
                    rPr = font._element.get_or_add_rPr()
                    strike = rPr.get("strike")
                    if strike and strike != "noStrike":
                        para_data.strikethrough = True
                except Exception:
                    pass

                # Superscript / subscript (baseline attribute)
                try:
                    rPr = font._element.get_or_add_rPr()
                    baseline = rPr.get("baseline")
                    if baseline is not None:
                        bval = int(baseline)
                        if bval > 0:
                            para_data.superscript = True
                        elif bval < 0:
                            para_data.subscript = True
                except Exception:
                    pass

                # All caps
                try:
                    if font.all_caps:
                        para_data.all_caps = True
                except Exception:
                    pass

                # Small caps
                try:
                    rPr = font._element.get_or_add_rPr()
                    if rPr.get("smCaps") in ("1", "true"):
                        para_data.small_caps = True
                except Exception:
                    pass

                # Character spacing (spc attribute, in hundredths of a point)
                try:
                    rPr = font._element.get_or_add_rPr()
                    spc = rPr.get("spc")
                    if spc is not None:
                        para_data.char_spacing = round(int(spc) / 100, 2)
                except Exception:
                    pass

        paragraphs.append(para_data)

    return paragraphs


def has_bullet(paragraph) -> bool:
    """Check if paragraph has bullet formatting."""
    try:
        pPr = paragraph._element.pPr
        if pPr is None:
            return False

        # Check for bullet elements in DrawingML namespace
        for child in pPr:
            tag_name = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag_name in ["buChar", "buAutoNum"]:
                return True
    except Exception:
        pass
    return False


def calculate_frame_overflow(shape) -> float | None:
    """Text overflow within shape boundaries, in inches, or None; see `text_metrics.frame_overflow`."""
    try:
        return frame_overflow(shape)
    except Exception:
        return None


def detect_overlaps(shapes: list[ShapeData]) -> None:
    """Detect and record overlapping shapes."""
    for i, shape1 in enumerate(shapes):
        for shape2 in shapes[i + 1:]:
            overlap_area = calculate_overlap_area(shape1, shape2)
            if overlap_area > 0:
                shape1.overlapping_shapes[shape2.shape_id] = round(overlap_area, 2)
                shape2.overlapping_shapes[shape1.shape_id] = round(overlap_area, 2)


def calculate_overlap_area(shape1: ShapeData, shape2: ShapeData) -> float:
    """Calculate overlap area between two shapes."""
    # Calculate edges
    left1, right1 = shape1.left, shape1.left + shape1.width
    top1, bottom1 = shape1.top, shape1.top + shape1.height
    left2, right2 = shape2.left, shape2.left + shape2.width
    top2, bottom2 = shape2.top, shape2.top + shape2.height

    # Calculate overlap dimensions
    overlap_width = min(right1, right2) - max(left1, left2)
    overlap_height = min(bottom1, bottom2) - max(top1, top2)

    # Check tolerance
    if overlap_width <= OVERLAP_TOLERANCE_INCHES or overlap_height <= OVERLAP_TOLERANCE_INCHES:
        return 0.0

    return overlap_width * overlap_height


def extract_text(pptx_path: Path, prs: Presentation = None) -> ExtractedShapesData:
    """Extract text content from PowerPoint presentation.

    Args:
        pptx_path: Path to PowerPoint file
        prs: Optional pre-loaded Presentation object

    Returns:
        Dictionary mapping slide-N to shape-N to ShapeData
    """
    if prs is None:
        prs = Presentation(str(pptx_path))

    extracted_shapes_data = {}

    for slide_idx, slide in enumerate(prs.slides):
        slide_key = f"slide-{slide_idx}"

        # Build z-order lookup: shape element → z-order index (position in spTree)
        z_order_map: dict[int, int] = {}
        for z_idx, shape in enumerate(slide.shapes):
            z_order_map[id(shape._element)] = z_idx

        # Collect all text shapes with absolute positions
        shape_positions = []
        for shape in slide.shapes:
            shape_positions.extend(collect_shapes_with_absolute_positions(shape))

        if not shape_positions:
            continue

        # Convert to ShapeData objects
        shape_data_list = [
            ShapeData(swp.shape, swp.absolute_left, swp.absolute_top, slide)
            for swp in shape_positions
        ]

        # Assign z_order
        for sd in shape_data_list:
            sd.z_order = z_order_map.get(id(sd.shape._element))

        # Sort by visual position
        sorted_shapes = sort_shapes_by_position(shape_data_list)

        # Assign shape IDs
        for shape_idx, shape_data in enumerate(sorted_shapes):
            shape_data.shape_id = f"shape-{shape_idx}"

        # Detect overlaps
        detect_overlaps(sorted_shapes)

        # Build shapes dictionary
        shapes_dict = {
            shape_data.shape_id: shape_data
            for shape_data in sorted_shapes
        }

        extracted_shapes_data[slide_key] = shapes_dict

    return extracted_shapes_data


def filter_issues_only(extracted_shapes_data: ExtractedShapesData) -> ExtractedShapesData:
    """Filter extracted shapes data to include only shapes with issues."""
    filtered = {}

    for slide_key, shapes_dict in extracted_shapes_data.items():
        filtered_shapes = {
            shape_key: shape_data
            for shape_key, shape_data in shapes_dict.items()
            if shape_data.has_issues
        }

        if filtered_shapes:
            filtered[slide_key] = filtered_shapes

    return filtered


def extract_slide_notes(slide) -> str:
    """Return a slide's speaker-notes text, or '' when there are none."""
    try:
        if not slide.has_notes_slide:
            return ""
        text_frame = slide.notes_slide.notes_text_frame
        return text_frame.text.strip() if text_frame is not None else ""
    except Exception:
        return ""


def extract_all_notes(prs: Presentation) -> dict[str, str]:
    """Map slide-N to its speaker notes, skipping slides that have none.

    Notes live on a separate notes slide, not in the shape tree, so the shape
    inventory cannot see them — and a slide carrying only notes has no entry at
    all. Collected separately and merged into the output for that reason.
    """
    return {
        f"slide-{idx}": notes
        for idx, slide in enumerate(prs.slides)
        if (notes := extract_slide_notes(slide))
    }


def _slide_sort_key(slide_key: str) -> int:
    try:
        return int(slide_key.split("-")[1])
    except (IndexError, ValueError):
        return -1


def shapes_data_to_json(extracted_shapes_data: ExtractedShapesData) -> dict:
    """Convert extracted shapes data to JSON-serializable dictionary."""
    result = {}

    for slide_key, shapes_dict in extracted_shapes_data.items():
        result[slide_key] = {
            shape_key: shape_data.to_dict()
            for shape_key, shape_data in shapes_dict.items()
        }

    return result


def run_extract_shapes(args) -> None:
    """Entry point from CLI dispatcher."""
    input_path = Path(args.input)
    output_arg = args.output

    # Validate input
    if not input_path.exists():
        print(f"Error: Input file '{input_path}' not found")
        sys.exit(1)

    if input_path.suffix.lower() != ".pptx":
        print(f"Error: Input file must be a .pptx file")
        sys.exit(1)

    # Directory mode: output ends with "/" or is an existing directory
    dir_mode = output_arg.endswith("/") or Path(output_arg).is_dir()
    output_path = Path(output_arg)

    try:
        print(f"Processing: {input_path}")

        # Extract shapes data
        prs = Presentation(str(input_path))
        extracted_shapes_data = extract_text(input_path, prs)
        notes_by_slide = extract_all_notes(prs)

        # Filter to a single slide if requested
        if args.slide is not None:
            slide_key = f"slide-{args.slide}"
            if not 0 <= args.slide < len(prs.slides):
                print(f"Error: slide index {args.slide} not found (valid range: 0–{len(prs.slides)-1})")
                sys.exit(1)
            extracted_shapes_data = {
                k: v for k, v in extracted_shapes_data.items() if k == slide_key
            }
            notes_by_slide = {k: v for k, v in notes_by_slide.items() if k == slide_key}

        # Filter if requested
        if args.issues_only:
            extracted_shapes_data = filter_issues_only(extracted_shapes_data)
            if not extracted_shapes_data:
                print("No issues discovered")
                sys.exit(0)
            # Notes are content, not issues — they would only pad the report.
            notes_by_slide = {}

        # Convert to JSON
        json_data = shapes_data_to_json(extracted_shapes_data)
        for slide_key, notes in notes_by_slide.items():
            json_data.setdefault(slide_key, {})["notes"] = notes
        json_data = {k: json_data[k] for k in sorted(json_data, key=_slide_sort_key)}

        total_slides = len(json_data)
        total_shapes = sum(
            len([k for k in shapes if k.startswith("shape-")]) for shapes in json_data.values()
        )

        if dir_mode:
            # Write one slide_N.shapes.json per slide (1-based filenames)
            output_path.mkdir(parents=True, exist_ok=True)
            written = []
            for slide_key, shapes in json_data.items():
                # slide_key is "slide-0", "slide-1", ...
                slide_idx = int(slide_key.split("-")[1])
                file_path = output_path / f"slide_{slide_idx + 1}.shapes.json"
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump({slide_key: shapes}, f, indent=2, ensure_ascii=False)
                written.append(str(file_path))
            print(f"Extracted {total_slides} slides with {total_shapes} text elements")
            for p in written:
                print(f"  {p}")
        else:
            # Single combined file (original behaviour)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            print(f"Extracted {total_slides} slides with {total_shapes} text elements")
            print(f"Output saved to: {output_path}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
