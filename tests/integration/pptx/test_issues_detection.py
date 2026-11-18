"""What `extract-shapes --issues-only` actually flags.

A shape whose text fits is not flagged, and one that does not fit is. Both directions matter. A detector
that flags everything and one that flags nothing are equally useless, and each
passes a test that only checks the other direction.
"""
import json
import unittest
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx_tool.cmd_extract_shapes import extract_shapes

from tests.integration.pptx import (
    cleanup_dir, fresh_dir, write_readme,
)

DIR = fresh_dir("test_issues_detection")


def _deck(name: str, build) -> Path:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    build(prs.slides.add_slide(prs.slide_layouts[6]))  # blank
    path = DIR / name
    prs.save(str(path))
    return path


def _textbox(slide, left, top, width, height, text, size=18):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    box.text_frame.word_wrap = True
    para = box.text_frame.paragraphs[0]
    para.text = text
    para.font.size = Pt(size)
    return box


class TestIssuesOnly(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        write_readme(DIR,
            "extract-shapes --issues-only: the overflow / overlap / off-slide detector.\n"
            "Each .pptx here isolates one condition; the matching .json is what the\n"
            "detector reported. fits.pptx must produce no JSON at all.")

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def _issues(self, deck: Path, name: str):
        """The issues JSON extract_shapes writes for `deck`, or None when it reports no issues."""
        out = DIR / f"{name}.json"
        result = extract_shapes(deck, out, issues_only=True)
        self.assertEqual(result is not None, out.exists(), "the return value disagrees with the file")
        return json.loads(out.read_text()) if result is not None else None

    def test_overflowing_text_is_flagged_with_an_amount(self) -> None:
        """extract_shapes with issues_only reports a text box whose text cannot fit with a positive
        frame overflow_bottom. Guards the overflow detector in the flagging direction."""
        deck = _deck("overflow.pptx",
                     lambda s: _textbox(s, 1, 1, 1.5, 0.4, " ".join(["overflowing"] * 60)))
        data = self._issues(deck, "overflow")
        self.assertIsNotNone(data, "an obviously overflowing box was not flagged")
        shape = next(iter(data["slide-0"].values()))
        self.assertGreater(shape["overflow"]["frame"]["overflow_bottom"], 0)

    def test_shape_off_the_slide_edge_is_flagged(self) -> None:
        """extract_shapes with issues_only reports a box extending past the right slide edge with a
        positive slide overflow_right. Guards the off-slide check."""
        deck = _deck("offslide.pptx", lambda s: _textbox(s, 12.0, 1, 4, 1, "Hanging off the right"))
        data = self._issues(deck, "offslide")
        self.assertIsNotNone(data)
        shape = next(iter(data["slide-0"].values()))
        self.assertGreater(shape["overflow"]["slide"]["overflow_right"], 0)

    def test_overlapping_shapes_are_flagged_on_both_sides(self) -> None:
        """extract_shapes with issues_only reports two overlapping boxes, each with the other in
        overlapping_shapes. Guards that overlap is recorded on both shapes."""
        def build(slide):
            _textbox(slide, 1, 1, 4, 2, "First box")
            _textbox(slide, 2, 1.5, 4, 2, "Second box")

        deck = _deck("overlap.pptx", build)
        data = self._issues(deck, "overlap")
        self.assertIsNotNone(data, "two boxes sitting on top of each other were not flagged")
        shapes = data["slide-0"]
        self.assertEqual(len(shapes), 2, "overlap must be reported against both shapes")
        for shape in shapes.values():
            self.assertTrue(shape["overlap"]["overlapping_shapes"])

    def test_manual_bullet_character_is_warned_about(self) -> None:
        """extract_shapes with issues_only warns manual_bullet_symbol for text starting with a typed
        bullet. Guards the manual bullet warning."""
        deck = _deck("bullets.pptx", lambda s: _textbox(s, 1, 1, 8, 2, "• typed by hand"))
        data = self._issues(deck, "bullets")
        self.assertIsNotNone(data)
        shape = next(iter(data["slide-0"].values()))
        self.assertIn("manual_bullet_symbol", " ".join(shape["warnings"]))

    def test_clean_deck_says_so_and_writes_nothing(self) -> None:
        """extract_shapes with issues_only on a box whose text fits returns None, which the CLI
        prints as "No issues discovered", and writes no file. Guards the detector in the
        non-flagging direction and the no-file rule."""
        deck = _deck("clean.pptx", lambda s: _textbox(s, 1, 1, 8, 2, "All fine here"))
        out = DIR / "clean.json"
        self.assertIsNone(extract_shapes(deck, out, issues_only=True))
        self.assertFalse(out.exists())
