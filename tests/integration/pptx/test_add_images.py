"""Integration tests for the add-images command."""
import unittest

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from tests.integration.pptx import (
    cleanup_dir, create_multilayout_pptx, create_test_image, create_test_pptx, fresh_dir,
    run_cli, stamp_description,
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
        """add-images with one image fills one PICTURE placeholder of the slide (the single-image
        branch, placeholder index 0). Guards that the image becomes a picture in the placeholder."""
        out = DIR / "img_one.pptx"
        r = run_cli("add-images", str(self.with_placeholders), str(out), "1", str(self.test_image))
        self.assertEqual(r.returncode, 0, r.stderr)
        slide = Presentation(str(out)).slides[1]
        pictures = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
        self.assertEqual(len(pictures), 1)
        stamp_description(out,
            "add-images: inserted a RED image into slide 1 (index 1).\n"
            "Expected:\n"
            "  Slide 2 ('Picture Slide'): the RED image fills the left picture placeholder")

    def test_add_multiple_images(self) -> None:
        """add-images with two comma-separated images fills both PICTURE placeholders of the slide.
        Guards the multi-image branch; an exit code of 0 alone passed when only one image landed."""
        out = DIR / "img_two.pptx"
        images = f"{self.test_image},{self.test_image2}"
        r = run_cli("add-images", str(self.with_placeholders), str(out), "1", images)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(out.exists())
        # Both placeholders must be filled: the exit code alone passes when only one
        # image lands.
        slide = Presentation(str(out)).slides[1]
        pictures = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
        self.assertEqual(len(pictures), 2)
        stamp_description(out,
            "add-images: inserted RED and BLUE images into slide 1 (index 1).\n"
            "Expected:\n"
            "  Slide 2 ('Picture Slide'): RED in placeholder 0, BLUE in placeholder 1")

    def test_add_image_to_simple(self) -> None:
        """add-images exits non-zero on a slide without PICTURE placeholders. Guards the error for a
        missing placeholder instead of a silent no-op."""
        out = DIR / "img_simple.pptx"
        r = run_cli("add-images", str(self.simple), str(out), "0", str(self.test_image))
        # Simple PPTX has no PICTURE placeholders, so this should fail
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_add_image_missing_file(self) -> None:
        """add-images exits non-zero when an image path does not exist. Guards the file check before
        the deck is opened."""
        out = DIR / "img_missing.pptx"
        r = run_cli("add-images", str(self.simple), str(out), "0", "/nonexistent.png")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_add_image_bad_slide_index(self) -> None:
        """add-images exits non-zero for a slide index past the last slide. Guards the slide range
        check."""
        out = DIR / "img_bad_slide.pptx"
        r = run_cli("add-images", str(self.simple), str(out), "99", str(self.test_image))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_add_image_invalid_type(self) -> None:
        """add-images exits non-zero for --type INVALID. Guards the PlaceholderType lookup that
        lists PICTURE, OBJECT and MEDIA."""
        out = DIR / "img_bad_type.pptx"
        r = run_cli("add-images", str(self.simple), str(out), "0", str(self.test_image), "--type", "INVALID")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_add_image_missing_input(self) -> None:
        """add-images exits non-zero when the input deck does not exist. Guards the input check of
        the command."""
        out = DIR / "img_no_input.pptx"
        r = run_cli("add-images", "/nonexistent.pptx", str(out), "0", str(self.test_image))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
