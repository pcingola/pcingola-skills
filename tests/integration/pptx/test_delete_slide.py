"""Integration tests for the delete-slide command."""
import unittest

from pptx import Presentation

from pptx_tool.cmd_delete_slide import delete_slides
from pptx_tool.exceptions import PptxError
from tests.integration.pptx import cleanup_dir, cli, create_test_pptx, fresh_dir, stamp_description

DIR = fresh_dir("test_delete_slide")


class TestDeleteSlide(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = create_test_pptx(DIR, num_slides=5)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_delete_single(self) -> None:
        """delete_slides removes the given slide and keeps the others in order. Guards that the
        requested slide, not another, is removed."""
        out = DIR / "del_one.pptx"
        result = delete_slides(self.source, out, [0])
        self.assertEqual(result.removed, [0])
        prs = Presentation(str(out))
        self.assertEqual(len(prs.slides), 4)
        self.assertIn("Slide 1 Title", prs.slides[0].shapes.title.text)
        stamp_description(out,
            "delete-slide: removed slide 0 from a 5-slide source.\n"
            "Expected 4 slides remaining:\n"
            "  Slide 1: 'Slide 1 Title' (was originally slide 1)\n"
            "  Slide 2: 'Slide 2 Title'\n"
            "  Slide 3: 'Slide 3 Title'\n"
            "  Slide 4: 'Slide 4 Title'\n"
            "Verify: 'Slide 0 Title' should NOT appear anywhere.")

    def test_delete_multiple(self) -> None:
        """delete-slide with "0,4" on the command line removes both slides. Guards the parse of the
        comma-separated index list, whose indices refer to the original deck."""
        out = DIR / "del_multi.pptx"
        r = cli("delete-slide", str(self.source), str(out), "0,4")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        prs = Presentation(str(out))
        self.assertEqual(len(prs.slides), 3)
        self.assertEqual([s.shapes.title.text for s in prs.slides],
                         ["Slide 1 Title", "Slide 2 Title", "Slide 3 Title"])
        stamp_description(out,
            "delete-slide: removed slides 0 and 4 from a 5-slide source.\n"
            "Expected 3 slides remaining:\n"
            "  Slide 1: 'Slide 1 Title'\n"
            "  Slide 2: 'Slide 2 Title'\n"
            "  Slide 3: 'Slide 3 Title'\n"
            "Verify: 'Slide 0 Title' and 'Slide 4 Title' should NOT appear.")

    def test_delete_out_of_range(self) -> None:
        """delete_slides raises PptxError for index 99 and writes no output. Guards the slide range
        check."""
        out = DIR / "del_bad.pptx"
        with self.assertRaisesRegex(PptxError, r"Slide index 99 out of range \(0-4\)"):
            delete_slides(self.source, out, [99])
        self.assertFalse(out.exists())

    def test_delete_invalid_format(self) -> None:
        """delete-slide on the command line exits 1 with the index format error on stdout for a
        non-integer index list. Guards the index parsing error and its exit code."""
        out = DIR / "del_invalid.pptx"
        r = cli("delete-slide", str(self.source), str(out), "abc")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Error: Invalid indices format", r.stdout)

    def test_delete_missing_file(self) -> None:
        """delete_slides raises PptxError when the input deck does not exist. Guards the input check
        of the command."""
        out = DIR / "del_missing.pptx"
        with self.assertRaisesRegex(PptxError, "Input file not found"):
            delete_slides(DIR / "nonexistent.pptx", out, [0])
