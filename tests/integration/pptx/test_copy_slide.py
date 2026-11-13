"""Integration tests for the copy-slide command."""
import unittest

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Inches

from tests.integration.pptx import (
    cleanup_dir, create_test_image, create_test_pptx, fresh_dir, run_cli, stamp_description,
)

DIR = fresh_dir("test_copy_slide")


class TestCopySlide(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = create_test_pptx(DIR, name="source.pptx", num_slides=3)
        cls.target = create_test_pptx(DIR, name="target.pptx", num_slides=2)

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_copy_multiple_slides(self) -> None:
        """copy-slide with "0,2" appends both source slides to the target. Guards the
        comma-separated slide list and the default append."""
        out = DIR / "copy_multi.pptx"
        r = run_cli("copy-slide", str(self.source), str(self.target), str(out), "0,2")
        self.assertEqual(r.returncode, 0, r.stderr)
        prs = Presentation(str(out))
        self.assertEqual(len(prs.slides), 4)
        stamp_description(out,
            "copy-slide: copied source slides 0 and 2 into target (2 slides).\n"
            "Expected 4 slides total:\n"
            "  Slides 1-2: original target slides\n"
            "  Slide 3: copied source slide 0 ('Slide 0 Title')\n"
            "  Slide 4: copied source slide 2 ('Slide 2 Title')")

    def test_copy_at_position_zero(self) -> None:
        """copy-slide --position 0 inserts the copied slide before the target's first slide. Guards
        the past bug where --position was parsed and ignored, so slides were always appended."""
        out = DIR / "copy_pos0.pptx"
        r = run_cli("copy-slide", str(self.source), str(self.target), str(out),
                    "2", "--position", "0")
        self.assertEqual(r.returncode, 0, r.stderr)
        prs = Presentation(str(out))
        self.assertEqual(len(prs.slides), 3)
        titles = [s.shapes.title.text for s in prs.slides]
        self.assertEqual(titles, ["Slide 2 Title", "Slide 0 Title", "Slide 1 Title"])

    def test_copy_at_middle_position(self) -> None:
        """copy-slide with two slides and --position 1 inserts them at that position in source
        order. Guards the insertion order of several copied slides."""
        out = DIR / "copy_pos1.pptx"
        r = run_cli("copy-slide", str(self.source), str(self.target), str(out),
                    "0,2", "--position", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        prs = Presentation(str(out))
        titles = [s.shapes.title.text for s in prs.slides]
        self.assertEqual(
            titles,
            ["Slide 0 Title", "Slide 0 Title", "Slide 2 Title", "Slide 1 Title"],
        )

    def test_copy_position_out_of_range(self) -> None:
        """copy-slide exits non-zero for --position 99. Guards the position range check."""
        out = DIR / "copy_pos_bad.pptx"
        r = run_cli("copy-slide", str(self.source), str(self.target), str(out),
                    "0", "--position", "99")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_cross_deck_copy_keeps_images(self) -> None:
        """copy-slide copies a slide's picture into another deck with an image part resolvable in
        the target package. Guards the deep copy of referenced parts and rId remapping; copying
        shape elements alone drops the image."""
        img = create_test_image(DIR, "cross.png", 160, 120, "green")
        src = DIR / "with_image.pptx"
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[5])
        slide.shapes.title.text = "Picture Source"
        slide.shapes.add_picture(str(img), Inches(1), Inches(2), Inches(3), Inches(2))
        prs.save(str(src))

        out = DIR / "copy_image.pptx"
        r = run_cli("copy-slide", str(src), str(self.target), str(out), "0")
        self.assertEqual(r.returncode, 0, r.stderr)

        copied = Presentation(str(out)).slides[-1]
        pictures = [s for s in copied.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
        self.assertEqual(len(pictures), 1, "image was dropped by the cross-deck copy")
        # The blob must be resolvable in the *target* package, not dangling.
        self.assertGreater(len(pictures[0].image.blob), 0)

    def test_copy_out_of_range(self) -> None:
        """copy-slide exits non-zero for source slide 99. Guards the source slide range check."""
        out = DIR / "copy_bad.pptx"
        r = run_cli("copy-slide", str(self.source), str(self.target), str(out), "99")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_copy_missing_source(self) -> None:
        """copy-slide exits non-zero when the source deck does not exist. Guards the source file
        check."""
        out = DIR / "copy_nosrc.pptx"
        r = run_cli("copy-slide", "/nonexistent.pptx", str(self.target), str(out), "0")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_copy_missing_target(self) -> None:
        """copy-slide exits non-zero when the target deck does not exist. Guards the target file
        check."""
        out = DIR / "copy_notgt.pptx"
        r = run_cli("copy-slide", str(self.source), "/nonexistent.pptx", str(out), "0")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
