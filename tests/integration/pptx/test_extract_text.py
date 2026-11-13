"""Integration tests for the extract-text command.

`extract-text` shipped with no coverage in either tier. It is the flat one-line-
per-paragraph dump the SKILL.md tells you to reach for first, and the only reader
small enough to survive a read-truncation limit on a large deck — so text that
silently goes missing here is text nobody checks.
"""
import json
import unittest

from tests.integration.pptx import (
    cleanup_dir, create_multilayout_pptx, create_test_pptx, fresh_dir, run_cli, write_readme,
)

DIR = fresh_dir("test_extract_text")


class TestExtractText(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = create_test_pptx(DIR, num_slides=3)
        cls.multilayout = create_multilayout_pptx(DIR)
        write_readme(DIR,
            "extract-text: flat one-paragraph-per-line dumps.\n"
            "Expected outputs:\n"
            "  dump.txt   — every paragraph of test.pptx, prefixed S01/S02/S03\n"
            "  dump.json  — the same records as a JSON array\n"
            "Table cell text must appear with a TABLE[r,c] shape label.")

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_stdout_has_one_line_per_paragraph(self) -> None:
        """extract-text prints one line per paragraph, prefixed S01 and carrying the layout name.
        Guards the flat dump format SKILL.md names as the first reader."""
        r = run_cli("extract-text", str(self.source))
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
        # 3 slides x (title + body)
        self.assertEqual(len(lines), 6)
        self.assertTrue(lines[0].startswith("S01"))
        self.assertIn("Slide 0 Title", lines[0])
        self.assertIn("Title and Content", lines[0])  # layout name column

    def test_output_file(self) -> None:
        """extract-text -o writes the dump to the file and reports the paragraph count. Guards the
        file output mode."""
        out = DIR / "dump.txt"
        r = run_cli("extract-text", str(self.source), "-o", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Wrote 6 paragraphs", r.stdout)
        self.assertEqual(len([ln for ln in out.read_text().splitlines() if ln.strip()]), 6)

    def test_json_mode(self) -> None:
        """extract-text --json writes records with exactly slide, layout, shape and text, slide
        1-based. Guards the JSON record format and its slide numbering."""
        out = DIR / "dump.json"
        r = run_cli("extract-text", str(self.source), "--json", "-o", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        records = json.loads(out.read_text())
        self.assertEqual(len(records), 6)
        self.assertEqual(set(records[0]), {"slide", "layout", "shape", "text"})
        self.assertEqual(records[0]["slide"], 1)  # 1-based in the dump

    def test_single_slide_filter(self) -> None:
        """extract-text --slide 1 returns only records of the second slide (slide 2 in the 1-based
        dump). Guards the 0-based filter against the 1-based output."""
        r = run_cli("extract-text", str(self.source), "--slide", "1", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        records = json.loads(r.stdout)
        self.assertTrue(records)
        self.assertEqual({rec["slide"] for rec in records}, {2})

    def test_table_cells_are_dumped(self) -> None:
        """extract-text dumps each table cell as a record with a TABLE[r,c] shape label. Guards that
        text inside GraphicFrame tables is not lost."""
        r = run_cli("extract-text", str(self.multilayout), "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        records = json.loads(r.stdout)
        table_rows = [rec for rec in records if rec["shape"].startswith("TABLE[")]
        self.assertEqual(
            sorted(rec["text"] for rec in table_rows),
            ["$45M", "EMEA", "Region", "Revenue"],
        )

    def test_missing_file(self) -> None:
        """extract-text exits non-zero when the input deck does not exist. Guards the input check of
        the command."""
        r = run_cli("extract-text", "/nonexistent.pptx")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
