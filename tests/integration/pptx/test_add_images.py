"""Integration tests for the add-images command.

The tests call the core function `add_images`. One test calls the CLI in process to check the
stream and exit code of an error.
"""
import unittest
from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from pptx_tool.cmd_add_images import add_images, parse_image_paths
from pptx_tool.exceptions import PptxError
from tests.integration.pptx import (
    cleanup_dir, cli, create_multilayout_pptx, create_test_image, create_test_pptx, fresh_dir,
    stamp_description,
)

DIR = fresh_dir("test_add_images")


class TestAddImages(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        # Slide 1 of the synthetic fixture carries two PICTURE placeholders.
        cls.with_placeholders = create_multilayout_pptx(DIR, "placeholders.pptx")
        stamp_description(cls.with_placeholders,
            "TEST FIXTURE: synthetic multi-layout deck.\n"
            "This file is used as input for the add-images tests.\n"
            "No verification needed — open img_one.pptx or img_two.pptx instead.")

        cls.test_image = create_test_image(DIR, "red.png", 200, 200, "red")
        cls.test_image2 = create_test_image(DIR, "blue.png", 200, 200, "blue")
        cls.simple = create_test_pptx(DIR, num_slides=2)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_add_single_image(self) -> None:
        """add_images with one image fills one PICTURE placeholder of the slide (the single-image
        branch, placeholder index 0) and reports one image inserted. Guards that the image becomes
        a picture in the placeholder."""
        out = DIR / "img_one.pptx"
        result = add_images(self.with_placeholders, out, 1, [self.test_image])
        self.assertEqual(result.inserted, 1)
        slide = Presentation(str(out)).slides[1]
        pictures = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
        self.assertEqual(len(pictures), 1)
        stamp_description(out,
            "add-images: inserted a RED image into slide 1 (index 1).\n"
            "Expected:\n"
            "  Slide 2 ('Picture Slide'): the RED image fills the left picture placeholder")

    def test_add_multiple_images(self) -> None:
        """add_images with two images, parsed from the comma-separated CLI argument, fills both
        PICTURE placeholders of the slide. Guards the multi-image branch; a run without an error
        passed when only one image landed."""
        out = DIR / "img_two.pptx"
        images = parse_image_paths(f"{self.test_image},{self.test_image2}")
        self.assertEqual(images, [self.test_image, self.test_image2])
        result = add_images(self.with_placeholders, out, 1, images)
        self.assertTrue(out.exists())
        self.assertEqual(result.inserted, 2)
        self.assertEqual(result.warnings, [])
        # Both placeholders must be filled: a run without an error passes when only one
        # image lands.
        slide = Presentation(str(out)).slides[1]
        pictures = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
        self.assertEqual(len(pictures), 2)
        stamp_description(out,
            "add-images: inserted RED and BLUE images into slide 1 (index 1).\n"
            "Expected:\n"
            "  Slide 2 ('Picture Slide'): RED in placeholder 0, BLUE in placeholder 1")

    def test_add_image_to_simple(self) -> None:
        """add_images raises PptxError on a slide without PICTURE placeholders and writes no output.
        Guards the error for a missing placeholder instead of a silent no-op."""
        out = DIR / "img_simple.pptx"
        with self.assertRaisesRegex(PptxError, "No PICTURE placeholder found on slide 0"):
            add_images(self.simple, out, 0, [self.test_image])
        self.assertFalse(out.exists())

    def test_add_image_missing_file(self) -> None:
        """add_images raises PptxError naming the image when an image path does not exist. Guards
        the file check before the deck is opened."""
        out = DIR / "img_missing.pptx"
        with self.assertRaisesRegex(PptxError, "Image file not found: /nonexistent.png"):
            add_images(self.simple, out, 0, [Path("/nonexistent.png")])

    def test_add_image_bad_slide_index(self) -> None:
        """add_images raises PptxError for a slide index past the last slide or negative. Guards the
        slide range check."""
        for slide in (99, -1):
            with self.assertRaisesRegex(PptxError, rf"Slide index {slide} out of range \(0-1\)"):
                add_images(self.simple, DIR / "img_bad_slide.pptx", slide, [self.test_image])

    def test_add_image_bad_placeholder_index(self) -> None:
        """add_images raises PptxError with "out of range" for index 9, past the PICTURE
        placeholders of the slide. Guards the error path of insert_image_in_placeholder, which
        turns its IndexError into a PptxError."""
        with self.assertRaisesRegex(PptxError, "Placeholder index 9 out of range"):
            add_images(self.with_placeholders, DIR / "img_bad_index.pptx", 1,
                       [self.test_image], index=9)

    def test_add_image_invalid_type(self) -> None:
        """add_images raises PptxError listing the valid types for placeholder type INVALID. Guards
        the PlaceholderType lookup that lists PICTURE, OBJECT and MEDIA."""
        out = DIR / "img_bad_type.pptx"
        with self.assertRaisesRegex(PptxError, "PICTURE, OBJECT, MEDIA"):
            add_images(self.simple, out, 0, [self.test_image], placeholder_type="INVALID")

    def test_add_image_missing_input(self) -> None:
        """add_images raises PptxError naming the input deck when it does not exist. Guards the
        input check of the command."""
        out = DIR / "img_no_input.pptx"
        with self.assertRaisesRegex(PptxError, "Input file not found: /nonexistent.pptx"):
            add_images(Path("/nonexistent.pptx"), out, 0, [self.test_image])

    def test_cli_error_on_stderr(self) -> None:
        """The add-images CLI exits 1 with one `Error:` line on stderr, none on stdout and no
        traceback, for a negative slide index given as `-1`. Guards the error stream of add-images
        (stderr, unlike the commands in STDOUT_ERROR_COMMANDS) and that argparse takes `-1` as the
        slide argument."""
        r = cli("add-images", str(self.simple), str(DIR / "img_cli_error.pptx"), "-1",
                str(self.test_image))
        self.assertEqual(r.returncode, 1)
        self.assertIn("Error: Slide index -1 out of range (0-1)", r.stderr)
        self.assertNotIn("Error:", r.stdout)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
