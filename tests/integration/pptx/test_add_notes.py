"""Integration tests for the add-notes command (and `get slide-N/notes`)."""
import unittest

from tests.integration.pptx import (
    cleanup_dir, create_test_pptx, fresh_dir, run_cli, write_text_data_json,
)

DIR = fresh_dir("test_add_notes")


class TestAddNotes(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = create_test_pptx(DIR, num_slides=3)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_multiple_slides_in_one_call(self) -> None:
        """add-notes sets notes on slide-0 and slide-2 in one call, and get slide-1/notes prints
        nothing for the untouched slide. Guards that get returns empty notes without error for a
        slide without a notes slide."""
        notes_data = {
            "slide-0": "Notes for slide 0.",
            "slide-2": "Notes for slide 2.",
        }
        notes_json = write_text_data_json(DIR, notes_data, "multi.json")
        out = DIR / "multi_out.pptx"
        r = run_cli("add-notes", str(self.source), str(notes_json), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)

        g0 = run_cli("get", str(out), "slide-0/notes")
        g2 = run_cli("get", str(out), "slide-2/notes")
        self.assertIn("Notes for slide 0.", g0.stdout)
        self.assertIn("Notes for slide 2.", g2.stdout)

        # Slide 1 was untouched — no notes slide.
        g1 = run_cli("get", str(out), "slide-1/notes")
        self.assertEqual(g1.returncode, 0, g1.stderr)
        self.assertEqual(g1.stdout.strip(), "")

    def test_does_not_disturb_slide_content(self) -> None:
        """add-notes leaves the slide's title shape text unchanged. Guards that notes are written to
        the notes slide only."""
        notes_data = {"slide-0": "Some notes."}
        notes_json = write_text_data_json(DIR, notes_data, "preserve.json")
        out = DIR / "preserve_out.pptx"
        r = run_cli("add-notes", str(self.source), str(notes_json), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)

        g = run_cli("get", str(out), "slide-0/shape-0")
        self.assertEqual(g.returncode, 0, g.stderr)
        self.assertIn("Slide 0 Title", g.stdout)

    def test_missing_input(self) -> None:
        """add-notes exits non-zero when the input deck does not exist. Guards the input check of
        the command."""
        notes_json = write_text_data_json(DIR, {}, "empty.json")
        out = DIR / "missing_input_out.pptx"
        r = run_cli("add-notes", "/nonexistent.pptx", str(notes_json), str(out))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_missing_json(self) -> None:
        """add-notes exits non-zero when the notes JSON does not exist. Guards the data file check."""
        out = DIR / "missing_json_out.pptx"
        r = run_cli("add-notes", str(self.source), "/nonexistent.json", str(out))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
