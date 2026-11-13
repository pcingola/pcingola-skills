"""Integration tests for the add-table command."""
import json
import unittest

from pptx import Presentation
from pptx.util import Inches

from tests.integration.pptx import (
    cleanup_dir, create_test_pptx, fresh_dir, run_cli, stamp_description,
)

DIR = fresh_dir("test_add_table")


def write_table_data_json(d, data, name="table_data.json"):
    """Write a table data JSON file."""
    path = d / name
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path


class TestAddTable(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = create_test_pptx(DIR, num_slides=3)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_basic_table(self) -> None:
        """add-table builds a table with one row per JSON row and the cell texts in order. Guards
        the rows/cells mapping of add-table."""
        table_data = {
            "slide-0": {
                "rows": [
                    {"cells": ["Name", "Value"]},
                    {"cells": ["Alpha", "100"]},
                    {"cells": ["Beta", "200"]},
                ]
            }
        }
        table_json = write_table_data_json(DIR, table_data, "basic.json")
        out = DIR / "basic.pptx"
        r = run_cli("add-table", str(self.source), str(table_json), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(out.exists())

        prs = Presentation(str(out))
        slide = prs.slides[0]
        tables = [s for s in slide.shapes if s.has_table]
        self.assertEqual(len(tables), 1)
        tbl = tables[0].table
        self.assertEqual(len(tbl.rows), 3)
        self.assertEqual(len(tbl.columns), 2)
        self.assertEqual(tbl.cell(0, 0).text, "Name")
        self.assertEqual(tbl.cell(1, 1).text, "100")

        stamp_description(out,
            "add-table: basic 3x2 table on slide 0.\n"
            "Expected:\n"
            "  Row 0: Name | Value\n"
            "  Row 1: Alpha | 100\n"
            "  Row 2: Beta | 200")

    def test_header_row_styling(self) -> None:
        """add-table makes the text of a row with header true bold. Guards the header row styling
        applied by add-table."""
        table_data = {
            "slide-0": {
                "rows": [
                    {"header": True, "cells": ["Metric", "Q1", "Q2"]},
                    {"cells": ["Revenue", "$2.5M", "$3.1M"]},
                ]
            }
        }
        table_json = write_table_data_json(DIR, table_data, "header.json")
        out = DIR / "header.pptx"
        r = run_cli("add-table", str(self.source), str(table_json), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)

        prs = Presentation(str(out))
        tbl = [s for s in prs.slides[0].shapes if s.has_table][0].table
        # Header cell should be bold
        header_run = tbl.cell(0, 0).text_frame.paragraphs[0].runs[0]
        self.assertTrue(header_run.font.bold)

        stamp_description(out,
            "add-table: table with header row styling.\n"
            "Expected:\n"
            "  Header row: dark blue background, white bold text\n"
            "  Data row: default styling")

    def test_cell_formatting(self) -> None:
        """add-table applies per-cell bold, colour and italic from cell objects and accepts plain
        strings in the same row. Guards the mixed cell formats of the table JSON."""
        table_data = {
            "slide-0": {
                "rows": [
                    {"header": True, "cells": ["Feature", "Status", "Notes"]},
                    {"cells": [
                        {"text": "Bold Cell", "bold": True, "font_size": 16},
                        {"text": "Green BG", "background_color": "#E2EFDA"},
                        {"text": "Red Text", "color": "#FF0000"},
                    ]},
                    {"cells": [
                        {"text": "Italic", "italic": True},
                        {"text": "Large", "font_size": 20},
                        "Plain text",
                    ]},
                ]
            }
        }
        table_json = write_table_data_json(DIR, table_data, "cell_fmt.json")
        out = DIR / "cell_fmt.pptx"
        r = run_cli("add-table", str(self.source), str(table_json), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)

        prs = Presentation(str(out))
        tbl = [s for s in prs.slides[0].shapes if s.has_table][0].table
        self.assertEqual(len(tbl.rows), 3)
        self.assertEqual(len(tbl.columns), 3)
        # Bold cell in row 1
        run0 = tbl.cell(1, 0).text_frame.paragraphs[0].runs[0]
        self.assertTrue(run0.font.bold)
        # Red text cell in row 1
        run2 = tbl.cell(1, 2).text_frame.paragraphs[0].runs[0]
        self.assertEqual(str(run2.font.color.rgb), "FF0000")
        # Italic cell in row 2
        run_italic = tbl.cell(2, 0).text_frame.paragraphs[0].runs[0]
        self.assertTrue(run_italic.font.italic)

        stamp_description(out,
            "add-table: cell-level formatting (3x3).\n"
            "Expected:\n"
            "  Header: Feature | Status | Notes (dark blue bg, white bold)\n"
            "  Row 1: bold 16pt | green bg | red text\n"
            "  Row 2: italic | 20pt | plain")

    def test_column_widths(self) -> None:
        """add-table sets each column to its column_widths value in inches. Guards the column width
        mapping."""
        table_data = {
            "slide-0": {
                "rows": [
                    {"header": True, "cells": ["ID", "Description", "Amount"]},
                    {"cells": ["1", "Widget Alpha — premium edition", "$49.99"]},
                    {"cells": ["2", "Widget Beta — standard", "$29.99"]},
                    {"cells": ["3", "Accessory Pack", "$9.99"]},
                ],
                "column_widths": [1.0, 4.0, 2.5],
            }
        }
        table_json = write_table_data_json(DIR, table_data, "col_widths.json")
        out = DIR / "col_widths.pptx"
        r = run_cli("add-table", str(self.source), str(table_json), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)

        prs = Presentation(str(out))
        tbl = [s for s in prs.slides[0].shapes if s.has_table][0].table
        self.assertEqual(len(tbl.rows), 4)
        self.assertEqual(tbl.columns[0].width, Inches(1.0))
        self.assertEqual(tbl.columns[1].width, Inches(4.0))
        self.assertEqual(tbl.columns[2].width, Inches(2.5))

        stamp_description(out,
            "add-table: custom column widths (4x3).\n"
            "Expected: narrow ID col (1\"), wide description (4\"), medium amount (2.5\")")

    def test_cell_merging(self) -> None:
        """add-table merges the cell range given in merges, with the start cell as merge origin.
        Guards the merges option."""
        table_data = {
            "slide-0": {
                "rows": [
                    {"header": True, "cells": ["Category", "Details", ""]},
                    {"cells": ["A", "Info A1", "Info A2"]},
                    {"cells": ["A", "Info A3", "Info A4"]},
                ],
                "merges": [
                    {"start_row": 0, "start_col": 1, "end_row": 0, "end_col": 2},
                ]
            }
        }
        table_json = write_table_data_json(DIR, table_data, "merge.json")
        out = DIR / "merge.pptx"
        r = run_cli("add-table", str(self.source), str(table_json), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)

        prs = Presentation(str(out))
        tbl = [s for s in prs.slides[0].shapes if s.has_table][0].table
        # Merged cells should span — the merge makes cell(0,1) span to cell(0,2)
        self.assertTrue(tbl.cell(0, 1).is_merge_origin)

        stamp_description(out,
            "add-table: cell merging.\n"
            "Expected:\n"
            "  Header row: 'Category' | 'Details' merged across cols 1-2\n"
            "  Data rows: normal 3-column layout")

    def test_explicit_position(self) -> None:
        """add-table places the table at the given position in inches. Guards the position option
        instead of the default placement."""
        table_data = {
            "slide-0": {
                "rows": [
                    {"header": True, "cells": ["Region", "Sales", "Target"]},
                    {"cells": ["North", "$1.2M", "$1.0M"]},
                    {"cells": ["South", "$0.8M", "$1.0M"]},
                ],
                "position": {"left": 2.0, "top": 3.0, "width": 6.0, "height": 2.0},
            }
        }
        table_json = write_table_data_json(DIR, table_data, "position.json")
        out = DIR / "position.pptx"
        r = run_cli("add-table", str(self.source), str(table_json), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)

        prs = Presentation(str(out))
        table_shape = [s for s in prs.slides[0].shapes if s.has_table][0]
        self.assertEqual(table_shape.left, Inches(2.0))
        self.assertEqual(table_shape.top, Inches(3.0))

        stamp_description(out,
            "add-table: explicit position (3x3).\n"
            "Expected: table at left=2\", top=3\", 6\"x2\"")

    def test_multiple_tables_on_slide(self) -> None:
        """add-table with a list of table specs for one slide adds every table. Guards the list form
        of the slide value."""
        table_data = {
            "slide-0": [
                {
                    "rows": [
                        {"header": True, "cells": ["Product", "Price"]},
                        {"cells": ["Widget A", "$10"]},
                        {"cells": ["Widget B", "$20"]},
                    ],
                    "position": {"left": 0.5, "top": 1.5, "width": 4.0, "height": 2.5},
                },
                {
                    "rows": [
                        {"header": True, "cells": ["Service", "Rate"]},
                        {"cells": ["Support", "$50/hr"]},
                        {"cells": ["Consulting", "$150/hr"]},
                    ],
                    "position": {"left": 5.5, "top": 1.5, "width": 4.0, "height": 2.5},
                },
            ]
        }
        table_json = write_table_data_json(DIR, table_data, "multi.json")
        out = DIR / "multi.pptx"
        r = run_cli("add-table", str(self.source), str(table_json), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)

        prs = Presentation(str(out))
        tables = [s for s in prs.slides[0].shapes if s.has_table]
        self.assertEqual(len(tables), 2)
        for tbl_shape in tables:
            self.assertEqual(len(tbl_shape.table.rows), 3)
            self.assertEqual(len(tbl_shape.table.columns), 2)

        stamp_description(out,
            "add-table: two 3x2 tables side by side on slide 0.\n"
            "Expected: Products table on left, Services table on right")

    def test_table_style_defaults(self) -> None:
        """add-table applies the table-level style font_size to data cells. Guards the table-wide
        style defaults."""
        table_data = {
            "slide-0": {
                "rows": [
                    {"header": True, "cells": ["Name", "Role", "Status"]},
                    {"cells": ["Alice", "Engineer", "Active"]},
                    {"cells": ["Bob", "Designer", "On Leave"]},
                    {"cells": ["Carol", "Manager", "Active"]},
                ],
                "style": {"font_size": 14, "alignment": "CENTER"},
            }
        }
        table_json = write_table_data_json(DIR, table_data, "style.json")
        out = DIR / "style.pptx"
        r = run_cli("add-table", str(self.source), str(table_json), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)

        prs = Presentation(str(out))
        tbl = [s for s in prs.slides[0].shapes if s.has_table][0].table
        self.assertEqual(len(tbl.rows), 4)
        from pptx.util import Pt
        # Check style applies to data cells
        run = tbl.cell(1, 0).text_frame.paragraphs[0].runs[0]
        self.assertEqual(run.font.size, Pt(14))
        run2 = tbl.cell(2, 2).text_frame.paragraphs[0].runs[0]
        self.assertEqual(run2.font.size, Pt(14))

        stamp_description(out,
            "add-table: table-level style defaults (4x3).\n"
            "Expected: all cells 14pt, center-aligned")

    def test_invalid_slide_index(self) -> None:
        """add-table exits non-zero for slide-99 on a three-slide deck. Guards the slide range
        check."""
        table_data = {
            "slide-99": {
                "rows": [
                    {"header": True, "cells": ["Col A", "Col B"]},
                    {"cells": ["data", "data"]},
                ]
            }
        }
        table_json = write_table_data_json(DIR, table_data, "bad_slide.json")
        out = DIR / "bad_slide.pptx"
        r = run_cli("add-table", str(self.source), str(table_json), str(out))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_missing_rows(self) -> None:
        """add-table exits non-zero for a table spec without rows. Guards the required rows key."""
        table_data = {
            "slide-0": {
                "column_widths": [2.0, 3.0]
            }
        }
        table_json = write_table_data_json(DIR, table_data, "no_rows.json")
        out = DIR / "no_rows.pptx"
        r = run_cli("add-table", str(self.source), str(table_json), str(out))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_missing_input_file(self) -> None:
        """add-table exits non-zero when the input deck does not exist. Guards the input check of
        the command."""
        table_json = write_table_data_json(DIR, {}, "empty.json")
        out = DIR / "missing_input.pptx"
        r = run_cli("add-table", "/nonexistent.pptx", str(table_json), str(out))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_missing_json_file(self) -> None:
        """add-table exits non-zero when the table JSON does not exist. Guards the data file check."""
        out = DIR / "missing_json.pptx"
        r = run_cli("add-table", str(self.source), "/nonexistent.json", str(out))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
