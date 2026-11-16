"""The shared font-loading and text-measurement path.

`measure.py` is the one measurement path shared by the overflow detector and
the font-size fitter. These tests pin its properties.

The bundled-font case is the sharp one. `load_font` used to fall through to
PIL's built-in bitmap font whenever no system font matched, which is what
happens on a container with no Calibri installed. Nothing raised: measurement
just quietly became meaningless while every overflow assertion still passed.
That is why `assets/fonts/Inter_24pt-Light.ttf` ships, and why it needs a test —
if the file goes missing, or the path constant is wrong, the failure is silent.
"""
import unittest

from PIL import ImageFont

from pptx_tool.common import DEFAULT_FONT_PATH
from pptx_tool import measure


class TestBundledFont(unittest.TestCase):

    def test_load_font_falls_back_to_the_bundled_face_not_pil_default(self) -> None:
        """measure.load_font returns the bundled Inter face (DEFAULT_FONT_PATH) when no system font
        matches. Guards the fallback that keeps measurement meaningful on machines without the
        deck's fonts; PIL's default font measured silently wrong before."""
        font = measure.load_font("NoSuchFontExistsAnywhere", 18, font_dirs=[])
        self.assertIsInstance(font, ImageFont.FreeTypeFont)
        self.assertEqual(font.path, str(DEFAULT_FONT_PATH))


class TestMeasureTextLines(unittest.TestCase):

    def test_short_text_is_one_line(self) -> None:
        """measure.measure_text_lines counts two words in a 6-inch column as one line. Guards the
        wrap loop and the 10% width margin against overcounting short text."""
        self.assertEqual(measure.measure_text_lines("Two words", "Arial", 18, 6.0), 1)

    def test_narrower_column_needs_more_lines(self) -> None:
        """measure.measure_text_lines returns more lines for the same text in a narrower column.
        Guards that the column width reaches the wrap computation."""
        text = " ".join(["word"] * 20)
        self.assertGreater(
            measure.measure_text_lines(text, "Arial", 18, 1.5),
            measure.measure_text_lines(text, "Arial", 18, 6.0),
        )

    def test_empty_text_is_one_line(self) -> None:
        """measure.measure_text_lines returns 1 for empty text. Guards the explicit empty-text
        branch, which would otherwise index words[0] of an empty list."""
        self.assertEqual(measure.measure_text_lines("", "Arial", 18, 4.0), 1)

    def test_fallback_estimate_scales_with_font_size(self) -> None:
        """measure.estimate_text_lines, measure_text_lines' fallback when measuring fails, gives more
        lines at 32 pt than at 10 pt. Guards the replacement of a fixed chars-per-inch estimate
        that ignored the font size."""
        small = measure.estimate_text_lines("x" * 200, 10, 2.0)
        large = measure.estimate_text_lines("x" * 200, 32, 2.0)
        self.assertGreater(large, small, "fallback ignored font size")


class TestTextWidth(unittest.TestCase):

    def test_empty_string_is_zero(self) -> None:
        """measure.text_width returns 0.0 for an empty string. Guards the explicit early return used
        by callers that place shapes by text width."""
        self.assertEqual(measure.text_width("", "Arial", 18), 0.0)

    def test_larger_font_measures_wider(self) -> None:
        """measure.text_width measures the same text wider at 36 pt than at 12 pt. Guards that the
        point size is passed through to the font load."""
        self.assertGreater(
            measure.text_width("Sample", "Arial", 36),
            measure.text_width("Sample", "Arial", 12),
        )
