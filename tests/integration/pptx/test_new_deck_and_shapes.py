"""Integration tests for the new-deck and add-shapes commands.

The new-deck tests check the CLI defaults and options, so they call the CLI in process.
The add-shapes tests call the core function. Together they are the blank-canvas path that
references/blank-canvas.md documents: `new-deck` produces the canvas `add-shapes` draws on.
"""
import unittest
from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from pptx_tool.cmd_add_shapes import PresentationShapesAdder
from pptx_tool.cmd_new_deck import create_deck
from pptx_tool.exceptions import PptxError
from tests.integration.pptx import (
    cleanup_dir, cli, create_test_image, fresh_dir, stamp_description, write_readme,
)

DIR = fresh_dir("test_new_deck_and_shapes")
EMU_PER_INCH = 914400


class TestNewDeck(unittest.TestCase):

    @classmethod
    def tearDownClass(cls) -> None:
        write_readme(DIR,
            "new-deck / add-shapes: blank canvas path.\n"
            "Expected outputs:\n"
            "  wide.pptx    — 1 blank slide, 13.33 x 7.5 in\n"
            "  four_3.pptx  — 3 blank slides, 10.0 x 7.5 in\n"
            "  drawn.pptx   — a rect, an oval, a textbox, a line and a picture,\n"
            "                 all native and selectable in PowerPoint")

    def test_default_is_widescreen_single_slide(self) -> None:
        """new-deck without options writes one empty 13.333 x 7.5 in slide. Guards the CLI defaults
        (16:9, one slide) and the blank canvas without placeholders."""
        out = DIR / "wide.pptx"
        r = cli("new-deck", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        prs = Presentation(str(out))
        self.assertEqual(len(prs.slides), 1)
        self.assertAlmostEqual(prs.slide_width / EMU_PER_INCH, 13.333, places=2)
        self.assertAlmostEqual(prs.slide_height / EMU_PER_INCH, 7.5, places=2)
        # A canvas, not a template: no placeholders to fight with.
        self.assertEqual(len(prs.slides[0].shapes), 0)

    def test_slides_and_four_three_size(self) -> None:
        """new-deck --slides 3 --size 4:3 writes three 10 in wide slides. Guards that both options
        reach create_deck."""
        out = DIR / "four_3.pptx"
        r = cli("new-deck", str(out), "--slides", "3", "--size", "4:3")
        self.assertEqual(r.returncode, 0, r.stderr)
        prs = Presentation(str(out))
        self.assertEqual(len(prs.slides), 3)
        self.assertAlmostEqual(prs.slide_width / EMU_PER_INCH, 10.0, places=2)


class TestAddShapes(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.canvas = DIR / "canvas.pptx"
        create_deck(cls.canvas, 1, "16:9")
        cls.image = create_test_image(DIR, "logo.png", 120, 120, "orange")

    def test_draws_native_shapes_and_a_picture(self) -> None:
        """add_shapes on a new-deck canvas draws rect, oval, textbox, line and image as five native
        shapes with readable text at the given inch coordinates, and reports five shapes on slide-0. Guards the blank-canvas path of
        references/blank-canvas.md end to end."""
        spec = {
            "slide-0": [
                {"type": "rect", "left": 0.5, "top": 0.5, "width": 3, "height": 1.2,
                 "fill": "#EFEFEF", "line": {"color": "#333333", "weight": 1},
                 "text": {"paragraphs": [{"text": "Boxed", "bold": True, "font_size": 14}]}},
                {"type": "oval", "left": 4.5, "top": 0.5, "width": 2, "height": 2,
                 "fill": "#8064A2"},
                {"type": "textbox", "left": 0.5, "top": 2.5, "width": 4, "height": 0.8,
                 "text": {"paragraphs": [{"text": "Free text", "font_size": 12}]}},
                {"type": "line", "x1": 0.5, "y1": 4.0, "x2": 6.0, "y2": 4.0,
                 "line": {"color": "#1B1B4B", "weight": 2}, "arrow": "end"},
                {"type": "image", "path": str(self.image), "left": 7.5, "top": 0.5, "width": 1.5},
            ]
        }
        out = DIR / "drawn.pptx"
        result = PresentationShapesAdder().add_shapes(self.canvas, spec, out)
        self.assertEqual(result.per_slide, {"slide-0": 5})

        slide = Presentation(str(out)).slides[0]
        kinds = [s.shape_type for s in slide.shapes]
        self.assertEqual(len(kinds), 5)
        self.assertIn(MSO_SHAPE_TYPE.PICTURE, kinds)
        self.assertIn(MSO_SHAPE_TYPE.TEXT_BOX, kinds)
        # Native, not a flattened image: the text is still readable from the XML.
        texts = [s.text_frame.text for s in slide.shapes if s.has_text_frame]
        self.assertIn("Boxed", texts)
        self.assertIn("Free text", texts)
        # Coordinates land where the spec asked, in inches.
        rect = next(s for s in slide.shapes if s.has_text_frame and s.text_frame.text == "Boxed")
        self.assertAlmostEqual(rect.left / EMU_PER_INCH, 0.5, places=2)
        self.assertAlmostEqual(rect.width / EMU_PER_INCH, 3.0, places=2)
        stamp_description(out,
            "add-shapes: five native shapes on a blank canvas.\n"
            "Expected: grey box reading 'Boxed', magenta oval, 'Free text' textbox,\n"
            "a navy arrow, and an orange square picture top-right.")

    def test_missing_input_errors(self) -> None:
        """add_shapes raises PptxError naming the input deck when it does not exist, and writes
        no output. Guards the input check of the command."""
        out = DIR / "nope3.pptx"
        with self.assertRaisesRegex(PptxError, "Input file '/nonexistent.pptx' not found"):
            PresentationShapesAdder().add_shapes(Path("/nonexistent.pptx"), {"slide-0": []}, out)
        self.assertFalse(out.exists())
