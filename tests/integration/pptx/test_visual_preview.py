"""Tests of the visual-preview command.

LibreOffice only supplies the slide images; the output names and the grid layout
are our code and are tested on Pillow images without LibreOffice. One end-to-end
test runs LibreOffice and pdftoppm.
"""
import unittest
from pathlib import Path

from PIL import Image

from pptx_tool.cmd_visual_preview import default_output_base, grid_output_paths, visual_preview
from pptx_tool.thumbnail_grid import BORDER_WIDTH, PADDING, THUMBNAIL_WIDTH, Thumbnail, ThumbnailGridGenerator
from tests.prereq import requires
from tests.integration.pptx import (
    cleanup_dir, create_test_pptx, fresh_dir, has_libreoffice, write_readme,
)

DIR = fresh_dir("test_visual_preview")


def _grid_width(columns: int) -> int:
    """Width of a grid of `columns` columns of THUMBNAIL_WIDTH thumbnails, as create_grid lays it out."""
    return columns * (THUMBNAIL_WIDTH + 2 * BORDER_WIDTH) + (columns + 1) * PADDING


class TestVisualPreviewWithoutLibreOffice(unittest.TestCase):

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_default_output_name(self) -> None:
        """Without an output prefix, a deck that fits one grid gets <stem>_thumbnails.jpg next to
        the input. Guards the default output name."""
        base = default_output_base(Path("/decks/test.pptx"))
        self.assertEqual(grid_output_paths(base, 1), [Path("/decks/test_thumbnails.jpg")])

    def test_custom_output_name(self) -> None:
        """An output prefix gives <prefix>.jpg for one grid and <prefix>-1.jpg .. <prefix>-N.jpg for
        several. Guards the single-grid file name (no -N suffix) and the suffixes of several grids."""
        base = Path("/out/preview")
        self.assertEqual(grid_output_paths(base, 1), [Path("/out/preview.jpg")])
        self.assertEqual(grid_output_paths(base, 2), [Path("/out/preview-1.jpg"), Path("/out/preview-2.jpg")])

    def test_custom_cols(self) -> None:
        """create_grid with 3 columns lays 4 thumbnails out in two rows, taller than the one-row
        grid of 5 columns, and each grid is as wide as its column count gives. Guards that the
        column count sets the grid layout."""
        thumbnails = [Thumbnail(i, Image.new("RGB", (THUMBNAIL_WIDTH, 225), "white")) for i in range(4)]
        sizes = {}
        for cols in (5, 3):
            out = DIR / f"preview_cols{cols}.jpg"
            ThumbnailGridGenerator(cols).create_grid(thumbnails, out)
            with Image.open(out) as im:
                sizes[cols] = im.size
            self.assertEqual(sizes[cols][0], _grid_width(cols))
        self.assertGreater(sizes[3][1], sizes[5][1])


@requires(has_libreoffice(), "LibreOffice not installed")
class TestVisualPreviewEndToEnd(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.dir = fresh_dir("test_visual_preview_e2e")
        cls.source = create_test_pptx(cls.dir, num_slides=4)
        write_readme(cls.dir,
            "visual-preview end to end.\n"
            "test.pptx is the source (4 slides: 'Slide 0-3 Title').\n"
            "Expected JPEG output:\n"
            "  test_thumbnails.jpg: 3-column grid, two rows (3 + 1), showing the 4 slide thumbnails.")

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(cls.dir)

    def test_default_preview_with_libreoffice(self) -> None:
        """visual_preview without an output prefix and with 3 columns renders the 4-slide deck and
        writes one grid, <stem>_thumbnails.jpg next to the input, 3 columns wide. Guards the
        integration with LibreOffice and pdftoppm, the default output name, and that the column
        count reaches the grid."""
        outputs = visual_preview(self.source, columns=3)
        expected = self.dir / "test_thumbnails.jpg"
        self.assertEqual(outputs, [expected])
        self.assertTrue(expected.is_file())
        with Image.open(expected) as im:
            self.assertEqual(im.width, _grid_width(3))
