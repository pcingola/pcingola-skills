"""Integration tests for the validate command."""
import json
import unittest

from pptx import Presentation
from pptx.util import Inches
from pptx_tool.cmd_validate import validate_deck

from tests.integration.pptx import (
    cleanup_dir, cli, create_multilayout_pptx, fresh_dir, write_readme,
)

DIR = fresh_dir("test_validate")


class TestValidate(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.multilayout = create_multilayout_pptx(DIR)
        write_readme(DIR, "validate: reports on the synthetic multi-layout deck and a clean deck.")

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_problems_exit_2(self) -> None:
        """The validate CLI with an output path exits 2 and writes a report listing slide-3 under
        text_issues for the deck with an overlong text box. Guards the exit code that signals
        problems, the report file mode and the text issue report."""
        out = DIR / "problems.json"
        r = cli("validate", str(self.multilayout), str(out))
        self.assertEqual(r.returncode, 2, r.stderr)
        report = json.loads(out.read_text())
        # Slide 3 carries a deliberately overlong text box.
        self.assertIn("slide-3", report["text_issues"])

    def test_empty_picture_placeholders_are_unfilled(self) -> None:
        """validate_deck lists both empty PICTURE placeholders of slide 1 as
        unfilled_visual_placeholders. Guards the unfilled picture check."""
        report = validate_deck(self.multilayout)
        pictures = [p for p in report.unfilled_visual_placeholders
                    if p.slide == 1 and p.placeholder_type == "PICTURE"]
        self.assertEqual(len(pictures), 2, report.unfilled_visual_placeholders)

    def test_object_placeholder_with_text_is_not_unfilled(self) -> None:
        """validate_deck does not report OBJECT placeholders that carry text as unfilled. Guards
        that column layouts with text count as filled."""
        report = validate_deck(self.multilayout)
        flagged = [p for p in report.unfilled_visual_placeholders if p.slide in (0, 2)]
        self.assertEqual(flagged, [])

    def test_empty_text_placeholder_is_reported(self) -> None:
        """validate_deck reports problems and lists an empty TITLE placeholder under
        empty_text_placeholders. Guards the empty text placeholder check and that it counts as a
        problem (exit code 2 in the CLI)."""
        deck = DIR / "empty_title.pptx"
        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[5])  # Title Only, title left empty
        prs.save(str(deck))
        report = validate_deck(deck)
        self.assertTrue(report.has_problems)
        self.assertEqual([p.placeholder_type for p in report.empty_text_placeholders], ["TITLE"])

    def test_clean_deck_has_no_problems(self) -> None:
        """validate_deck reports no problems and no text issues for a deck whose text fits.
        Guards against false problems on a clean deck (exit code 0 in the CLI)."""
        deck = DIR / "clean.pptx"
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank
        slide.shapes.add_textbox(Inches(1), Inches(1), Inches(6), Inches(1)).text_frame.text = "Short"
        prs.save(str(deck))
        report = validate_deck(deck)
        self.assertFalse(report.has_problems, report)
        self.assertEqual(report.text_issues, {})

    def test_stdout_when_no_output_path(self) -> None:
        """The validate CLI without an output path prints the JSON report to stdout and still exits
        2 on problems. Guards the stdout mode."""
        r = cli("validate", str(self.multilayout))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual(json.loads(r.stdout)["slide_count"], 5)

    def test_missing_input(self) -> None:
        """The validate CLI exits 1 and reports the missing file when the input deck does not
        exist. Guards the distinct exit code for errors versus problems."""
        r = cli("validate", str(DIR / "nope.pptx"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("not found", r.stderr)


if __name__ == "__main__":
    unittest.main()
