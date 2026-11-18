"""Integration tests for list-images and extract-images."""
import json
import unittest

from pptx_tool.cmd_extract_media import extract_images

from tests.integration.pptx import (
    cleanup_dir,
    cli,
    create_pptx_with_table_and_image,
    fresh_dir,
)

IMG_DIR = fresh_dir("test_extract_images")


class TestExtractImages(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.pptx = create_pptx_with_table_and_image(IMG_DIR)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(IMG_DIR)

    def test_list_images(self) -> None:
        """The list-images CLI prints a header line and one line per image. Guards the image listing
        output, which the CLI layer formats."""
        r = cli("list-images", str(self.pptx))
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = [l for l in r.stdout.splitlines() if l.strip()]
        self.assertGreaterEqual(len(lines), 2)
        self.assertIn("slide", lines[0])

    def test_extract_images(self) -> None:
        """extract_images writes each image as slide_NN_img_* with an images.json sidecar entry
        carrying its 0-based slide, and a 1-based slide number in the file name. Guards the file
        naming and sidecar of extracted images."""
        out_dir = IMG_DIR / "out_images"
        extract_images(self.pptx, out_dir, min_bytes=1)
        sidecar = json.loads((out_dir / "images.json").read_text())
        self.assertGreaterEqual(len(sidecar), 1)
        entry = sidecar[0]
        self.assertEqual(entry["slide"], 0)  # 0-based field, 1-based file name
        self.assertTrue((out_dir / entry["file"]).exists())
        self.assertTrue(entry["file"].startswith("slide_01_img_"))

    def test_extract_images_min_pixels_filter(self) -> None:
        """extract_images with min_pixels (9999, 9999) writes an empty sidecar. Guards the pixel
        size filter. The parsing of the --min-pixels WxH string has unit tests in
        tests/unit/pptx/test_extract_media_helpers.py."""
        out_dir = IMG_DIR / "out_filtered"
        extract_images(self.pptx, out_dir, min_bytes=1, min_pixels=(9999, 9999))
        sidecar = json.loads((out_dir / "images.json").read_text())
        self.assertEqual(sidecar, [])
