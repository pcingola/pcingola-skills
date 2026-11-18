"""Integration tests for the add-text command.

The tests call the core function `PresentationTextAdder.add_text`. The test of the text data
file check calls the CLI in process, because the CLI layer loads that file.
"""
import json
import unittest
from pathlib import Path

from pptx import Presentation
from pptx.util import Pt

from pptx_tool.cmd_add_text import PresentationTextAdder
from pptx_tool.cmd_extract_shapes import extract_shapes
from pptx_tool.exceptions import PptxError, ValidationError
from tests.integration.pptx import (
    cleanup_dir, cli, create_multilayout_pptx, create_test_pptx, fresh_dir,
    stamp_description,
)

DIR = fresh_dir("test_add_text")


class TestAddText(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = create_test_pptx(DIR, num_slides=2)
        # Extract shapes to know valid shape keys
        cls.inventory = DIR / "inventory.json"
        extract_shapes(cls.source, cls.inventory)
        cls.inventory_data = json.loads(cls.inventory.read_text())

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def _first_text_shape(self, slide_key: str = "slide-0") -> str | None:
        """Find the first shape key with paragraphs on the given slide."""
        slide_data = self.inventory_data.get(slide_key, {})
        for shape_key, shape_data in slide_data.items():
            if shape_data.get("paragraphs"):
                return shape_key
        return None

    def test_add_text_with_formatting(self) -> None:
        """add_text replaces a shape's text with the JSON paragraphs and applies their bold and font
        sizes. Guards the paragraph formatting mapping of add-text."""
        shape_key = self._first_text_shape()
        self.assertIsNotNone(shape_key)

        text_data = {
            "slide-0": {
                shape_key: {
                    "paragraphs": [
                        {"text": "Bold Heading", "font_size": 24, "bold": True},
                        {"text": "Normal body text", "font_size": 14},
                    ]
                }
            }
        }
        out = DIR / "add_formatted.pptx"
        PresentationTextAdder().add_text(self.source, text_data, out)
        shape = next(s for s in Presentation(str(out)).slides[0].shapes
                     if s.has_text_frame and "Bold Heading" in s.text_frame.text)
        heading, body = shape.text_frame.paragraphs[:2]
        self.assertEqual(body.text, "Normal body text")
        self.assertTrue(heading.runs[0].font.bold)
        self.assertEqual(heading.runs[0].font.size, Pt(24))
        self.assertEqual(body.runs[0].font.size, Pt(14))
        stamp_description(out,
            f"add-text: replaced text in slide-0/{shape_key} with formatting.\n"
            f"Expected in {shape_key}:\n"
            f"  Paragraph 1: 'Bold Heading' - 24pt, bold\n"
            f"  Paragraph 2: 'Normal body text' - 14pt, normal weight\n"
            f"  Slide 2: original content unchanged")

    def test_add_text_invalid_shape(self) -> None:
        """add_text raises ValidationError for a shape key that is not on the slide, with a detail
        line naming the shape, and writes no output. Guards the shape key validation against the
        inventory."""
        text_data = {
            "slide-0": {
                "shape-999": {
                    "paragraphs": [{"text": "Ghost"}]
                }
            }
        }
        out = DIR / "add_bad_shape.pptx"
        with self.assertRaisesRegex(ValidationError, r"Found 1 validation error\(s\)") as ctx:
            PresentationTextAdder().add_text(self.source, text_data, out)
        self.assertTrue(any("Shape 'shape-999' not found on 'slide-0'" in line
                            for line in ctx.exception.details))
        self.assertFalse(out.exists())

    def test_add_text_missing_input(self) -> None:
        """add_text raises PptxError naming the input deck when it does not exist. Guards the input
        check of the command."""
        out = DIR / "add_missing.pptx"
        with self.assertRaisesRegex(PptxError, "Input file '/nonexistent.pptx' not found"):
            PresentationTextAdder().add_text(Path("/nonexistent.pptx"), {}, out)
        self.assertFalse(out.exists())

    def test_add_text_missing_json(self) -> None:
        """The add-text CLI exits with 1 and prints the not-found error when the text data JSON does
        not exist. Guards the data file check of the CLI layer, which loads the file."""
        out = DIR / "add_no_json.pptx"
        r = cli("add-text", str(self.source), "/nonexistent.json", str(out))
        self.assertEqual(r.returncode, 1)
        self.assertIn("Error: Text data JSON file '/nonexistent.json' not found", r.stdout)
        self.assertFalse(out.exists())

    def test_deck_containing_a_table_does_not_crash(self) -> None:
        """add_text on a deck with a table replaces the title text and leaves the table cells
        unchanged. Guards the past bug where reading text_frame of a GraphicFrame table crashed
        the command."""
        source = create_multilayout_pptx(DIR, "with_table.pptx")
        data = {"slide-0": {"shape-0": {"paragraphs": [{"text": "Replaced title"}]}}}
        out = DIR / "table_deck.pptx"
        PresentationTextAdder().add_text(source, data, out)

        prs = Presentation(str(out))
        self.assertTrue(any("Replaced title" in s.text_frame.text
                            for s in prs.slides[0].shapes if s.has_text_frame))
        # The table itself must survive untouched.
        table = next(s.table for s in prs.slides[4].shapes if s.has_table)
        self.assertEqual(table.cell(0, 0).text, "Region")
