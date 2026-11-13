"""Integration tests for the select-slides command."""
import unittest

from pptx import Presentation

from tests.integration.pptx import (
    cleanup_dir, create_multilayout_pptx, create_test_pptx, fresh_dir, run_cli, stamp_description,
)

DIR = fresh_dir("test_select_slides")


class TestSelectSlides(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = create_test_pptx(DIR, num_slides=5)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_reorder_slides(self) -> None:
        """select-slides "4,2,0" writes the slides in the given order. Guards that the sequence
        order, not the source order, decides the output order."""
        out = DIR / "reordered.pptx"
        r = run_cli("select-slides", str(self.source), str(out), "4,2,0")
        self.assertEqual(r.returncode, 0, r.stderr)
        prs = Presentation(str(out))
        self.assertEqual(len(prs.slides), 3)
        titles = [slide.shapes.title.text for slide in prs.slides if slide.shapes.title]
        self.assertEqual(titles, ["Slide 4 Title", "Slide 2 Title", "Slide 0 Title"])
        stamp_description(out,
            "select-slides: reverse order 4, 2, 0 from a 5-slide source.\n"
            "Expected 3 slides in reverse order:\n"
            "  Slide 1: 'Slide 4 Title'\n"
            "  Slide 2: 'Slide 2 Title'\n"
            "  Slide 3: 'Slide 0 Title'")

    def test_out_of_range(self) -> None:
        """select-slides exits non-zero when the sequence names slide 99. Guards the index range
        check before the deck is built."""
        out = DIR / "bad_range.pptx"
        r = run_cli("select-slides", str(self.source), str(out), "0,99")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_invalid_sequence(self) -> None:
        """select-slides exits non-zero for a non-integer sequence. Guards the parse_sequence error
        reaching the exit code."""
        out = DIR / "bad_seq.pptx"
        r = run_cli("select-slides", str(self.source), str(out), "abc")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_with_multilayout_deck(self) -> None:
        """select-slides keeps each selected slide's layout from a deck with different layouts.
        Guards that slides are kept on their own layouts, not rebased on one."""
        source = create_multilayout_pptx(DIR)
        out = DIR / "from_multilayout.pptx"
        r = run_cli("select-slides", str(source), str(out), "0,1,2")
        self.assertEqual(r.returncode, 0, r.stderr)
        prs = Presentation(str(out))
        self.assertEqual(len(prs.slides), 3)
        self.assertEqual(
            [s.slide_layout.name for s in prs.slides],
            ["Title and Content", "Picture with Caption", "Two Content"],
        )
        stamp_description(out,
            "select-slides: first 3 slides of the synthetic multi-layout deck.\n"
            "Expected 3 slides with their original layouts and styling preserved.")

    def test_missing_template(self) -> None:
        """select-slides exits non-zero when the template deck does not exist. Guards the input
        check of the command."""
        out = DIR / "missing.pptx"
        r = run_cli("select-slides", "/nonexistent.pptx", str(out), "0")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
