"""Unit tests for extract_shapes data classes and helpers."""
import unittest

from pptx_tool.cmd_extract_shapes import ParagraphData


class TestParagraphData(unittest.TestCase):

    def test_to_dict_excludes_none(self) -> None:
        """cmd_extract_shapes.ParagraphData.to_dict drops fields that are None and keeps those set. Guards the compact shapes JSON, which omits unset formatting."""
        p = ParagraphData(text="hi", bold=True, font_size=18.0)
        d = p.to_dict()
        self.assertEqual(d["text"], "hi")
        self.assertTrue(d["bold"])
        self.assertEqual(d["font_size"], 18.0)
        self.assertNotIn("italic", d)
        self.assertNotIn("alignment", d)

    def test_to_dict_all_fields(self) -> None:
        """ParagraphData.to_dict keeps every set field, including bold=False. Guards that a falsy value is not dropped as if it were None, which would lose an explicit "not bold"."""
        p = ParagraphData(
            text="full",
            bullet=True,
            level=1,
            alignment="CENTER",
            space_before=6.0,
            space_after=6.0,
            font_name="Arial",
            font_size=14.0,
            bold=False,
            italic=True,
            underline=True,
            theme_color="ACCENT_1",
            line_spacing=1.5,
        )
        d = p.to_dict()
        self.assertEqual(len(d), 13)
        self.assertIs(d["bold"], False)
        self.assertEqual(d["level"], 1)
        self.assertEqual(d["line_spacing"], 1.5)
