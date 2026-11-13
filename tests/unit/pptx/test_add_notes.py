"""Unit tests for add-notes.

Focus is the command's own logic: the duplicate-key guard, the slide-range
and value-type validation rules, and that notes text lands correctly (split
into paragraphs on newlines) without disturbing slide content.
"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from pptx import Presentation
from pptx.enum.text import PP_ALIGN

from pptx_tool.cmd_add_notes import PresentationNotesSetter
from pptx_tool.cmd_new_deck import create_deck
from pptx_tool.exceptions import ValidationError


class TestDuplicateKeyGuard(unittest.TestCase):

    def test_duplicate_key_rejected(self) -> None:
        """cmd_add_notes.PresentationNotesSetter._check_duplicate_keys raises ValidationError when
        the notes JSON repeats a slide key. Guards against json.load silently keeping only the
        last value of a duplicate key."""
        pairs = [("slide-0", "a"), ("slide-0", "b")]
        with self.assertRaises(ValidationError):
            PresentationNotesSetter._check_duplicate_keys(pairs)

    def test_unique_keys_ok(self) -> None:
        """PresentationNotesSetter._check_duplicate_keys returns the pairs as a dict when the keys
        are unique. Guards that the object_pairs_hook keeps every entry of a valid notes file."""
        pairs = [("slide-0", "a"), ("slide-1", "b")]
        result = PresentationNotesSetter._check_duplicate_keys(pairs)
        self.assertEqual(result, {"slide-0": "a", "slide-1": "b"})


class TestValidation(unittest.TestCase):
    """Two-slide deck (indices 0-1); everything else should be rejected."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        deck = str(Path(self.tmp.name) / "in.pptx")
        create_deck(deck, slides=2, size="16:9")
        self.prs = Presentation(deck)
        self.setter = PresentationNotesSetter()

    def _err(self, data: dict) -> str:
        with self.assertRaises(ValidationError) as ctx:
            self.setter._validate_notes_data(self.prs, data)
        return str(ctx.exception)

    def test_non_slide_key_rejected(self) -> None:
        """PresentationNotesSetter._validate_notes_data rejects a key that does not start with
        slide-. Guards the slide-N key format of the notes JSON."""
        self._err({"sheet-0": "text"})

    def test_out_of_range_slide_rejected(self) -> None:
        """PresentationNotesSetter._validate_notes_data rejects slide-5 on a two-slide deck. Guards
        the slide index range check before any write."""
        self._err({"slide-5": "text"})

    def test_negative_slide_rejected(self) -> None:
        """PresentationNotesSetter._validate_notes_data rejects slide--1, whose index does not
        parse. Guards the invalid-key branch against a negative index reaching the slide list."""
        self._err({"slide--1": "text"})

    def test_non_string_value_error_names_type(self) -> None:
        """PresentationNotesSetter._validate_notes_data rejects a non-string value and prints that
        it must be a string with the type name. Guards the error message for notes given as
        numbers or lists."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self._err({"slide-0": 42})
        self.assertIn("must be a string", buf.getvalue())
        self.assertIn("int", buf.getvalue())


class TestApply(unittest.TestCase):
    """Set notes via the JSON entry point, reopen the deck, assert the text landed."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.deck = str(Path(self.tmp.name) / "in.pptx")
        create_deck(self.deck, slides=3, size="16:9")

    def _build(self, notes: dict) -> Presentation:
        data_path = str(Path(self.tmp.name) / "notes.json")
        out = str(Path(self.tmp.name) / "out.pptx")
        with open(data_path, "w") as f:
            json.dump(notes, f)
        PresentationNotesSetter().add_notes(self.deck, data_path, out)
        return Presentation(out)

    def test_multi_paragraph_notes_split_on_newline(self) -> None:
        """PresentationNotesSetter.add_notes splits notes text on newlines into separate paragraphs.
        Guards the paragraph split of add-notes."""
        prs = self._build({"slide-0": "First paragraph.\nSecond paragraph."})
        tf = prs.slides[0].notes_slide.notes_text_frame
        self.assertEqual(len(tf.paragraphs), 2)
        self.assertEqual(tf.paragraphs[0].text, "First paragraph.")
        self.assertEqual(tf.paragraphs[1].text, "Second paragraph.")

    def test_rerun_drops_stale_paragraph_formatting(self) -> None:
        """PresentationNotesSetter.add_notes on a slide with centred notes writes the new text
        without the old alignment. Guards the removal of the first paragraph's pPr, which
        tf.clear() keeps."""
        # tf.clear() preserves the retained first paragraph's <a:pPr> (alignment,
        # indent, bullet); a second add-notes call must not inherit it.
        prs = Presentation(self.deck)
        notes_tf = prs.slides[0].notes_slide.notes_text_frame
        notes_tf.text = "Old, centered note."
        notes_tf.paragraphs[0].alignment = PP_ALIGN.CENTER
        prs.save(self.deck)

        prs = self._build({"slide-0": "New note."})
        paragraph = prs.slides[0].notes_slide.notes_text_frame.paragraphs[0]
        self.assertEqual(paragraph.text, "New note.")
        self.assertIsNone(paragraph.alignment)

    def test_multiple_slides_in_one_call(self) -> None:
        """PresentationNotesSetter.add_notes sets notes on each listed slide in one call and creates
        no notes slide on unlisted slides. Guards that only the requested slides are changed."""
        prs = self._build({"slide-0": "Notes for 0.", "slide-2": "Notes for 2."})
        self.assertEqual(prs.slides[0].notes_slide.notes_text_frame.text, "Notes for 0.")
        self.assertFalse(prs.slides[1].has_notes_slide)
        self.assertEqual(prs.slides[2].notes_slide.notes_text_frame.text, "Notes for 2.")


if __name__ == "__main__":
    unittest.main()
