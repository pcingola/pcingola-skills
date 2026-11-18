"""The two rendering commands ship ungated, with an actionable message.

This path runs on a machine without LibreOffice:
`export-slides` and `visual-preview` are not hidden behind a
silent capability check — they run, and when the binary is missing they say what
to install. That contract had no test at all, which meant the message could rot
into a traceback without anything going red.

PATH points at an empty directory, so the real find_libreoffice() finds no
binary. The tests fail where LibreOffice sits in a platform default location
(/Applications on macOS), which PATH does not hide.
"""
import platform
import tempfile
import unittest
from pathlib import Path

from pptx_tool import _KNOWN_PATHS
from tests.prereq import requires
from tests.subproc import child_env, run_python

# Each child makes a blank deck with python-pptx in the empty temporary directory
# and calls the command's core function on it; the input checks and the deck load
# pass, and LibreOffice is the first thing missing.
INSTALL_HINT = "brew install libreoffice"


@requires(not any(Path(p).exists() for p in _KNOWN_PATHS.get(platform.system(), [])),
          "LibreOffice is in a platform default location (/Applications on macOS) that PATH does not hide")
class TestLibreOfficeMissingMessage(unittest.TestCase):

    def run_without_libreoffice(self, call: str):
        """In a child process whose PATH is an empty directory, save a blank deck as deck.pptx
        in that directory and run `call`, an expression of `deck` (its path) and `out` (an
        output path in that directory)."""
        with tempfile.TemporaryDirectory() as empty:
            code = (
                "from pathlib import Path\n"
                "from pptx import Presentation\n"
                "from pptx_tool import cmd_export_slides, cmd_visual_preview\n"
                f"deck = Path({empty!r}) / 'deck.pptx'\n"
                f"out = Path({empty!r}) / 'out'\n"
                "Presentation().save(deck)\n"
                f"{call}\n")
            return run_python(code, child_env(PATH=empty))

    def _assert_actionable(self, text: str) -> None:
        self.assertIn("LibreOffice", text)
        self.assertIn("not found", text)
        self.assertIn(INSTALL_HINT, text)
        self.assertIn("apt-get install libreoffice", text)

    def test_export_slides_raises_with_install_instructions(self) -> None:
        """cmd_export_slides.export_slides on a valid deck raises RuntimeError with the brew and
        apt-get install commands when LibreOffice is missing. Guards the actionable message of
        export-slides on a machine without LibreOffice."""
        done = self.run_without_libreoffice("cmd_export_slides.export_slides(deck, out)")
        self.assertIn("RuntimeError: ", done.stderr)
        self._assert_actionable(done.stderr)

    def test_visual_preview_raises_with_install_instructions(self) -> None:
        """cmd_visual_preview.visual_preview on a valid deck raises RuntimeError with the install
        commands when LibreOffice is missing. Guards the actionable message of visual-preview on
        a machine without LibreOffice."""
        done = self.run_without_libreoffice("cmd_visual_preview.visual_preview(deck, out)")
        self.assertIn("RuntimeError: ", done.stderr)
        self._assert_actionable(done.stderr)
