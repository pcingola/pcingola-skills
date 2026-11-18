"""Tests of the pptx wrapper `scripts/pptx.sh` run as a process.

The subject is the wrapper, the `uv_env.sh` it sources and the skill's locked environment:
`pptx.sh` finds the plugin directory, sets up the environment outside `plugins/`, starts
`python -m pptx_tool` and passes the arguments and the exit code through. These are the only
pptx tests that start `pptx.sh`; every other test calls the code in process.
"""
import json
import subprocess
import unittest

from tests.integration.pptx import PROJECT_DIR, cleanup_dir, fresh_dir

PPTX_TOOL = str(PROJECT_DIR / "plugins" / "docs" / "skills" / "pptx" / "scripts" / "pptx.sh")

DIR = fresh_dir("test_wrapper")
TIMEOUT_S = 25


def run_wrapper(*args: str) -> subprocess.CompletedProcess:
    """Run `pptx.sh <args>` from the repository root, for at most TIMEOUT_S seconds."""
    return subprocess.run([PPTX_TOOL, *args], capture_output=True, text=True, cwd=PROJECT_DIR,
                          timeout=TIMEOUT_S)


class TestWrapper(unittest.TestCase):

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_help(self) -> None:
        """`pptx.sh --help` exits 0 and prints the usage of the `pptx` parser with its commands.
        Guards that the wrapper builds the skill's environment and starts `pptx_tool` in it."""
        r = run_wrapper("--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("usage: pptx", r.stdout)
        self.assertIn("new-deck", r.stdout)

    def test_new_deck_then_validate(self) -> None:
        """`pptx.sh new-deck` writes a two-slide deck, and `pptx.sh validate` on it exits 0 and prints
        a JSON report with two slides and no problems. Guards that the wrapper passes arguments
        through and that a command runs end to end with the skill's locked dependencies."""
        deck = DIR / "deck.pptx"
        r = run_wrapper("new-deck", str(deck), "--slides", "2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(deck.is_file())

        r = run_wrapper("validate", str(deck))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        report = json.loads(r.stdout)
        self.assertEqual(report["slide_count"], 2)
        self.assertEqual(report["text_issues"], {})
        self.assertEqual(report["empty_text_placeholders"], [])
        self.assertEqual(report["unfilled_visual_placeholders"], [])

    def test_error_exit_code(self) -> None:
        """`pptx.sh validate` on a missing file exits 1 and prints the error on stderr. Guards that the
        wrapper (`exec uv run ...`) returns the CLI's exit code and stream to the caller."""
        missing = DIR / "missing.pptx"
        r = run_wrapper("validate", str(missing))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn(f"Error: Input file '{missing}' not found", r.stderr)


if __name__ == "__main__":
    unittest.main()
