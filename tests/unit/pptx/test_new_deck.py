"""Unit tests for new-deck: size mapping and argument validation.

These assert the command's own logic (SIZE_MAP wiring, slide-count loop,
guard rails), not that python-pptx can create a Presentation.
"""
import tempfile
import unittest
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches

from pptx_tool.cmd_new_deck import create_deck
from pptx_tool.exceptions import ValidationError


class TestCreateDeckValidation(unittest.TestCase):

    def _out(self) -> str:
        return str(Path(self.tmp.name) / "deck.pptx")

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_zero_slides_rejected(self) -> None:
        """cmd_new_deck.create_deck raises ValidationError for slides=0. Guards the --slides >= 1
        check, without which an empty deck is saved."""
        with self.assertRaises(ValidationError):
            create_deck(self._out(), slides=0, size="16:9")

    def test_unknown_size_rejected(self) -> None:
        """cmd_new_deck.create_deck raises ValidationError for a size not in SIZE_MAP. Guards the
        explicit error listing the valid sizes instead of a KeyError."""
        with self.assertRaises(ValidationError):
            create_deck(self._out(), slides=1, size="21:9")


class TestCreateDeckOutput(unittest.TestCase):
    """The mapping is only correct if it lands in the saved file."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _make(self, slides: int, size: str) -> Presentation:
        out = str(Path(self.tmp.name) / "deck.pptx")
        create_deck(out, slides=slides, size=size)
        return Presentation(out)

    def test_slide_count_matches_request(self) -> None:
        """cmd_new_deck.create_deck saves exactly the requested number of slides. Guards the slide
        loop of new-deck."""
        prs = self._make(slides=4, size="16:9")
        self.assertEqual(len(prs.slides), 4)

    def test_16_9_dimensions_written(self) -> None:
        """cmd_new_deck.create_deck writes the 16:9 size from SIZE_MAP to the saved deck. Guards
        that the size mapping is applied to the presentation, not only looked up."""
        prs = self._make(slides=1, size="16:9")
        self.assertEqual(prs.slide_width, Inches(13.333))
        self.assertEqual(prs.slide_height, Inches(7.5))

    def test_slides_use_blank_layout(self) -> None:
        """cmd_new_deck.create_deck adds slides on the blank layout (index 6), which has no
        placeholders. Guards the canvas contract of new-deck for add-shapes."""
        # Blank layout (index 6) carries no placeholders.
        prs = self._make(slides=1, size="16:9")
        self.assertEqual(len(list(prs.slides[0].placeholders)), 0)


if __name__ == "__main__":
    unittest.main()
