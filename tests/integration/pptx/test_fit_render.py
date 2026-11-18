"""Integration test of the text-height rule against LibreOffice renders (docs/pptx.md, "Text
measurement and fitting"): the most one-line bullets the add-text fitter accepts in the neutral
template's Title and Content body render inside the frame, and one more bullet renders below it."""
import unittest

from lxml import etree
from PIL import Image
from pptx import Presentation

from pptx_tool.cmd_add_slide import add_slides
from pptx_tool.cmd_add_text import PresentationTextAdder
from pptx_tool.cmd_export_slides import export_slides
from pptx_tool.text_fitting import TextFitter, paragraph_base_sizes
from tests.prereq import requires
from tests.integration.pptx import (
    PROJECT_DIR, cleanup_dir, fresh_dir, has_libreoffice, write_readme,
)

DIR = fresh_dir("test_fit_render")
TEMPLATE = PROJECT_DIR / "plugins/brand/skills/brand/brands/neutral/pptx/presentation.pptx"
EMU_PER_INCH = 914400
DPI = 100
NO_AUTOFIT = "{http://schemas.openxmlformats.org/drawingml/2006/main}noAutofit"


def _bullets(n: int) -> list[dict]:
    return [{"text": f"Short item {i}", "bullet": True} for i in range(n)]


def _deck(counts: list[int]):
    """A deck of one Title and Content slide per entry of `counts`, slide i with counts[i] bullets
    at the inherited size, written as add-text writes them, with the template's normAutofit
    replaced by noAutofit so the renderer does not shrink the text. Returns the presentation and
    the body shape of each slide."""
    prs = Presentation(str(TEMPLATE))
    ids = prs.slides._sldIdLst
    template_ids = list(ids)
    add_slides(prs, ["Title and Content"] * len(counts), None)
    for sld_id in template_ids:
        ids.remove(sld_id)
    bodies = []
    for slide, n in zip(prs.slides, counts):
        body = slide.shapes[1]
        body.text_frame.clear()
        PresentationTextAdder()._add_paragraphs(body.text_frame, _bullets(n), 0,
                                                paragraph_base_sizes(body, _bullets(n)))
        body_pr = body.text_frame._txBody.bodyPr
        for child in list(body_pr):
            if child.tag.endswith("Autofit"):
                body_pr.remove(child)
        etree.SubElement(body_pr, NO_AUTOFIT)
        bodies.append(body)
    return prs, bodies


def _last_ink_and_bottom(image, body) -> tuple[int, float]:
    """Return the lowest dark pixel row under `body` in the slide image rendered at DPI, and the
    row of the frame's bottom inset."""
    with Image.open(image) as im:
        gray = im.convert("L")
    x0 = int(body.left / EMU_PER_INCH * DPI) + 2
    x1 = int((body.left + body.width) / EMU_PER_INCH * DPI) - 2
    top = int(body.top / EMU_PER_INCH * DPI)
    ink = [y for y in range(top, gray.height) for x in range(x0, x1, 2) if gray.getpixel((x, y)) < 128]
    inset_bottom = (body.top + body.height - body.text_frame.margin_bottom) / EMU_PER_INCH * DPI
    return max(ink), inset_bottom


@requires(has_libreoffice(), "LibreOffice not installed")
class TestFitRender(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        write_readme(DIR,
            "Fitter against render: Title and Content body of the neutral template, one-line bullets\n"
            "at the inherited size, noAutofit.\n"
            "  render/slide_01.png : the most bullets the fitter accepts; all text inside the frame\n"
            "  render/slide_02.png : one bullet more; the last bullet below the frame")

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_fitter_limit_matches_render(self) -> None:
        """The largest bullet count the fitter accepts at the inherited size renders with its last
        line inside the frame's bottom inset, and one more bullet renders past it. Guards the
        text-height rule (1.2 x size per line, inherited spcBef between paragraphs) against what
        LibreOffice draws."""
        _, [body] = _deck([1])
        size = paragraph_base_sizes(body, _bullets(1))[0]
        fitter = TextFitter(min_font_size=size)
        accepted = max(n for n in range(1, 30) if fitter.find_fitting_reduction(
            body, {"paragraphs": _bullets(n)}, "slide-0", "shape-1").fits)

        prs, [fit_body, over_body] = _deck([accepted, accepted + 1])
        deck = DIR / "render.pptx"
        prs.save(str(deck))
        fit_image, over_image = export_slides(deck, DIR / "render", dpi=DPI)
        fit_ink, bottom = _last_ink_and_bottom(fit_image, fit_body)
        self.assertLessEqual(fit_ink, bottom, f"{accepted} accepted bullets render past the frame")
        over_ink, bottom = _last_ink_and_bottom(over_image, over_body)
        self.assertGreater(over_ink, bottom, f"{accepted + 1} bullets still render inside the frame")


if __name__ == "__main__":
    unittest.main()
