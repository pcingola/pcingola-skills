"""Integration tests for the edit command.

Every action name is the name of a real command. The operation tests call
`apply_operations`; the spec forms (`@path`, a path of any extension, inline JSON)
are CLI behaviour and run through `cli("edit", ...)`.

`test_edit_operations_are_atomic` covers the atomic-output guarantee.
"""
import json
import unittest

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from pptx_tool.cmd_add_slide import add_slides_to_file
from pptx_tool.cmd_edit import EditError, apply_operations
from pptx_tool.cmd_new_deck import create_deck
from pptx_tool.edit_operations import EditAction
from pptx_tool.exceptions import PptxError
from tests.integration.pptx import (
    PROJECT_DIR, cleanup_dir, cli, create_multilayout_pptx, create_test_image, create_test_pptx,
    fresh_dir, stamp_description, write_readme,
)

DIR = fresh_dir("test_edit")

CHART_DATA = {"chart_type": 51,
              "data": {"categories": ["A"], "series": [{"name": "X", "values": [1]}]}}


class TestEdit(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = create_multilayout_pptx(DIR, "source.pptx")
        cls.other = create_test_pptx(DIR, name="other.pptx", num_slides=2)
        cls.image = create_test_image(DIR, "green.png", 160, 160, "green")
        write_readme(DIR,
            "edit: multi-operation specs applied atomically.\n"
            "Expected outputs:\n"
            "  chained.pptx: a copied slide, a chart, a picture and new text, one call\n"
            "No .pptx should exist for a spec that failed partway; that is the guarantee\n"
            "`edit` exists for and what test_edit_operations_are_atomic checks.")

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_add_text(self) -> None:
        """edit dispatches an add-text operation and replaces the shape text on the given slide.
        Guards the add-text action of edit."""
        out = DIR / "text.pptx"
        apply_operations(self.source, out, [{
            "action": "add-text", "slide": 0,
            "data": {"shape-0": {"paragraphs": [{"text": "Edited title", "bold": True}]}},
        }])
        slide = Presentation(str(out)).slides[0]
        self.assertTrue(any("Edited title" in s.text_frame.text
                            for s in slide.shapes if s.has_text_frame))

    def test_add_chart(self) -> None:
        """edit dispatches an add-chart operation and inserts a native chart. Guards the add-chart
        action of edit."""
        out = DIR / "chart.pptx"
        apply_operations(self.source, out, [{
            "action": "add-chart", "slide": 0,
            "data": {"chart_type": 51,
                     "data": {"categories": ["A", "B"],
                              "series": [{"name": "X", "values": [1, 2]}]}},
        }])
        slide = Presentation(str(out)).slides[0]
        self.assertTrue(any(s.shape_type == MSO_SHAPE_TYPE.CHART for s in slide.shapes))

    def test_add_notes(self) -> None:
        """edit dispatches an add-notes operation whose data is the notes string. Guards the
        add-notes action and its string data form."""
        out = DIR / "notes.pptx"
        apply_operations(self.source, out,
                         [{"action": "add-notes", "slide": 0, "data": "Remember the framing"}])
        slide = Presentation(str(out)).slides[0]
        self.assertIn("Remember the framing", slide.notes_slide.notes_text_frame.text)

    def test_add_images(self) -> None:
        """edit dispatches an add-images operation with an images list and fills a picture
        placeholder. Guards the add-images action of edit."""
        out = DIR / "image.pptx"
        apply_operations(self.source, out,
                         [{"action": "add-images", "slide": 1, "images": [str(self.image)]}])
        slide = Presentation(str(out)).slides[1]
        self.assertTrue(any(s.shape_type == MSO_SHAPE_TYPE.PICTURE for s in slide.shapes))

    def test_copy_slide_appends(self) -> None:
        """edit's copy-slide operation without position appends the source slide at the end. Guards
        the default append of the copy-slide action."""
        out = DIR / "copied.pptx"
        apply_operations(self.source, out,
                         [{"action": "copy-slide", "source": str(self.other), "source_indices": [0]}])
        prs = Presentation(str(out))
        self.assertEqual(len(prs.slides), 6)
        self.assertEqual(prs.slides[5].shapes.title.text, "Slide 0 Title")

    def test_copy_slide_at_position(self) -> None:
        """edit's copy-slide operation with position 0 inserts the slide first. Guards the position
        key of the copy-slide action."""
        out = DIR / "copied_pos.pptx"
        apply_operations(self.source, out, [{
            "action": "copy-slide", "source": str(self.other),
            "source_indices": [1], "position": 0,
        }])
        prs = Presentation(str(out))
        self.assertEqual(len(prs.slides), 6)
        self.assertEqual(prs.slides[0].shapes.title.text, "Slide 1 Title")

    def test_delete_slide(self) -> None:
        """edit dispatches a delete-slide operation with an indices list. Guards the delete-slide
        action of edit."""
        out = DIR / "deleted.pptx"
        apply_operations(self.source, out, [{"action": "delete-slide", "indices": [1]}])
        self.assertEqual(len(Presentation(str(out)).slides), 4)

    def test_chained_operations_all_land(self) -> None:
        """edit applies copy-slide, add-chart, add-images and add-notes in one call, each on the
        deck the previous operation wrote, and returns one step per operation in order. Guards the
        chaining of operations within one edit."""
        out = DIR / "chained.pptx"
        result = apply_operations(self.source, out, [
            {"action": "copy-slide", "source": str(self.other), "source_indices": [0]},
            {"action": "add-chart", "slide": 0, "data": CHART_DATA},
            {"action": "add-images", "slide": 1, "images": [str(self.image)]},
            {"action": "add-notes", "slide": 3, "data": "Closing thought"},
        ])
        self.assertEqual([s.action for s in result.steps],
                         [EditAction.COPY_SLIDE, EditAction.ADD_CHART,
                          EditAction.ADD_IMAGES, EditAction.ADD_NOTES])
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
        """edit with a spec failing at operation 2 (zero-based) raises EditError that names that
        operation and carries the two steps that ran, and writes no output. Guards the atomic
        output that edit exists for."""
        out = DIR / "atomic.pptx"
        operations = [
            {"action": "add-text", "slide": 0,
             "data": {"shape-0": {"paragraphs": [{"text": "Step 1"}]}}},
            {"action": "add-notes", "slide": 0, "data": "Step 2"},
            {"action": "add-chart", "slide": 99, "data": CHART_DATA},  # <- fails here
            {"action": "add-notes", "slide": 1, "data": "Step 4"},
            {"action": "delete-slide", "indices": [0]},
        ]
        with self.assertRaisesRegex(EditError, r"operation 2 \('add-chart'\) failed") as ctx:
            apply_operations(self.source, out, operations)
        self.assertEqual([s.index for s in ctx.exception.steps], [0, 1])
        self.assertEqual(ctx.exception.failure.index, 2)
        self.assertIsInstance(ctx.exception.failure.cause, PptxError)
        self.assertFalse(out.exists(), "a failed edit left a partial deck behind")

    def test_cli_failure_report_names_the_operation(self) -> None:
        """edit on the command line exits 1 for a spec failing at operation 2 and prints the steps
        that ran, then "operation 2" on stderr. Guards the printed failure report."""
        out = DIR / "atomic_cli.pptx"
        spec = json.dumps({"operations": [
            {"action": "add-notes", "slide": 0, "data": "Step 1"},
            {"action": "add-notes", "slide": 0, "data": "Step 2"},
            {"action": "add-chart", "slide": 99, "data": CHART_DATA},
        ]})
        r = cli("edit", str(self.source), str(out), spec)
        self.assertEqual(r.returncode, 1)
        self.assertIn("[0] add-notes", r.stdout)
        self.assertIn("[1] add-notes", r.stdout)
        self.assertIn("Error: operation 2 ('add-chart') failed", r.stderr)
        self.assertFalse(out.exists())

    def test_existing_output_survives_a_failed_edit(self) -> None:
        """edit failing on an existing output path leaves that file byte-identical. Guards against
        truncating a previous good output before the operations succeed."""
        out = DIR / "preexisting.pptx"
        apply_operations(self.source, out, [{"action": "add-notes", "slide": 0, "data": "good run"}])
        before = out.read_bytes()

        with self.assertRaises(EditError):
            apply_operations(self.source, out, [{"action": "delete-slide", "indices": [99]}])
        self.assertEqual(out.read_bytes(), before)

    def test_at_path_spec(self) -> None:
        """edit reads the spec from `@<path>` on the command line. Guards SKILL.md `edit`: a spec
        path with a leading `@`."""
        out = DIR / "at_spec.pptx"
        path = DIR / "spec.json"
        path.write_text(json.dumps({"operations": [{"action": "delete-slide", "indices": [0]}]}))
        r = cli("edit", str(self.source), str(out), f"@{path}")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(Presentation(str(out)).slides), 4)

    def test_inline_json_spec(self) -> None:
        """edit accepts the spec as inline JSON instead of @file, with indices as a string. Guards
        the inline spec form and the string indices form."""
        out = DIR / "inline.pptx"
        spec = json.dumps({"operations": [{"action": "delete-slide", "indices": "0"}]})
        r = cli("edit", str(self.source), str(out), spec)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(Presentation(str(out)).slides), 4)

    def test_spec_path_of_any_extension(self) -> None:
        """edit reads a spec file named without `.json` and without `@`. Guards SKILL.md `edit`:
        a spec not starting with `{` or `[` is the path of a JSON file of any extension."""
        out = DIR / "txt_spec.pptx"
        path = DIR / "spec.txt"
        path.write_text(json.dumps({"operations": [{"action": "delete-slide", "indices": [0]}]}))
        r = cli("edit", str(self.source), str(out), str(path))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(Presentation(str(out)).slides), 4)

    def test_missing_spec_file_errors(self) -> None:
        """edit exits 1 with "could not read spec" on stderr for a spec path that does not exist.
        Guards that a missing file is reported as such, not as a JSON parse error."""
        r = cli("edit", str(self.source), str(DIR / "none.pptx"), str(DIR / "absent.txt"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("could not read spec", r.stderr)
        self.assertIn("absent.txt", r.stderr)

    def test_skill_md_example_runs(self) -> None:
        """The `edit` example of SKILL.md ("Several operations in one call"), read from SKILL.md,
        runs on a target deck of a blank slide and a Two Content slide, with `deck.pptx` a deck
        whose slide 4 is Title and Content. Its file names are mapped into the test directory.
        Guards the example against drifting from the operation formats."""
        skill = (PROJECT_DIR / "plugins/docs/skills/pptx/SKILL.md").read_text(encoding="utf-8")
        section = skill.split("## Several operations in one call", 1)[1]
        example = section.split("```json\n", 1)[1].split("```", 1)[0]
        source, target = DIR / "deck.pptx", DIR / "example_in.pptx"
        for path, layouts in ((source, ["Title Slide", "Title Slide", "Title Slide", "Title and Content"]),
                              (target, ["Two Content"])):
            create_deck(path, slides=1, size="16:9")
            add_slides_to_file(path, path, layouts, None)
        for name in ("a.png", "b.png"):
            create_test_image(DIR, name, 80, 80, "blue")
        for name in ("deck.pptx", "a.png", "b.png"):
            example = example.replace(f'"{name}"', json.dumps(str(DIR / name)))
        out = DIR / "example_out.pptx"
        apply_operations(target, out, json.loads(example)["operations"])
        slides = Presentation(str(out)).slides
        self.assertTrue(any(s.shape_type == MSO_SHAPE_TYPE.CHART for s in slides[1].shapes))
        self.assertEqual(sum(s.shape_type == MSO_SHAPE_TYPE.PICTURE for s in slides[2].shapes), 2)

    def test_missing_input_errors(self) -> None:
        """edit raises PptxError when the input deck does not exist. Guards the input check of the
        command."""
        with self.assertRaisesRegex(PptxError, "Input deck not found"):
            apply_operations(DIR / "nonexistent.pptx", DIR / "x.pptx",
                             [{"action": "delete-slide", "indices": [0]}])

    def test_unknown_action_errors_and_names_the_valid_ones(self) -> None:
        """edit raises EditError for an unknown action, with a message that lists the valid
        actions. Guards the action check and its message."""
        with self.assertRaisesRegex(EditError, "Unknown action 'nonsense'") as ctx:
            apply_operations(self.source, DIR / "x.pptx", [{"action": "nonsense"}])
        self.assertIn("add-chart", str(ctx.exception))

    def test_empty_operations_errors(self) -> None:
        """edit raises PptxError for a spec with no operations. Guards against writing an unchanged
        copy as a successful edit."""
        out = DIR / "empty.pptx"
        with self.assertRaisesRegex(PptxError, "'operations' list is empty"):
            apply_operations(self.source, out, [])
        self.assertFalse(out.exists())

    def test_missing_required_key_errors(self) -> None:
        """edit raises EditError whose cause is the ValueError "requires 'data'" for an add-chart
        operation without data, raised before the command runs. Guards the per-action required-key
        check."""
        with self.assertRaises(EditError) as ctx:
            apply_operations(self.source, DIR / "x.pptx", [{"action": "add-chart", "slide": 0}])
        failure = ctx.exception.failure
        self.assertIsInstance(failure.cause, ValueError)
        self.assertIn("requires 'data'", str(failure.cause))
        self.assertFalse(failure.command_ran)
