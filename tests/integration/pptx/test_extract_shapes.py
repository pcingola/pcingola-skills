"""Integration tests for the extract-shapes command."""
import json
import unittest
from pathlib import Path

from pptx_tool.cmd_extract_shapes import extract_shapes
from pptx_tool.cmd_show_shapes import show_shapes
from pptx_tool.exceptions import PptxError

from tests.integration.pptx import (
    cleanup_dir, cli, create_multilayout_pptx, create_test_pptx, fresh_dir, write_readme,
)

DIR = fresh_dir("test_extract_shapes")


class TestExtractShapes(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = create_test_pptx(DIR, num_slides=2)
        cls.multilayout = create_multilayout_pptx(DIR)
        write_readme(DIR,
            "extract-shapes: JSON output tests.\n"
            "test.pptx is the source (2 slides: 'Slide 0-1 Title').\n"
            "Expected JSON outputs:\n"
            "  shapes.json / shapes_text.json: full shape inventory\n"
            "  multilayout_shapes.json: shapes from the synthetic multi-layout deck\n"
            "  overflow_issues.json: the deliberately overlong text box on slide 3\n"
            "Each JSON has slide-N keys mapping to shape-N entries with paragraphs.")

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_extract_has_text(self) -> None:
        """extract_shapes writes a JSON whose slide-N/shape-N entries carry the slide's paragraph
        text. Guards the shape inventory format the add-text workflow reads."""
        out = DIR / "shapes_text.json"
        extract_shapes(self.source, out)
        data = json.loads(out.read_text())
        # Find a shape with our test text
        found = False
        for slide_key, shapes in data.items():
            if not slide_key.startswith("slide-"):
                continue
            for shape_key, shape_data in shapes.items():
                for para in shape_data.get("paragraphs", []):
                    if "Slide 0 Title" in para.get("text", ""):
                        found = True
        self.assertTrue(found, "Expected to find 'Slide 0 Title' in extracted shapes")

    def test_extract_issues_only_flags_overflow(self) -> None:
        """extract_shapes with issues_only reports the overlong text box of slide 3 with a frame
        overflow_bottom and includes only slides with issues. Guards the overflow detection and
        the issues-only filter."""
        out = DIR / "overflow_issues.json"
        result = extract_shapes(self.multilayout, out, issues_only=True)
        self.assertIsNotNone(result, "no issues reported")
        self.assertTrue(out.exists(), "no issues file written")
        data = json.loads(out.read_text())
        self.assertIn("slide-3", data, f"overflowing box not flagged: {list(data)}")
        overflows = [
            shape["overflow"]["frame"]["overflow_bottom"]
            for shape in data["slide-3"].values()
            if "overflow" in shape and "frame" in shape["overflow"]
        ]
        self.assertTrue(overflows, "slide-3 flagged without a frame overflow")
        # Every slide/shape present must have issues
        for slide_key, shapes in data.items():
            self.assertTrue(len(shapes) > 0, f"{slide_key} has no shapes but was included")

    def test_speaker_notes_are_surfaced(self) -> None:
        """extract_shapes adds a notes key to slide-4, which holds only a table and notes, and no
        notes key to slides without notes. Guards the past gap where notes, outside the shape
        tree, were missing from the output."""
        out = DIR / "notes.json"
        extract_shapes(self.multilayout, out)
        data = json.loads(out.read_text())
        self.assertEqual(data["slide-4"]["notes"], "Talk track: emphasise EMEA growth.")
        # Slides without notes carry no notes key.
        self.assertNotIn("notes", data["slide-0"])

    def test_issues_only_omits_notes(self) -> None:
        """extract_shapes with issues_only writes no notes keys. Guards that notes, which are
        content, do not pad the issues report."""
        out = DIR / "issues_no_notes.json"
        self.assertIsNotNone(extract_shapes(self.multilayout, out, issues_only=True))
        data = json.loads(out.read_text())
        for slide in data.values():
            self.assertNotIn("notes", slide)

    def test_cli_forwards_issues_only_and_slide(self) -> None:
        """extract-shapes on the command line with --issues-only --slide 0 writes nothing, since
        slide 0 has no issue, and with --issues-only --slide 3 writes only slide-3 with only its
        overlong text box. Guards that --issues-only and --slide reach extract_shapes."""
        clean = DIR / "cli_slide0_issues.json"
        r = cli("extract-shapes", str(self.multilayout), str(clean), "--issues-only", "--slide", "0")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("No issues discovered", r.stdout)
        self.assertFalse(clean.exists())

        out = DIR / "cli_slide3_issues.json"
        r = cli("extract-shapes", str(self.multilayout), str(out), "--issues-only", "--slide", "3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = json.loads(out.read_text())
        self.assertEqual(list(data), ["slide-3"])
        texts = [p.get("text", "") for shape in data["slide-3"].values()
                 for p in shape.get("paragraphs", [])]
        self.assertTrue(texts, "slide-3 has no shapes")
        self.assertTrue(all(t.startswith("overflowing") for t in texts), texts)

    def test_show_shapes_reads_the_augmented_json(self) -> None:
        """show_shapes reads extract_shapes output that has slide-level notes keys and includes the
        notes in its summary. Guards format_shapes skipping keys that are not shape-N."""
        out = DIR / "for_show.json"
        extract_shapes(self.multilayout, out)
        self.assertIn("Talk track", show_shapes(out))

    def test_extract_missing_file(self) -> None:
        """extract_shapes raises PptxError when the input deck does not exist. Guards the input
        check of the command."""
        out = DIR / "missing.json"
        with self.assertRaisesRegex(PptxError, "Input file '/nonexistent.pptx' not found"):
            extract_shapes(Path("/nonexistent.pptx"), out)
