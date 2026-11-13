"""voiceover_tool.cli.play_command: VLC on macOS, xdg-open elsewhere."""
import unittest
from pathlib import Path

from voiceover_tool import cli


class TestPlay(unittest.TestCase):

    def test_command_per_os(self) -> None:
        """cli.play_command opens the file with `open -a VLC` on macOS and with `xdg-open` on Linux. Guards
        `play` on a machine without `open -a`."""
        self.assertEqual(cli.play_command(Path("a.wav"), "Darwin"), ["open", "-a", "VLC", "a.wav"])
        self.assertEqual(cli.play_command(Path("a.wav"), "Linux"), ["xdg-open", "a.wav"])


if __name__ == "__main__":
    unittest.main()
