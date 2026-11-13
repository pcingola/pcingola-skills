"""Integration tests for the visual-preview command."""
import unittest

from PIL import Image

from tests.prereq import requires
from tests.integration.pptx import (
    cleanup_dir, create_test_pptx, fresh_dir, has_libreoffice, run_cli, write_readme,
)

DIR = fresh_dir("test_visual_preview")


@requires(has_libreoffice(), "LibreOffice not installed")
class TestVisualPreview(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = create_test_pptx(DIR, num_slides=4)
        write_readme(DIR,
            "visual-preview: JPEG thumbnail output tests.\n"
            "test.pptx is the source (4 slides: 'Slide 0-3 Title').\n"
            "Expected JPEG outputs:\n"
            "  test_thumbnails.jpg: default 5-column grid\n"
            "  preview.jpg: grid at an explicit output prefix\n"
            "  preview_cols5.jpg, preview_cols3.jpg: one row of 4, and 2 rows of 3 + 1\n"
            "Each should show the 4 slide thumbnails.")

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_default_preview(self) -> None:
        """visual-preview without an output path writes <stem>_thumbnails.jpg next to the input.
        Guards the default output name."""
        r = run_cli("visual-preview", str(self.source))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((DIR / "test_thumbnails.jpg").is_file(), r.stdout)

    def test_custom_output(self) -> None:
        """visual-preview with an output prefix writes <prefix>.jpg when the slides fit one grid.
        Guards the single-grid file name (no -N suffix)."""
        out = DIR / "preview"
        r = run_cli("visual-preview", str(self.source), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((DIR / "preview.jpg").is_file(), r.stdout)

    def test_custom_cols(self) -> None:
        """visual-preview --cols 3 lays 4 slides out in two rows, taller than the one-row grid of
        --cols 5. Guards that --cols reaches the grid layout."""
        for cols in ("5", "3"):
            r = run_cli("visual-preview", str(self.source), str(DIR / f"preview_cols{cols}"),
                        "--cols", cols)
            self.assertEqual(r.returncode, 0, r.stderr)
        with Image.open(DIR / "preview_cols5.jpg") as five, Image.open(DIR / "preview_cols3.jpg") as three:
            self.assertGreater(three.height, five.height)
