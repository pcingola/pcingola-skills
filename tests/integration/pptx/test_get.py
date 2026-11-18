"""Integration tests for the get command."""
import unittest
from pathlib import Path

from pptx_tool.cmd_get import get_text
from pptx_tool.exceptions import PptxError

from tests.integration.pptx import cleanup_dir, create_test_pptx, fresh_dir, write_readme

DIR = fresh_dir("test_get")


class TestGet(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = create_test_pptx(DIR, num_slides=3)
        write_readme(DIR,
            "get: stdout-only tests, no output files to inspect.\n"
            "test.pptx is the source (3 slides: 'Slide 0-2 Title').\n"
            "The get command prints a single shape's text content.")

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_get_title(self) -> None:
        """get_text on slide-0/shape-0 returns that shape's text. Guards the slide-N/shape-N path
        resolution of get."""
        self.assertIn("Slide 0 Title", get_text(self.source, "slide-0/shape-0"))

    def test_get_invalid_path_format(self) -> None:
        """get_text raises PptxError naming the expected format for a path that is not
        slide-N/shape-N. Guards the path format check."""
        with self.assertRaisesRegex(PptxError, "Invalid path 'bad-path'. Expected format"):
            get_text(self.source, "bad-path")

    def test_get_nonexistent_slide(self) -> None:
        """get_text raises PptxError for slide-99 of a 3-slide deck. Guards the slide range
        check."""
        with self.assertRaisesRegex(PptxError, "slide-99 not found"):
            get_text(self.source, "slide-99/shape-0")

    def test_get_nonexistent_shape(self) -> None:
        """get_text raises PptxError for shape-99 of slide-0. Guards the shape range check."""
        with self.assertRaisesRegex(PptxError, "shape-99 not found on slide-0"):
            get_text(self.source, "slide-0/shape-99")

    def test_get_missing_file(self) -> None:
        """get_text raises PptxError when the input deck does not exist. Guards the input check of
        the command."""
        with self.assertRaisesRegex(PptxError, "Input file not found"):
            get_text(Path("/nonexistent.pptx"), "slide-0/shape-0")
