"""Integration tests for the add-text command."""
import json
import unittest

from pptx import Presentation
from pptx.util import Pt

from tests.integration.pptx import (
    cleanup_dir, create_multilayout_pptx, create_test_pptx, fresh_dir, run_cli,
    stamp_description, write_text_data_json,
)

DIR = fresh_dir("test_add_text")


class TestAddText(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = create_test_pptx(DIR, num_slides=2)
        # Extract shapes to know valid shape keys
        cls.inventory = DIR / "inventory.json"
        r = run_cli("extract-shapes", str(cls.source), str(cls.inventory))
        assert r.returncode == 0, f"extract-shapes failed: {r.stderr}"
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
        """add-text replaces a shape's text with the JSON paragraphs and applies their bold and font
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
        text_json = write_text_data_json(DIR, text_data, "formatted.json")
        out = DIR / "add_formatted.pptx"
        r = run_cli("add-text", str(self.source), str(text_json), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
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
        """add-text exits non-zero for a shape key that is not on the slide. Guards the shape key
        validation against the inventory."""
        text_data = {
            "slide-0": {
                "shape-999": {
                    "paragraphs": [{"text": "Ghost"}]
                }
            }
        }
        text_json = write_text_data_json(DIR, text_data, "bad_shape.json")
        out = DIR / "add_bad_shape.pptx"
        r = run_cli("add-text", str(self.source), str(text_json), str(out))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_add_text_missing_input(self) -> None:
        """add-text exits non-zero when the input deck does not exist. Guards the input check of the
        command."""
        text_json = write_text_data_json(DIR, {}, "empty.json")
        out = DIR / "add_missing.pptx"
        r = run_cli("add-text", "/nonexistent.pptx", str(text_json), str(out))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_add_text_missing_json(self) -> None:
        """add-text exits non-zero when the text JSON does not exist. Guards the data file check."""
        out = DIR / "add_no_json.pptx"
        r = run_cli("add-text", str(self.source), "/nonexistent.json", str(out))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_deck_containing_a_table_does_not_crash(self) -> None:
        """add-text on a deck with a table replaces the title text and leaves the table cells
        unchanged. Guards the past bug where reading text_frame of a GraphicFrame table crashed
        the command."""
        source = create_multilayout_pptx(DIR, "with_table.pptx")
        data = write_text_data_json(
            DIR,
            {"slide-0": {"shape-0": {"paragraphs": [{"text": "Replaced title"}]}}},
            name="table_deck_text.json",
        )
        out = DIR / "table_deck.pptx"
        r = run_cli("add-text", str(source), str(data), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)

        prs = Presentation(str(out))
        self.assertTrue(any("Replaced title" in s.text_frame.text
                            for s in prs.slides[0].shapes if s.has_text_frame))
        # The table itself must survive untouched.
        table = next(s.table for s in prs.slides[4].shapes if s.has_table)
        self.assertEqual(table.cell(0, 0).text, "Region")
