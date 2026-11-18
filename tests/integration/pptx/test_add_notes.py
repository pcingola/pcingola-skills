"""Integration tests for the add-notes command (and `get slide-N/notes`).

The tests call the core functions `PresentationNotesSetter.add_notes` and `get_text`. The test
of the notes data file check calls the CLI in process, because the CLI layer loads that file.
"""
import unittest
from pathlib import Path

from pptx_tool.cmd_add_notes import PresentationNotesSetter
from pptx_tool.cmd_get import get_text
from pptx_tool.exceptions import PptxError
from tests.integration.pptx import cleanup_dir, cli, create_test_pptx, fresh_dir

DIR = fresh_dir("test_add_notes")


class TestAddNotes(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = create_test_pptx(DIR, num_slides=3)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_multiple_slides_in_one_call(self) -> None:
        """add_notes sets notes on slide-0 and slide-2 in one call and reports both slide keys, and
        get_text of slide-1/notes returns nothing for the untouched slide. Guards that get returns empty notes without error for a
        slide without a notes slide."""
        notes_data = {
            "slide-0": "Notes for slide 0.",
            "slide-2": "Notes for slide 2.",
        }
        out = DIR / "multi_out.pptx"
        result = PresentationNotesSetter().add_notes(self.source, notes_data, out)
        self.assertEqual(result.slide_keys, ["slide-0", "slide-2"])

        self.assertIn("Notes for slide 0.", "\n".join(get_text(out, "slide-0/notes")))
        self.assertIn("Notes for slide 2.", "\n".join(get_text(out, "slide-2/notes")))

        # Slide 1 was untouched, so it has no notes slide.
        self.assertEqual(get_text(out, "slide-1/notes"), [])

    def test_does_not_disturb_slide_content(self) -> None:
        """add_notes leaves the slide's title shape text unchanged. Guards that notes are written to
        the notes slide only."""
        notes_data = {"slide-0": "Some notes."}
        out = DIR / "preserve_out.pptx"
        PresentationNotesSetter().add_notes(self.source, notes_data, out)

        self.assertIn("Slide 0 Title", "\n".join(get_text(out, "slide-0/shape-0")))

    def test_missing_input(self) -> None:
        """add_notes raises PptxError naming the input deck when it does not exist. Guards the input
        check of the command."""
        out = DIR / "missing_input_out.pptx"
        with self.assertRaisesRegex(PptxError, "Input file '/nonexistent.pptx' not found"):
            PresentationNotesSetter().add_notes(Path("/nonexistent.pptx"), {}, out)
        self.assertFalse(out.exists())

    def test_missing_json(self) -> None:
        """The add-notes CLI exits with 1 and prints the not-found error when the notes data JSON
        does not exist. Guards the data file check of the CLI layer, which loads the file."""
        out = DIR / "missing_json_out.pptx"
        r = cli("add-notes", str(self.source), "/nonexistent.json", str(out))
        self.assertEqual(r.returncode, 1)
        self.assertIn("Error: Notes data JSON file '/nonexistent.json' not found", r.stdout)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
