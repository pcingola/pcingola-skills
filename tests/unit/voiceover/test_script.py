"""Unit tests for voiceover_tool.script: one sentence per line."""

import unittest

from voiceover_tool.script import parse_script


class TestScript(unittest.TestCase):

    def test_blank_lines_skipped_order_kept(self) -> None:
        """script.parse_script returns one stripped sentence per non-blank line, in order, without splitting a line.
        Guards the rule that timing.json indexes exactly the script's lines."""
        text = "\nFirst sentence.\n\n   \nSecond one, with a comma. And a second clause.\n  Third.  \n\n"
        self.assertEqual(
            parse_script(text),
            ["First sentence.", "Second one, with a comma. And a second clause.", "Third."],
        )


def test_line_style():
    """A line that starts with `[style]` gives that style and the sentence without it; any other line no style."""
    from voiceover_tool.script import split_style

    assert split_style("[whisper]  Keep it quiet.") == ("whisper", "Keep it quiet.")
    assert split_style("[calm  narrator] Hi.") == ("calm narrator", "Hi.")
    assert split_style("Keep [this] in.") == (None, "Keep [this] in.")
    assert split_style("[only a tag]") == (None, "[only a tag]")


if __name__ == "__main__":
    unittest.main()
