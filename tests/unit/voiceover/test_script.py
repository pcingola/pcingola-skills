"""Unit tests for voiceover_tool.script: one sentence per line."""

import unittest

import pytest

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


def test_line_of_a_tag_model():
    """For a model that takes inline tags, `@name` gives the speaker, and bracket and speaker tags anywhere are
    sent and left out of the aligned text."""
    from voiceover_tool.script import Line, strip_tags

    line = Line.of("@anna [sighs] Fine. <|speaker:1|> [laughs] Well.", styles=False, tags=True)
    assert (line.speaker, line.text, line.said) == ("anna", "Fine. Well.", "[sighs] Fine. <|speaker:1|> [laughs] Well.")
    assert strip_tags("a [b]c  <|speaker:2|>d") == "a c d"
    with pytest.raises(ValueError, match="lowercase letters"):
        Line.of("@Anna hi", styles=False, tags=True)
    with pytest.raises(ValueError, match="only tags"):
        Line.of("@anna [laughs]", styles=False, tags=True)


def test_line_of_a_model_without_tags():
    """For a model without inline tags, a leading `[style]` is the style of a model that takes styles; any other
    tag, and an `@speaker`, is refused, since the model would speak it."""
    from voiceover_tool.script import Line

    assert Line.of("[whisper] Hi.", styles=True, tags=False) == Line("Hi.", "Hi.", "whisper")
    assert Line.of("Hi @ noon.", styles=False, tags=False) == Line("Hi @ noon.", "Hi @ noon.")
    for line, styles in [("[whisper] Hi.", False), ("Hi [laughs] there.", True), ("@guest Hi.", True),
                         ("Hi <|speaker:1|> there.", False)]:
        with pytest.raises(ValueError, match="would speak aloud"):
            Line.of(line, styles=styles, tags=False, model="k:kokoro-v1.0")


def test_line_style():
    """A line that starts with `[style]` gives that style and the sentence without it; any other line no style."""
    from voiceover_tool.script import split_style

    assert split_style("[whisper]  Keep it quiet.") == ("whisper", "Keep it quiet.")
    assert split_style("[calm  narrator] Hi.") == ("calm narrator", "Hi.")
    assert split_style("Keep [this] in.") == (None, "Keep [this] in.")
    assert split_style("[only a tag]") == (None, "[only a tag]")


if __name__ == "__main__":
    unittest.main()
