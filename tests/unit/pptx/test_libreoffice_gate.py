"""The two rendering commands ship ungated, with an actionable message.

`export-slides` and `visual-preview` are not hidden behind a capability check: they run, and when LibreOffice is
missing, `slide_render.libreoffice_to_pdf` raises `LIBREOFFICE_MISSING`, which says what to install. The commands
themselves run with LibreOffice in tests/integration/pptx.
"""
import unittest

from pptx_tool import slide_render


class TestLibreOfficeMissingMessage(unittest.TestCase):

    def test_message_names_both_install_commands(self) -> None:
        """LIBREOFFICE_MISSING says LibreOffice is not found and gives the brew and apt-get install commands.
        Guards the actionable message of export-slides and visual-preview on a machine without LibreOffice."""
        text = slide_render.LIBREOFFICE_MISSING
        for part in ("LibreOffice", "not found", "brew install libreoffice", "apt-get install libreoffice"):
            self.assertIn(part, text)
