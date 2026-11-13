"""Table-cell and speaker-notes coverage in the pptx read path.

`extract_text` walks GraphicFrame tables (`is_valid_table_shape`) and records
them per-shape with cell formatting, fills and borders, on table-only slides
included. Speaker notes are collected separately (`extract_all_notes`).
"""
import unittest

from pptx import Presentation
from pptx.util import Inches

from pptx_tool.cmd_extract_shapes import (
    extract_all_notes, extract_slide_notes, extract_text, shapes_data_to_json,
)


def _deck_with_table_and_notes(path):
    """Build a one-slide deck carrying a 2x2 table and speaker notes."""
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank

    table = slide.shapes.add_table(2, 2, Inches(1), Inches(1), Inches(6), Inches(2)).table
    table.cell(0, 0).text = "Region"
    table.cell(0, 1).text = "Revenue"
    table.cell(1, 0).text = "EMEA"
    table.cell(1, 1).text = "$45M"

    slide.notes_slide.notes_text_frame.text = "Talk track: emphasise EMEA growth."
    prs.save(str(path))
    return prs, slide


def _blank_deck():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    return prs, slide


class TestTableExtraction(unittest.TestCase):
    """A slide whose only content is a table must still appear, with its cells."""

    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.deck = f"{self._tmp.name}/deck.pptx"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_table_only_slide_is_not_skipped(self) -> None:
        """cmd_extract_shapes.extract_text keeps a slide whose only shape is a table. Guards against
        dropping table-only slides from the shapes JSON."""
        _deck_with_table_and_notes(self.deck)
        data = shapes_data_to_json(extract_text(self.deck))
        self.assertIn("slide-0", data, "a slide carrying only a table was dropped")

    def test_cell_text_is_row_major(self) -> None:
        """cmd_extract_shapes.extract_text records a table's cell text row by row with num_rows and
        num_cols. Guards the table structure in the shapes JSON."""
        _deck_with_table_and_notes(self.deck)
        data = shapes_data_to_json(extract_text(self.deck))
        tables = [s["table"] for s in data["slide-0"].values() if "table" in s]
        self.assertEqual(len(tables), 1)
        rows = [[cell["text"] for cell in row["cells"]] for row in tables[0]["rows"]]
        self.assertEqual(rows, [["Region", "Revenue"], ["EMEA", "$45M"]])
        self.assertEqual(tables[0]["num_rows"], 2)
        self.assertEqual(tables[0]["num_cols"], 2)


class TestExtractSlideNotes(unittest.TestCase):

    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.deck = f"{self._tmp.name}/deck.pptx"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_returns_notes_text(self) -> None:
        """cmd_extract_shapes.extract_slide_notes returns the slide's speaker-notes text. Guards
        notes extraction, which lives outside the shape tree."""
        _, slide = _deck_with_table_and_notes(self.deck)
        self.assertEqual(extract_slide_notes(slide), "Talk track: emphasise EMEA growth.")

    def test_no_notes_returns_empty_string(self) -> None:
        """cmd_extract_shapes.extract_slide_notes returns "" for a slide without a notes slide.
        Guards the has_notes_slide check, which avoids creating a notes slide on read."""
        _, slide = _blank_deck()
        self.assertEqual(extract_slide_notes(slide), "")

    def test_extract_all_notes_keys_by_slide_and_skips_empty(self) -> None:
        """cmd_extract_shapes.extract_all_notes maps slide-N to stripped notes and omits slides
        without notes. Guards the slide keys and the skipping of empty notes."""
        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])                      # no notes
        second = prs.slides.add_slide(prs.slide_layouts[6])
        second.notes_slide.notes_text_frame.text = "  second slide notes  "
        self.assertEqual(extract_all_notes(prs), {"slide-1": "second slide notes"})
