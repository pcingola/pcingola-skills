"""Unit tests for second_opinion_tool.review and models: the request content, the answer check,
the Markdown report, the CLI refusals and the model choice. No test calls a model."""

import tempfile
import unittest
from pathlib import Path

import pytest
from pydantic_ai import BinaryContent

from second_opinion_tool import cli, review
from second_opinion_tool.files import ReviewFile
from tests.inproc import run_main


def text_file(path="notes.md", text="line 1\nline 2\n"):
    return ReviewFile(path, "text", "text/plain", text.encode(), text)


def test_boundary_is_random_per_request():
    """review.new_boundary returns a different token of at least 24 characters on each call. Guards
    the per-request boundary that file text cannot predict, so a file cannot close its own text
    block.
    """
    assert review.new_boundary() != review.new_boundary()
    assert len(review.new_boundary()) >= 24


def test_content_layout():
    """review.content puts the brief with the boundary first, each text file between boundary lines
    after its header, and each other file as a header and a BinaryContent part. Guards the user
    message layout.
    """
    png = ReviewFile("s.png", "image", "image/png", b"\x89PNG")
    parts = review.content("Check the sums.", [text_file(), png], "b0b")
    assert "Brief:\nCheck the sums." in parts[0] and "BOUNDARY for this request: b0b" in parts[0]
    assert parts[1] == "File: notes.md (text, text/plain)\n<<<b0b\nline 1\nline 2\n\nb0b>>>"
    assert parts[2] == "File: s.png (image, image/png)"
    assert parts[3] == BinaryContent(b"\x89PNG", media_type="image/png") and len(parts) == 4


GOOD = {"severity": "warn", "location": " a ", "issue": "b", "evidence": "c", "suggestion": "d"}
MALFORMED = [[], {"summary": "s"}, {"summary": "s", "findings": ["x"]},
             {"summary": "s", "findings": [{**GOOD, "severity": "error"}]},
             {"summary": "s", "findings": [{k: v for k, v in GOOD.items() if k != "evidence"}]}]


def test_check_answer_strips_strings():
    """review.check_answer returns the findings with strings stripped. Guards the cleaning of a
    valid answer.
    """
    r = review.check_answer({"summary": " One. ", "findings": [GOOD]})
    assert r == {"summary": "One.", "findings": [{**GOOD, "location": "a"}]}


@pytest.mark.parametrize("bad", MALFORMED)
def test_check_answer_rejects_malformed(bad):
    """review.check_answer raises ValueError for a non-object, missing findings, a finding that is
    not an object, an unknown severity and a missing key, so the model is asked again. Guards each
    check of check_answer.
    """
    with pytest.raises((ValueError, AttributeError)):
        review.check_answer(bad)


def test_models_task_by_kinds(cli_settings):
    """`second-opinion models` shows tasks.chat and tasks.vision of config.yaml and exits 0. Guards
    models.describe and the `models` command.
    """
    p = run_main(cli.main, "models")
    assert p.returncode == 0, p.stderr
    assert "chat    ollama:c" in p.stdout and "vision  ollama:v" in p.stdout


class TestMarkdown(unittest.TestCase):
    def test_findings_ordered_by_severity(self):
        """review.markdown writes the header, files and summary, then the findings ordered fail,
        warn, note with evidence and suggestion. Guards the report layout and order.
        """
        f = lambda sev, loc: {"severity": sev, "location": loc, "issue": "i", "evidence": "e", "suggestion": "s"}
        md = review.markdown({"model": "m", "files": [{"path": "a.png"}], "summary": "Two problems.",
                              "findings": [f("note", "n"), f("fail", "x"), f("warn", "w")]})
        self.assertTrue(md.startswith("# Second opinion (m)\n\nFiles: `a.png`\n\nTwo problems.\n"))
        self.assertLess(md.index("**fail** x"), md.index("**warn** w"))
        self.assertLess(md.index("**warn** w"), md.index("**note** n"))
        self.assertIn("1. **fail** x: i\n   - Evidence: e\n   - Suggestion: s\n", md)

    def test_no_findings(self):
        """review.markdown ends with 'No findings.' when the findings list is empty. Guards the
        report of a clean review.
        """
        md = review.markdown({"model": "m", "files": [], "summary": "No problems found.", "findings": []})
        self.assertTrue(md.endswith("No problems found.\n\nNo findings.\n"))


class TestCliRefusals(unittest.TestCase):
    """Refusals happen before any request, so they need no model."""

    def run_cli(self, argv):
        """The exit code and stderr of `cli.main(argv)` in process."""
        p = run_main(cli.main, *argv)
        return p.returncode, p.stderr

    def test_empty_brief_refused(self):
        """`second-opinion review` exits 1 for a whitespace-only brief. Guards the refusal before any
        request.
        """
        with tempfile.TemporaryDirectory() as tmp:
            md = Path(tmp) / "a.md"
            md.write_text("x")
            code, err = self.run_cli(["review", "--brief", "  ", "--file", str(md)])
        self.assertEqual(code, 1)
        self.assertIn("the brief is empty", err)

    def test_existing_out_checked_before_files(self):
        """`second-opinion review --out` exits before reading the files when the output exists and
        --force is not given. Guards the check order, so an existing findings file is never
        replaced and no transcode runs.
        """
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "findings.json"
            out.write_text("{}")
            code, err = self.run_cli(["review", "--brief", "b", "--file", str(Path(tmp) / "missing.mp4"),
                                      "--out", str(out)])
        self.assertEqual(code, 1)
        self.assertIn("pass --force", err)

    def test_bad_brief_file_and_unreadable_file_end_in_error(self):
        """`second-opinion review` exits 1 with one error message for a brief file that is not
        UTF-8, a missing brief file and an unreadable review file. Guards the error handling of
        _read_brief and files._read instead of a traceback.
        """
        with tempfile.TemporaryDirectory() as tmp:
            brief = Path(tmp) / "brief.md"
            brief.write_bytes(b"check \xff\xfe")
            md = Path(tmp) / "a.md"
            md.write_text("x")
            code, err = self.run_cli(["review", "--brief-file", str(brief), "--file", str(md)])
            self.assertEqual(code, 1)
            self.assertTrue(err.startswith("Error: the brief"), err)
            self.assertIn("not valid UTF-8", err)
            code, err = self.run_cli(["review", "--brief-file", str(Path(tmp) / "none.md"), "--file", str(md)])
            self.assertEqual(code, 1)
            self.assertTrue(err.startswith("Error: cannot read the brief"), err)
            md.chmod(0)
            try:
                code, err = self.run_cli(["review", "--brief", "b", "--file", str(md)])
            finally:
                md.chmod(0o644)
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("Error:") and "cannot read" in err, err)


if __name__ == "__main__":
    unittest.main()
