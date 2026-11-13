"""Unit tests for select_slides parsing functions."""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches

from pptx_tool.cmd_select_slides import clone_slide_to_presentation, create_presentation_from_template, parse_sequence

# Slides needed by REPEAT_SEQUENCE below (its highest index is 17).
FIXTURE_SLIDES = 18


def build_fixture_deck(path: Path, num_slides: int = FIXTURE_SLIDES) -> Path:
    """Build a deck with `num_slides` distinct, image-bearing slides.

    What these tests need is slide count (>= 18, for
    REPEAT_SEQUENCE) and a title text frame per slide; the image gives the part
    graph something to get wrong beyond the slide XML itself.
    """
    from PIL import Image

    prs = Presentation()
    img = path.parent / "_fixture.png"
    Image.new("RGB", (120, 80), color=(20, 140, 220)).save(img)
    for i in range(num_slides):
        slide = prs.slides.add_slide(prs.slide_layouts[5])  # Title Only
        slide.shapes.title.text = f"Fixture slide {i}"
        slide.shapes.add_picture(str(img), Inches(1), Inches(2), Inches(2), Inches(1.5))
    prs.save(str(path))
    img.unlink(missing_ok=True)
    return path


class TestParseSequence(unittest.TestCase):

    def test_repeated_indices(self) -> None:
        """cmd_select_slides.parse_sequence keeps repeated and out-of-order indices. Guards that a
        sequence can reuse a template slide several times, as a long deck built from a few layouts does."""
        self.assertEqual(parse_sequence("0,3,3,7"), [0, 3, 3, 7])

    def test_invalid_format(self) -> None:
        """cmd_select_slides.parse_sequence raises ValueError with a usage example for a non-integer
        entry. Guards the explicit error message of --sequence."""
        with self.assertRaises(ValueError) as ctx:
            parse_sequence("abc")
        self.assertIn("Invalid sequence format", str(ctx.exception))


class TestDuplicateSlideIndependence(unittest.TestCase):
    """Cloned slides must have independent parts after save/reload.

    Bug: when create_presentation_from_template deletes some template slides
    and then duplicates others, the new partnames allocated by add_slide()
    can collide with partnames of deleted-but-still-packaged slides.  On
    save, the ZIP gets duplicate entries (e.g. two slide5.xml files) and
    python-pptx resolves them to one Part on reload.  Writing to one
    slide's shapes then silently overwrites the other.

    The sequence [4,3,0,3,3,17,0,...] of a 32-slide deck triggers this because template
    slide 4 = slide5.xml is kept, and a duplicate of template slide 0 is
    allocated partname slide5.xml (matching the deleted-then-freed slot).
    """

    # A sequence that triggers the partname collision bug
    REPEAT_SEQUENCE = [4, 3, 0, 3, 3, 17, 0, 3, 3, 3, 3, 3, 0, 3, 3, 3, 3, 3, 3, 3, 3, 0, 3, 3, 3, 3, 3, 0, 3, 3, 3, 4]

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = Path(tempfile.mkdtemp(prefix="pptx_select_"))
        cls.TEMPLATE = build_fixture_deck(cls._tmp / "fixture.pptx")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_no_shared_parts_after_save_reload(self):
        """cmd_select_slides.create_presentation_from_template with a repeating sequence gives every
        slide its own part after save and reload. Guards the past bug where a duplicate's
        partname collided with a deleted slide's and two slides shared one part."""
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            create_presentation_from_template(self.TEMPLATE, tmp_path, self.REPEAT_SEQUENCE)

            prs = Presentation(str(tmp_path))
            self.assertEqual(len(prs.slides), len(self.REPEAT_SEQUENCE))

            part_ids = [id(prs.slides[i].part) for i in range(len(prs.slides))]
            self.assertEqual(
                len(set(part_ids)), len(self.REPEAT_SEQUENCE),
                f"All {len(self.REPEAT_SEQUENCE)} slides must have distinct Part objects"
            )
        finally:
            os.unlink(tmp_path)


class TestCloneSlideToPresentation(unittest.TestCase):
    """clone_slide_to_presentation must produce independent parts."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = Path(tempfile.mkdtemp(prefix="pptx_clone_"))
        cls.TEMPLATE = build_fixture_deck(cls._tmp / "fixture.pptx", num_slides=3)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def test_cloned_slides_have_distinct_parts(self):
        """cmd_select_slides.clone_slide_to_presentation cloning one slide twice adds two slides
        with distinct parts. Guards that each clone gets its own slide part."""
        source = Presentation(str(self.TEMPLATE))
        target = Presentation(str(self.TEMPLATE))
        total_before = len(target.slides)

        clone_slide_to_presentation(source, target, 0)
        clone_slide_to_presentation(source, target, 0)

        total_after = len(target.slides)
        self.assertEqual(total_after, total_before + 2)

        clone1_part = target.slides[total_before].part
        clone2_part = target.slides[total_before + 1].part
        self.assertIsNot(
            clone1_part, clone2_part,
            "Cloned slides must not share the same Part object"
        )
