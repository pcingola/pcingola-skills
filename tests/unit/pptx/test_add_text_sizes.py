"""Unit tests for the text sizes add-text writes on slides of the neutral brand template: inherited
sizes stay inherited, overflow still reduces from the inherited size, explicit sizes stay."""
import tempfile
import unittest
from pathlib import Path

from pptx import Presentation
from pptx.util import Pt

from pptx_tool.cmd_add_slide import add_slides
from pptx_tool.cmd_edit import apply_operations
from pptx_tool.cmd_extract_shapes import get_placeholder_type
from pptx_tool.text_fitting import inherited_font_size

TEMPLATE = (Path(__file__).resolve().parents[3]
            / "plugins/brand/skills/brand/brands/neutral/pptx/presentation.pptx")


def _run_sizes(shape) -> list:
    """The explicit run sizes of a shape, None for a run without one."""
    return [run.font.size for p in shape.text_frame.paragraphs for run in p.runs]


class TestAddTextSizes(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "out.pptx"

    def test_inherited_size_follows_layout(self) -> None:
        """inherited_font_size reads the layout and master chain: the Title Slide CENTER_TITLE gets
        the title size of the template, larger than the 18 pt body default. Guards CENTER_TITLE
        being sized as body text."""
        prs = Presentation(str(TEMPLATE))
        add_slides(prs, ["Title Slide"], None)
        title = prs.slides[0].shapes[0]
        self.assertEqual(get_placeholder_type(title), "CENTER_TITLE")
        self.assertGreater(inherited_font_size(title, "CENTER_TITLE"), 18.0)

    def test_title_slide_title_inherits(self) -> None:
        """add-text on a new Title Slide writes no sz on title and subtitle runs without font_size.
        Guards the fixed 18 pt default that shrank Title Slide titles."""
        apply_operations(TEMPLATE, self.out, [
            {"action": "add-slide", "layouts": ["Title Slide"]},
            {"action": "add-text", "data": {"slide-0": {
                "shape-0": {"paragraphs": [{"text": "Quarterly review"}]},
                "shape-1": {"paragraphs": [{"text": "Subtitle"}]},
            }}},
        ])
        slide = Presentation(str(self.out)).slides[0]
        self.assertEqual(slide.shapes[0].text_frame.text, "Quarterly review")
        self.assertEqual(_run_sizes(slide.shapes[0]), [None])
        self.assertEqual(_run_sizes(slide.shapes[1]), [None])

    def test_overflow_reduces_from_inherited_size(self) -> None:
        """Body text that overflows at the inherited size gets an explicit size below it. Guards the
        overflow reduction after the change to inherited sizes."""
        prs = Presentation(str(TEMPLATE))
        add_slides(prs, ["Title and Content"], None)
        inherited = inherited_font_size(prs.slides[0].shapes[1], "OBJECT")
        bullets = [{"text": f"Point {i} with enough words to wrap across the placeholder width once",
                    "bullet": True} for i in range(8)]
        apply_operations(TEMPLATE, self.out, [
            {"action": "add-slide", "layouts": ["Title and Content"]},
            {"action": "add-text", "data": {"slide-0": {"shape-1": {"paragraphs": bullets}}}},
        ])
        sizes = _run_sizes(Presentation(str(self.out)).slides[0].shapes[1])
        self.assertEqual(len(sizes), 8)
        self.assertTrue(all(s is not None and s < Pt(inherited) for s in sizes), sizes)

    def test_explicit_font_size_kept(self) -> None:
        """A paragraph with font_size keeps that size when the text fits. Guards explicit sizes."""
        apply_operations(TEMPLATE, self.out, [
            {"action": "add-slide", "layouts": ["Title Slide"]},
            {"action": "add-text", "data": {"slide-0": {
                "shape-0": {"paragraphs": [{"text": "Title", "font_size": 30}]},
            }}},
        ])
        title = Presentation(str(self.out)).slides[0].shapes[0]
        self.assertEqual(_run_sizes(title), [Pt(30)])


if __name__ == "__main__":
    unittest.main()
