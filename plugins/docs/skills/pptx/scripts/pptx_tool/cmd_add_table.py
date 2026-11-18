"""Add tables to PowerPoint presentations.

The table data JSON structure uses slide-N keys with table definitions.
Tables can be placed into OBJECT placeholders or at explicit positions.
Supports header row styling, cell-level formatting, column widths, and cell merging.
"""

from dataclasses import dataclass
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from .common import load_data_json, require_file
from .exceptions import ValidationError
from .pptx import print_unexpected_failure
from .text_formatters import ParagraphProcessor

# Shared run/paragraph styler — the same path add-text and add-shapes use, so a
# table cell's text is formatted by one implementation, not a table-only copy.
_PARAGRAPH_PROCESSOR = ParagraphProcessor()


ALIGNMENT_MAP = {
    "LEFT": PP_ALIGN.LEFT,
    "CENTER": PP_ALIGN.CENTER,
    "RIGHT": PP_ALIGN.RIGHT,
    "JUSTIFY": PP_ALIGN.JUSTIFY,
}


@dataclass(frozen=True)
class TablesAdded:
    """What `add_tables` did: the number of tables added, warning lines in order, and the output path."""
    tables_added: int
    warnings: list[str]
    output_path: Path


class PresentationTableAdder:
    """Adds tables to presentations from JSON definitions."""

    def __init__(self):
        self.warnings: list[str] = []

    def add_tables(self, input_path: Path, table_data: dict, output_path: Path) -> TablesAdded:
        """Add the tables of `table_data` (slide-N keys) to the deck and save it to output_path.

        Invalid data raises ValidationError with one detail line per problem.
        """
        require_file(input_path, f"Input file '{input_path}' not found")
        prs = Presentation(str(input_path))
        self._validate_table_data(prs, table_data)

        tables_added = 0
        for slide_key, tables in table_data.items():
            slide_index = int(slide_key.split("-")[1])
            slide = prs.slides[slide_index]

            table_list = tables if isinstance(tables, list) else [tables]
            for table_def in table_list:
                self._add_table(slide, table_def)
                tables_added += 1

        prs.save(str(output_path))
        return TablesAdded(tables_added, list(self.warnings), output_path)

    def _validate_table_data(self, prs, table_data: dict) -> None:
        """Validate table data against the presentation."""
        errors = []
        slide_count = len(prs.slides)

        for slide_key, tables in table_data.items():
            if not slide_key.startswith("slide-"):
                errors.append(f"Invalid key '{slide_key}': must be 'slide-N'")
                continue

            try:
                slide_index = int(slide_key.split("-")[1])
            except (IndexError, ValueError):
                errors.append(f"Invalid slide key '{slide_key}'")
                continue

            if slide_index < 0 or slide_index >= slide_count:
                errors.append(f"Slide index {slide_index} out of range (0-{slide_count - 1})")
                continue

            table_list = tables if isinstance(tables, list) else [tables]
            for i, table_def in enumerate(table_list):
                prefix = f"{slide_key} table {i}"
                if "rows" not in table_def:
                    errors.append(f"{prefix}: missing 'rows'")
                elif not isinstance(table_def["rows"], list) or len(table_def["rows"]) == 0:
                    errors.append(f"{prefix}: 'rows' must be a non-empty list")

        if errors:
            raise ValidationError(
                f"Found {len(errors)} validation error(s)",
                ["ERROR: Invalid table data:", *(f"  - {error}" for error in errors)],
            )

    def _add_table(self, slide, table_def: dict) -> None:
        """Add a single table to a slide."""
        rows_data = table_def["rows"]
        num_rows = len(rows_data)
        num_cols = max(len(row.get("cells", [])) for row in rows_data)

        # Determine position and size
        position = self._resolve_position(slide, table_def)
        left, top, width, height = position

        # Create the table
        table_shape = slide.shapes.add_table(num_rows, num_cols, left, top, width, height)
        table = table_shape.table
        self._replace_empty_placeholder(slide, table_def)

        # Apply column widths if specified
        col_widths = table_def.get("column_widths")
        if col_widths:
            for i, w in enumerate(col_widths):
                if i < num_cols:
                    table.columns[i].width = Inches(w)

        # Apply default table style
        style = table_def.get("style", {})

        # Process each row
        for row_idx, row_data in enumerate(rows_data):
            is_header = row_data.get("header", False)
            row_style = row_data.get("style", {})
            cells = row_data.get("cells", [])

            for col_idx, cell_data in enumerate(cells):
                if col_idx >= num_cols:
                    break
                cell = table.cell(row_idx, col_idx)
                self._format_cell(cell, cell_data, is_header, row_style, style)

        # Apply row heights if specified
        row_heights = table_def.get("row_heights")
        if row_heights:
            for i, h in enumerate(row_heights):
                if h is not None and i < len(table.rows):
                    table.rows[i].height = Inches(h)

        # Apply cell merges after all cells are formatted
        merges = table_def.get("merges", [])
        for merge in merges:
            start_row = merge["start_row"]
            start_col = merge["start_col"]
            end_row = merge["end_row"]
            end_col = merge["end_col"]
            table.cell(start_row, start_col).merge(table.cell(end_row, end_col))

        # Apply table borders if specified
        borders = table_def.get("borders")
        if borders:
            self._apply_table_borders(table, borders)

    @staticmethod
    def _replace_empty_placeholder(slide, table_def: dict) -> None:
        """Remove the placeholder a table was placed into, when it holds no text.

        Left in place, the empty placeholder sits under the table, overlaps it in
        `extract-shapes` and counts as an unfilled visual slot in `validate`.
        """
        if table_def.get("position") or table_def.get("placeholder_index") is None:
            return
        for shape in slide.placeholders:
            if shape.placeholder_format.idx == table_def["placeholder_index"]:
                if not (shape.has_text_frame and shape.text_frame.text.strip()):
                    shape._element.getparent().remove(shape._element)
                return

    def _resolve_position(self, slide, table_def: dict) -> tuple:
        """Resolve table position from placeholder or explicit coordinates."""
        # Check for explicit position
        pos = table_def.get("position")
        if pos:
            return (
                Inches(pos.get("left", 0.5)),
                Inches(pos.get("top", 1.5)),
                Inches(pos.get("width", 9.0)),
                Inches(pos.get("height", 5.0)),
            )

        # Check for placeholder
        placeholder_idx = table_def.get("placeholder_index")
        if placeholder_idx is not None:
            for shape in slide.placeholders:
                if shape.placeholder_format.idx == placeholder_idx:
                    return (shape.left, shape.top, shape.width, shape.height)
            self.warnings.append(f"  Warning: Placeholder index {placeholder_idx} not found, using defaults")

        # Default position (centered, below typical title area)
        return (Inches(0.5), Inches(1.5), Inches(9.0), Inches(5.0))

    def _format_cell(self, cell, cell_data, is_header: bool, row_style: dict, table_style: dict) -> None:
        """Format a single table cell."""
        # cell_data can be a string (shorthand) or a dict
        if isinstance(cell_data, str):
            cell_data = {"text": cell_data}

        text = cell_data.get("text", "")

        # Resolve effective properties: cell > row > table defaults
        bg_color = cell_data.get("background_color") or row_style.get("background_color") or table_style.get("background_color")
        font_color = cell_data.get("color") or row_style.get("color") or table_style.get("color")
        font_size = cell_data.get("font_size") or row_style.get("font_size") or table_style.get("font_size")
        bold = cell_data.get("bold") if cell_data.get("bold") is not None else row_style.get("bold") if row_style.get("bold") is not None else table_style.get("bold")
        italic = cell_data.get("italic") if cell_data.get("italic") is not None else row_style.get("italic") if row_style.get("italic") is not None else table_style.get("italic")
        font_name = cell_data.get("font_name") or row_style.get("font_name") or table_style.get("font_name")
        alignment = cell_data.get("alignment") or row_style.get("alignment") or table_style.get("alignment")

        # Header defaults
        if is_header:
            if bg_color is None:
                bg_color = "#1F4E79"
            if font_color is None:
                font_color = "#FFFFFF"
            if bold is None:
                bold = True

        # Apply background color
        if bg_color:
            self._set_cell_background(cell, bg_color)

        # Set cell text and run/paragraph styling through the shared
        # ParagraphProcessor (same path add-text/add-shapes use), not a
        # table-only reimplementation of font/color/alignment.
        cell.text = ""
        paragraph = cell.text_frame.paragraphs[0]
        para_props = {"text": text}
        if font_size:
            para_props["font_size"] = font_size
        if bold is not None:
            para_props["bold"] = bold
        if italic is not None:
            para_props["italic"] = italic
        if font_name:
            para_props["font_name"] = font_name
        if font_color:
            para_props["color"] = font_color
        if alignment and alignment in ALIGNMENT_MAP:
            para_props["alignment"] = alignment
        _PARAGRAPH_PROCESSOR.apply_properties(paragraph, para_props)

        # Apply vertical anchor
        vertical_anchor = cell_data.get("vertical_anchor")
        if vertical_anchor:
            from pptx.enum.text import MSO_ANCHOR
            anchor_map = {"TOP": MSO_ANCHOR.TOP, "MIDDLE": MSO_ANCHOR.MIDDLE, "BOTTOM": MSO_ANCHOR.BOTTOM}
            if vertical_anchor in anchor_map:
                cell.vertical_anchor = anchor_map[vertical_anchor]

        # Apply cell padding / internal margins
        cell_margin = (
            cell_data.get("cell_margin_in")
            or row_style.get("cell_margin_in")
            or table_style.get("cell_margin_in")
        )
        if cell_margin is not None:
            if isinstance(cell_margin, (int, float)):
                m = Inches(cell_margin)
                cell.margin_top = m
                cell.margin_bottom = m
                cell.margin_left = m
                cell.margin_right = m
            elif isinstance(cell_margin, dict):
                if "top" in cell_margin:
                    cell.margin_top = Inches(cell_margin["top"])
                if "bottom" in cell_margin:
                    cell.margin_bottom = Inches(cell_margin["bottom"])
                if "left" in cell_margin:
                    cell.margin_left = Inches(cell_margin["left"])
                if "right" in cell_margin:
                    cell.margin_right = Inches(cell_margin["right"])

    @staticmethod
    def _apply_table_borders(table, borders_def: dict) -> None:
        """Apply border styling to all cells in a table.

        borders_def keys:
          "none": true — remove all borders
          "outer": {"color": "#RRGGBB", "weight_pt": 1.0, "dash": "solid"}
          "inner_h": {"color": "#RRGGBB", "weight_pt": 0.5}
          "inner_v": {"color": "#RRGGBB", "weight_pt": 0.5}
        """
        from lxml import etree
        from pptx.oxml.ns import qn

        ns = "http://schemas.openxmlformats.org/drawingml/2006/main"
        nrows = len(table.rows)
        ncols = len(table.columns)

        def make_ln_element(tag, spec):
            ln = etree.SubElement(etree.Element("dummy"), f"{{{ns}}}{tag}")
            ln = etree.Element(f"{{{ns}}}{tag}")
            if spec:
                weight = spec.get("weight_pt")
                color = spec.get("color")
                dash = spec.get("dash", "solid").lower()
                if weight is not None:
                    ln.set("w", str(int(Pt(weight))))
                if color:
                    solidFill = etree.SubElement(ln, f"{{{ns}}}solidFill")
                    srgbClr = etree.SubElement(solidFill, f"{{{ns}}}srgbClr")
                    srgbClr.set("val", color.lstrip("#"))
                else:
                    etree.SubElement(ln, f"{{{ns}}}noFill")
                prstDash = etree.SubElement(ln, f"{{{ns}}}prstDash")
                prstDash.set("val", dash)
            else:
                etree.SubElement(ln, f"{{{ns}}}noFill")
            return ln

        for r_idx, row in enumerate(table.rows):
            for c_idx, cell in enumerate(row.cells):
                tc = cell._tc
                tcPr = tc.get_or_add_tcPr()

                # Remove existing border elements
                for tag in ["lnL", "lnR", "lnT", "lnB", "lnTlToBr", "lnBlToTr"]:
                    existing = tcPr.find(f"{{{ns}}}{tag}")
                    if existing is not None:
                        tcPr.remove(existing)

                if borders_def.get("none"):
                    # Explicitly set noFill on all sides
                    for tag in ["lnL", "lnR", "lnT", "lnB"]:
                        ln = etree.SubElement(tcPr, f"{{{ns}}}{tag}")
                        etree.SubElement(ln, f"{{{ns}}}noFill")
                    continue

                outer_spec = borders_def.get("outer")
                inner_h_spec = borders_def.get("inner_h")
                inner_v_spec = borders_def.get("inner_v")

                is_top = r_idx == 0
                is_bottom = r_idx == nrows - 1
                is_left = c_idx == 0
                is_right = c_idx == ncols - 1

                side_specs = {
                    "lnT": outer_spec if is_top else inner_h_spec,
                    "lnB": outer_spec if is_bottom else inner_h_spec,
                    "lnL": outer_spec if is_left else inner_v_spec,
                    "lnR": outer_spec if is_right else inner_v_spec,
                }

                for tag, spec in side_specs.items():
                    if spec is not None or borders_def.get("outer") is not None:
                        ln = make_ln_element(tag, spec)
                        tcPr.append(ln)

    @staticmethod
    def _set_cell_background(cell, color_hex: str) -> None:
        """Set cell background color via XML manipulation."""
        from pptx.oxml.xmlchemy import OxmlElement
        from pptx.oxml.ns import qn

        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()

        # Remove existing solidFill if present
        for child in list(tcPr):
            if child.tag.endswith("solidFill"):
                tcPr.remove(child)

        solidFill = OxmlElement("a:solidFill")
        srgbClr = OxmlElement("a:srgbClr")
        srgbClr.set("val", color_hex.lstrip("#"))
        solidFill.append(srgbClr)
        tcPr.append(solidFill)


def _parse_color(color_hex: str) -> RGBColor:
    """Parse a hex color string to RGBColor."""
    h = color_hex.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def run_add_table(args) -> int:
    """Entry point from CLI dispatcher."""
    input_pptx = Path(args.input)
    output_pptx = Path(args.output)
    # The CLI reports a missing input before a missing or malformed table data file.
    require_file(input_pptx, f"Input file '{input_pptx}' not found")
    try:
        table_data = load_data_json(Path(args.table_data), "Table data")
        result = PresentationTableAdder().add_tables(input_pptx, table_data, output_pptx)
    except Exception as e:
        if print_unexpected_failure(e):
            return 1
        raise
    print_tables_added(result)
    return 0


def print_tables_added(result: TablesAdded) -> None:
    """Print the add-table report: warnings, the saved path and the number of tables added."""
    for line in result.warnings:
        print(line)
    print(f"Saved presentation to: {result.output_path}")
    print(f"Tables added: {result.tables_added}")
