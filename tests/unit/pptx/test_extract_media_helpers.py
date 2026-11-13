"""Unit tests for pptx extract_media helpers."""
import unittest

from pptx_tool.cmd_extract_media import _parse_min_pixels


class TestParseMinPixels(unittest.TestCase):

    def test_rectangular(self) -> None:
        """cmd_extract_media._parse_min_pixels reads "100x30" as (width, height). Guards the order of the --min-pixels threshold, which filters images by width and height separately."""
        self.assertEqual(_parse_min_pixels("100x30"), (100, 30))

    def test_invalid_raises(self) -> None:
        """cmd_extract_media._parse_min_pixels raises ValueError on a value that is not WxH. Guards the explicit error for a malformed --min-pixels instead of a silent default."""
        with self.assertRaises(ValueError):
            _parse_min_pixels("invalid")

