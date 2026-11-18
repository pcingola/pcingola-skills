"""Integration tests for the extract-text command.

`extract-text` shipped with no coverage in either tier. It is the flat one-line-
per-paragraph dump the SKILL.md tells you to reach for first, and the only reader
small enough to survive a read-truncation limit on a large deck — so text that
silently goes missing here is text nobody checks.
"""
import json
import unittest
from pathlib import Path

from pptx_tool.cmd_check_text import extract_paragraphs, format_paragraphs
from pptx_tool.exceptions import PptxError

from tests.integration.pptx import (
    cleanup_dir, cli, create_multilayout_pptx, create_test_pptx, fresh_dir, write_readme,
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
            "  dump.txt   — every paragraph of test.pptx, prefixed S00/S01/S02\n"
            "  dump.json  — the same records as a JSON array\n"
            "Table cell text must appear with a TABLE[r,c] shape label.")

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_text_has_one_line_per_paragraph(self) -> None:
        """format_paragraphs gives one line per paragraph of extract_paragraphs, prefixed S00 and
        carrying the layout name. Guards the flat dump format SKILL.md names as the first
        reader."""
        text = format_paragraphs(extract_paragraphs(self.source), as_json=False)
        lines = [ln for ln in text.splitlines() if ln.strip()]
        # 3 slides x (title + body)
        self.assertEqual(len(lines), 6)
        self.assertTrue(lines[0].startswith("S00"))
        self.assertIn("Slide 0 Title", lines[0])
        self.assertIn("Title and Content", lines[0])  # layout name column

    def test_output_file(self) -> None:
        """The extract-text CLI with -o writes the dump to the file and reports the paragraph
        count. Guards the file output mode, which lives in the CLI layer."""
        out = DIR / "dump.txt"
        r = cli("extract-text", str(self.source), "-o", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Wrote 6 paragraphs", r.stdout)
        self.assertEqual(len([ln for ln in out.read_text().splitlines() if ln.strip()]), 6)

    def test_json_mode(self) -> None:
        """The extract-text CLI with --json -o writes records with exactly slide, layout, shape and
        text, slide 0-based like every slide index of the tool. Guards the JSON record format, its
        slide numbering and the JSON file mode."""
        out = DIR / "dump.json"
        r = cli("extract-text", str(self.source), "--json", "-o", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        records = json.loads(out.read_text())
        self.assertEqual(len(records), 6)
        self.assertEqual(set(records[0]), {"slide", "layout", "shape", "text"})
        self.assertEqual(records[0]["slide"], 0)

    def test_single_slide_filter(self) -> None:
        """extract_paragraphs with slide=1 returns only paragraphs of the second slide, numbered 1
        in the JSON output. Guards that the filter and the output use the same 0-based index."""
        records = json.loads(format_paragraphs(extract_paragraphs(self.source, slide=1), as_json=True))
        self.assertTrue(records)
        self.assertEqual({rec["slide"] for rec in records}, {1})

    def test_table_cells_are_dumped(self) -> None:
        """extract_paragraphs returns each table cell as a paragraph with a TABLE[r,c] shape label.
        Guards that text inside GraphicFrame tables is not lost."""
        table_rows = [p for p in extract_paragraphs(self.multilayout) if p.shape.startswith("TABLE[")]
        self.assertEqual(
            sorted(p.text for p in table_rows),
            ["$45M", "EMEA", "Region", "Revenue"],
        )

    def test_missing_file(self) -> None:
        """extract_paragraphs raises PptxError when the input deck does not exist. Guards the input
        check of the command."""
        with self.assertRaisesRegex(PptxError, "'/nonexistent.pptx' not found"):
            extract_paragraphs(Path("/nonexistent.pptx"))
