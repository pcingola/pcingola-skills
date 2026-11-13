"""Integration tests for the edit command.

Every action name is the name of a real command.

`test_edit_operations_are_atomic` covers the atomic-output guarantee.
"""
import json
import unittest

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from tests.integration.pptx import (
    cleanup_dir, create_multilayout_pptx, create_test_image, create_test_pptx,
    fresh_dir, run_cli, stamp_description, write_readme,
)

DIR = fresh_dir("test_edit")


def _spec(name: str, *operations: dict) -> str:
    path = DIR / name
    path.write_text(json.dumps({"operations": list(operations)}))
    return f"@{path}"


class TestEdit(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = create_multilayout_pptx(DIR, "source.pptx")
        cls.other = create_test_pptx(DIR, name="other.pptx", num_slides=2)
        cls.image = create_test_image(DIR, "green.png", 160, 160, "green")
        write_readme(DIR,
            "edit: multi-operation specs applied atomically.\n"
            "Expected outputs:\n"
            "  chained.pptx — a copied slide, a chart, a picture and new text, one call\n"
            "No .pptx should exist for a spec that failed partway; that is the guarantee\n"
            "`edit` exists for and what test_edit_operations_are_atomic checks.")

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_add_text(self) -> None:
        """edit dispatches an add-text operation and replaces the shape text on the given slide.
        Guards the add-text action of edit."""
        out = DIR / "text.pptx"
        spec = _spec("text.json", {
            "action": "add-text", "slide": 0,
            "data": {"shape-0": {"paragraphs": [{"text": "Edited title", "bold": True}]}},
        })
        r = run_cli("edit", str(self.source), str(out), spec)
        self.assertEqual(r.returncode, 0, r.stderr)
        slide = Presentation(str(out)).slides[0]
        self.assertTrue(any("Edited title" in s.text_frame.text
                            for s in slide.shapes if s.has_text_frame))

    def test_add_chart(self) -> None:
        """edit dispatches an add-chart operation and inserts a native chart. Guards the add-chart
        action of edit."""
        out = DIR / "chart.pptx"
        spec = _spec("chart.json", {
            "action": "add-chart", "slide": 0,
            "data": {"chart_type": 51,
                     "data": {"categories": ["A", "B"],
                              "series": [{"name": "X", "values": [1, 2]}]}},
        })
        r = run_cli("edit", str(self.source), str(out), spec)
        self.assertEqual(r.returncode, 0, r.stderr)
        slide = Presentation(str(out)).slides[0]
        self.assertTrue(any(s.shape_type == MSO_SHAPE_TYPE.CHART for s in slide.shapes))

    def test_add_notes(self) -> None:
        """edit dispatches an add-notes operation whose data is the notes string. Guards the
        add-notes action and its string data form."""
        out = DIR / "notes.pptx"
        spec = _spec("notes.json",
                     {"action": "add-notes", "slide": 0, "data": "Remember the framing"})
        r = run_cli("edit", str(self.source), str(out), spec)
        self.assertEqual(r.returncode, 0, r.stderr)
        slide = Presentation(str(out)).slides[0]
        self.assertIn("Remember the framing", slide.notes_slide.notes_text_frame.text)

    def test_add_images(self) -> None:
        """edit dispatches an add-images operation with an images list and fills a picture
        placeholder. Guards the add-images action of edit."""
        out = DIR / "image.pptx"
        spec = _spec("image.json",
                     {"action": "add-images", "slide": 1, "images": [str(DIR / "green.png")]})
        r = run_cli("edit", str(self.source), str(out), spec)
        self.assertEqual(r.returncode, 0, r.stderr)
        slide = Presentation(str(out)).slides[1]
        self.assertTrue(any(s.shape_type == MSO_SHAPE_TYPE.PICTURE for s in slide.shapes))

    def test_copy_slide_appends(self) -> None:
        """edit's copy-slide operation without position appends the source slide at the end. Guards
        the default append of the copy-slide action."""
        out = DIR / "copied.pptx"
        spec = _spec("copy.json",
                     {"action": "copy-slide", "source": str(self.other), "source_indices": [0]})
        r = run_cli("edit", str(self.source), str(out), spec)
        self.assertEqual(r.returncode, 0, r.stderr)
        prs = Presentation(str(out))
        self.assertEqual(len(prs.slides), 6)
        self.assertEqual(prs.slides[5].shapes.title.text, "Slide 0 Title")

    def test_copy_slide_at_position(self) -> None:
        """edit's copy-slide operation with position 0 inserts the slide first. Guards the position
        key of the copy-slide action."""
        out = DIR / "copied_pos.pptx"
        spec = _spec("copy_pos.json", {
            "action": "copy-slide", "source": str(self.other),
            "source_indices": [1], "position": 0,
        })
        r = run_cli("edit", str(self.source), str(out), spec)
        self.assertEqual(r.returncode, 0, r.stderr)
        prs = Presentation(str(out))
        self.assertEqual(len(prs.slides), 6)
        self.assertEqual(prs.slides[0].shapes.title.text, "Slide 1 Title")

    def test_delete_slide(self) -> None:
        """edit dispatches a delete-slide operation with an indices list. Guards the delete-slide
        action of edit."""
        out = DIR / "deleted.pptx"
        spec = _spec("delete.json", {"action": "delete-slide", "indices": [1]})
        r = run_cli("edit", str(self.source), str(out), spec)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(Presentation(str(out)).slides), 4)

    def test_chained_operations_all_land(self) -> None:
        """edit applies copy-slide, add-chart, add-images and add-notes in one call, each on the
        deck the previous operation wrote. Guards the chaining of operations within one edit."""
        out = DIR / "chained.pptx"
        spec = _spec("chained.json",
            {"action": "copy-slide", "source": str(self.other), "source_indices": [0]},
            {"action": "add-chart", "slide": 0,
             "data": {"chart_type": 51,
                      "data": {"categories": ["A"], "series": [{"name": "X", "values": [1]}]}}},
            {"action": "add-images", "slide": 1, "images": [str(DIR / "green.png")]},
            {"action": "add-notes", "slide": 3, "data": "Closing thought"},
        )
        r = run_cli("edit", str(self.source), str(out), spec)
        self.assertEqual(r.returncode, 0, r.stderr)
        prs = Presentation(str(out))
        self.assertEqual(len(prs.slides), 6)
        self.assertTrue(any(s.shape_type == MSO_SHAPE_TYPE.CHART for s in prs.slides[0].shapes))
        self.assertTrue(any(s.shape_type == MSO_SHAPE_TYPE.PICTURE for s in prs.slides[1].shapes))
        self.assertIn("Closing thought", prs.slides[3].notes_slide.notes_text_frame.text)
        stamp_description(out,
            "edit: four operations in one atomic call.\n"
            "Expected: a copied slide at the end, a column chart on slide 1,\n"
            "a green picture on slide 2, and speaker notes on slide 4.")

    def test_edit_operations_are_atomic(self) -> None:
        """edit with a spec failing at operation 2 (zero-based) exits non-zero, names that operation
        and writes no output. Guards the atomic output that edit exists for."""
        out = DIR / "atomic.pptx"
        spec = _spec("atomic.json",
            {"action": "add-text", "slide": 0,
             "data": {"shape-0": {"paragraphs": [{"text": "Step 1"}]}}},
            {"action": "add-notes", "slide": 0, "data": "Step 2"},
            {"action": "add-chart", "slide": 99,          # <- fails here
             "data": {"chart_type": 51,
                      "data": {"categories": ["A"], "series": [{"name": "X", "values": [1]}]}}},
            {"action": "add-notes", "slide": 1, "data": "Step 4"},
            {"action": "delete-slide", "indices": [0]},
        )
        r = run_cli("edit", str(self.source), str(out), spec)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        self.assertIn("operation 2", r.stderr)
        self.assertFalse(out.exists(), "a failed edit left a partial deck behind")

    def test_existing_output_survives_a_failed_edit(self) -> None:
        """edit failing on an existing output path leaves that file byte-identical. Guards against
        truncating a previous good output before the operations succeed."""
        out = DIR / "preexisting.pptx"
        ok = _spec("ok.json", {"action": "add-notes", "slide": 0, "data": "good run"})
        self.assertEqual(run_cli("edit", str(self.source), str(out), ok).returncode, 0)
        before = out.read_bytes()

        bad = _spec("bad.json", {"action": "delete-slide", "indices": [99]})
        self.assertNotEqual(run_cli("edit", str(self.source), str(out), bad).returncode, 0)
        self.assertEqual(out.read_bytes(), before)

    def test_inline_json_spec(self) -> None:
        """edit accepts the spec as inline JSON instead of @file, with indices as a string. Guards
        the inline spec form and the string indices form."""
        out = DIR / "inline.pptx"
        spec = json.dumps({"operations": [{"action": "delete-slide", "indices": "0"}]})
        r = run_cli("edit", str(self.source), str(out), spec)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(Presentation(str(out)).slides), 4)

    def test_missing_input_errors(self) -> None:
        """edit exits non-zero when the input deck does not exist. Guards the input check of the
        command."""
        spec = _spec("nope.json", {"action": "delete-slide", "indices": [0]})
        r = run_cli("edit", "/nonexistent.pptx", str(DIR / "x.pptx"), spec)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_unknown_action_errors_and_names_the_valid_ones(self) -> None:
        """edit exits non-zero for an unknown action and lists the valid actions. Guards the action
        check and its message."""
        spec = _spec("unknown.json", {"action": "nonsense"})
        r = run_cli("edit", str(self.source), str(DIR / "x.pptx"), spec)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        self.assertIn("Unknown action", r.stderr)
        self.assertIn("add-chart", r.stderr)

    def test_empty_operations_errors(self) -> None:
        """edit exits non-zero for a spec with no operations. Guards against writing an unchanged
        copy as a successful edit."""
        spec = _spec("empty.json")
        r = run_cli("edit", str(self.source), str(DIR / "x.pptx"), spec)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_missing_required_key_errors(self) -> None:
        """edit exits non-zero with "requires 'data'" for an add-chart operation without data.
        Guards the per-action required-key check."""
        spec = _spec("no_data.json", {"action": "add-chart", "slide": 0})
        r = run_cli("edit", str(self.source), str(DIR / "x.pptx"), spec)
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        self.assertIn("requires 'data'", r.stderr)
