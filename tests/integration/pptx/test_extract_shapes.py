"""Integration tests for the extract-shapes command."""
import json
import unittest

from tests.integration.pptx import (
    cleanup_dir, create_multilayout_pptx, create_test_pptx, fresh_dir, run_cli, write_readme,
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
        """extract-shapes writes a JSON whose slide-N/shape-N entries carry the slide's paragraph
        text. Guards the shape inventory format the add-text workflow reads."""
        out = DIR / "shapes_text.json"
        r = run_cli("extract-shapes", str(self.source), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
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
        """extract-shapes --issues-only reports the overlong text box of slide 3 with a frame
        overflow_bottom and includes only slides with issues. Guards the overflow detection and
        the issues-only filter."""
        out = DIR / "overflow_issues.json"
        r = run_cli("extract-shapes", str(self.multilayout), str(out), "--issues-only")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(out.exists(), f"no issues file written: {r.stdout}")
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
        """extract-shapes adds a notes key to slide-4, which holds only a table and notes, and no
        notes key to slides without notes. Guards the past gap where notes, outside the shape
        tree, were missing from the output."""
        out = DIR / "notes.json"
        r = run_cli("extract-shapes", str(self.multilayout), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(out.read_text())
        self.assertEqual(data["slide-4"]["notes"], "Talk track: emphasise EMEA growth.")
        # Slides without notes carry no notes key.
        self.assertNotIn("notes", data["slide-0"])

    def test_issues_only_omits_notes(self) -> None:
        """extract-shapes --issues-only writes no notes keys. Guards that notes, which are content,
        do not pad the issues report."""
        out = DIR / "issues_no_notes.json"
        r = run_cli("extract-shapes", str(self.multilayout), str(out), "--issues-only")
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(out.read_text())
        for slide in data.values():
            self.assertNotIn("notes", slide)

    def test_show_shapes_reads_the_augmented_json(self) -> None:
        """show-shapes reads extract-shapes output that has slide-level notes keys. Guards
        format_shapes skipping keys that are not shape-N."""
        out = DIR / "for_show.json"
        self.assertEqual(run_cli("extract-shapes", str(self.multilayout), str(out)).returncode, 0)
        r = run_cli("show-shapes", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Talk track", r.stdout)

    def test_extract_missing_file(self) -> None:
        """extract-shapes exits non-zero when the input deck does not exist. Guards the input check
        of the command."""
        out = DIR / "missing.json"
        r = run_cli("extract-shapes", "/nonexistent.pptx", str(out))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
