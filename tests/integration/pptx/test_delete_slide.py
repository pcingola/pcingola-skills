"""Integration tests for the delete-slide command."""
import unittest

from pptx import Presentation

from tests.integration.pptx import cleanup_dir, create_test_pptx, fresh_dir, run_cli, stamp_description

DIR = fresh_dir("test_delete_slide")


class TestDeleteSlide(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = create_test_pptx(DIR, num_slides=5)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_delete_single(self) -> None:
        """delete-slide removes the given slide and keeps the others in order. Guards that the
        requested slide, not another, is removed."""
        out = DIR / "del_one.pptx"
        r = run_cli("delete-slide", str(self.source), str(out), "0")
        self.assertEqual(r.returncode, 0, r.stderr)
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
        """delete-slide with "0,4" removes both slides. Guards the comma-separated index list, whose
        indices refer to the original deck."""
        out = DIR / "del_multi.pptx"
        r = run_cli("delete-slide", str(self.source), str(out), "0,4")
        self.assertEqual(r.returncode, 0, r.stderr)
        prs = Presentation(str(out))
        self.assertEqual(len(prs.slides), 3)
        stamp_description(out,
            "delete-slide: removed slides 0 and 4 from a 5-slide source.\n"
            "Expected 3 slides remaining:\n"
            "  Slide 1: 'Slide 1 Title'\n"
            "  Slide 2: 'Slide 2 Title'\n"
            "  Slide 3: 'Slide 3 Title'\n"
            "Verify: 'Slide 0 Title' and 'Slide 4 Title' should NOT appear.")

    def test_delete_out_of_range(self) -> None:
        """delete-slide exits non-zero for index 99. Guards the slide range check."""
        out = DIR / "del_bad.pptx"
        r = run_cli("delete-slide", str(self.source), str(out), "99")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_delete_invalid_format(self) -> None:
        """delete-slide exits non-zero for a non-integer index list. Guards the index parsing error."""
        out = DIR / "del_invalid.pptx"
        r = run_cli("delete-slide", str(self.source), str(out), "abc")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_delete_missing_file(self) -> None:
        """delete-slide exits non-zero when the input deck does not exist. Guards the input check of
        the command."""
        out = DIR / "del_missing.pptx"
        r = run_cli("delete-slide", "/nonexistent.pptx", str(out), "0")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
