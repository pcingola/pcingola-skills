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

# Any existing .pptx works — every command probes for LibreOffice before it
# looks at the deck. This file is not a deck; the ones that read it first are
# given a real one by the integration suite instead.
INSTALL_HINT = "brew install libreoffice"


@requires(not any(Path(p).exists() for p in _KNOWN_PATHS.get(platform.system(), [])),
          "LibreOffice is in a platform default location (/Applications on macOS) that PATH does not hide")
class TestLibreOfficeMissingMessage(unittest.TestCase):

    def run_without_libreoffice(self, code: str):
        """Run `code` in a child process whose PATH is an empty directory."""
        with tempfile.TemporaryDirectory() as empty:
            return run_python(code, child_env(PATH=empty))

    def _assert_actionable(self, text: str) -> None:
        self.assertIn("LibreOffice", text)
        self.assertIn("not found", text)
        self.assertIn(INSTALL_HINT, text)
        self.assertIn("apt-get install libreoffice", text)

    def test_export_slides_raises_with_install_instructions(self) -> None:
        """cmd_export_slides._libreoffice_to_pdf raises RuntimeError with the brew and apt-get
        install commands when LibreOffice is missing. Guards the actionable message of
        export-slides on a machine without LibreOffice."""
        done = self.run_without_libreoffice(
            "from pathlib import Path\nfrom pptx_tool import cmd_export_slides\n"
            "cmd_export_slides._libreoffice_to_pdf(Path('deck.pptx'), Path('/tmp'))")
        self.assertIn("RuntimeError: ", done.stderr)
        self._assert_actionable(done.stderr)

    def test_visual_preview_raises_with_install_instructions(self) -> None:
        """cmd_visual_preview.PPTXConverter.convert_to_pdf raises RuntimeError with the install
        commands when LibreOffice is missing. Guards the actionable message of visual-preview on
        a machine without LibreOffice."""
        done = self.run_without_libreoffice(
            "from pathlib import Path\nfrom pptx_tool import cmd_visual_preview\n"
            "cmd_visual_preview.PPTXConverter(Path('deck.pptx'), Path('/tmp')).convert_to_pdf()")
        self.assertIn("RuntimeError: ", done.stderr)
        self._assert_actionable(done.stderr)
