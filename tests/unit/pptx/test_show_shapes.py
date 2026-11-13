"""Unit tests for show-shapes command."""
import unittest
from argparse import Namespace

from pptx_tool.cmd_show_shapes import _first_text, _issue_flags, format_shapes, run_show_shapes


class TestFirstText(unittest.TestCase):

    def test_basic(self) -> None:
        """cmd_show_shapes._first_text returns the first paragraph's text unchanged when it is
        shorter than the preview length. Guards the preview of short text."""
        shape = {"paragraphs": [{"text": "Hello world"}]}
        self.assertEqual(_first_text(shape), "Hello world")

    def test_truncation(self) -> None:
        """cmd_show_shapes._first_text cuts text longer than TEXT_PREVIEW_LEN (60) and appends
        "...". Guards the one-line preview width of show-shapes."""
        long_text = "A" * 100
        shape = {"paragraphs": [{"text": long_text}]}
        result = _first_text(shape)
        self.assertTrue(result.endswith("..."))
        self.assertEqual(len(result), 63)  # 60 + "..."

    def test_no_paragraphs(self) -> None:
        """cmd_show_shapes._first_text returns "" for a shape without paragraphs or with an empty
        list. Guards the explicit empty branch for pictures and other shapes without text."""
        self.assertEqual(_first_text({}), "")
        self.assertEqual(_first_text({"paragraphs": []}), "")


class TestIssueFlags(unittest.TestCase):

    def test_no_issues(self) -> None:
        """cmd_show_shapes._issue_flags returns no flags for a shape without issue keys. Guards
        against false flags on clean shapes."""
        self.assertEqual(_issue_flags({}), [])

    def test_overlap(self) -> None:
        """cmd_show_shapes._issue_flags flags OVERLAP for a shape with overlapping shapes. Guards
        the mapping of extract-shapes' overlap key to its flag."""
        shape = {"overlap": {"overlapping_shapes": {"shape-1": 0.2}}}
        self.assertIn("OVERLAP", _issue_flags(shape))

    def test_multiple_flags(self) -> None:
        """cmd_show_shapes._issue_flags maps frame overflow to OVERFLOW, slide overflow to OFF-SLIDE
        and warnings to WARN, in that order. Guards the mapping of each extract-shapes issue key
        to its flag."""
        shape = {
            "overflow": {"frame": {"overflow_bottom": 0.5}, "slide": {"overflow_right": 0.1}},
            "warnings": ["something"],
        }
        self.assertEqual(_issue_flags(shape), ["OVERFLOW", "OFF-SLIDE", "WARN"])


class TestFormatShapes(unittest.TestCase):

    def test_basic_output(self) -> None:
        """cmd_show_shapes.format_shapes prints the shape count per slide, each shape's placeholder
        type (TEXT when absent) and a quoted text preview. Guards the summary format of
        show-shapes."""
        data = {
            "slide-0": {
                "shape-0": {
                    "left": 0.5,
                    "top": 0.75,
                    "width": 10.0,
                    "height": 1.2,
                    "placeholder_type": "TITLE",
                    "paragraphs": [{"text": "My Title"}],
                },
                "shape-1": {
                    "left": 0.5,
                    "top": 2.0,
                    "width": 9.0,
                    "height": 4.0,
                    "paragraphs": [{"text": "Body text here"}],
                },
            },
        }
        output = format_shapes(data)
        self.assertIn("slide-0: (2 shapes)", output)
        self.assertIn("shape-0: TITLE", output)
        self.assertIn('"My Title"', output)
        self.assertIn("shape-1: TEXT", output)
        self.assertIn('"Body text here"', output)

    def test_issue_flags_in_output(self) -> None:
        """cmd_show_shapes.format_shapes appends the issue flags in brackets to the shape line.
        Guards that detected overflow is visible in the summary."""
        data = {
            "slide-0": {
                "shape-0": {
                    "left": 0, "top": 0, "width": 5, "height": 1,
                    "paragraphs": [{"text": "Overflowing"}],
                    "overflow": {"frame": {"overflow_bottom": 0.5}},
                },
            },
        }
        output = format_shapes(data)
        self.assertIn("[OVERFLOW]", output)

    def test_empty_data(self) -> None:
        """cmd_show_shapes.format_shapes reports that no shapes were found for empty JSON. Guards
        the explicit message instead of an empty output."""
        output = format_shapes({})
        self.assertIn("No shapes", output)

    def test_missing_file_exits(self) -> None:
        """cmd_show_shapes.run_show_shapes exits with a not-found message for a missing JSON path.
        Guards the error message instead of a FileNotFoundError traceback."""
        args = Namespace(input="/nonexistent/shapes.json")
        with self.assertRaises(SystemExit) as ctx:
            run_show_shapes(args)
        self.assertIn("not found", str(ctx.exception))
