"""Integration test of the text-height rule against LibreOffice renders (docs/pptx.md, "Text
measurement and fitting"): the most one-line bullets the add-text fitter accepts in the neutral
template's Title and Content body render inside the frame, and one more bullet renders below it."""
import unittest

from lxml import etree
from PIL import Image
from pptx import Presentation

from pptx_tool.cmd_add_slide import add_slides
from pptx_tool.cmd_add_text import PresentationTextAdder
from pptx_tool.text_fitting import TextFitter, paragraph_base_sizes
from tests.prereq import requires
from tests.integration.pptx import (
    PROJECT_DIR, cleanup_dir, fresh_dir, has_libreoffice, run_cli, write_readme,
)

DIR = fresh_dir("test_fit_render")
TEMPLATE = PROJECT_DIR / "plugins/brand/skills/brand/brands/neutral/pptx/presentation.pptx"
EMU_PER_INCH = 914400
DPI = 100
NO_AUTOFIT = "{http://schemas.openxmlformats.org/drawingml/2006/main}noAutofit"


def _bullets(n: int) -> list[dict]:
    return [{"text": f"Short item {i}", "bullet": True} for i in range(n)]


def _deck(n: int):
    """A one-slide deck: Title and Content with `n` bullets at the inherited size, written as
    add-text writes them, with the template's normAutofit replaced by noAutofit so the renderer
    does not shrink the text. Returns the presentation and the body shape."""
    prs = Presentation(str(TEMPLATE))
    add_slides(prs, ["Title and Content"], None)
    ids = prs.slides._sldIdLst
    for sld_id in list(ids)[:-1]:
        ids.remove(sld_id)
    body = prs.slides[0].shapes[1]
    body.text_frame.clear()
    PresentationTextAdder()._add_paragraphs(body.text_frame, _bullets(n), 0,
                                            paragraph_base_sizes(body, _bullets(n)))
    body_pr = body.text_frame._txBody.bodyPr
    for child in list(body_pr):
        if child.tag.endswith("Autofit"):
            body_pr.remove(child)
    etree.SubElement(body_pr, NO_AUTOFIT)
    return prs, body


@requires(has_libreoffice(), "LibreOffice not installed")
class TestFitRender(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        write_readme(DIR,
            "Fitter against render: Title and Content body of the neutral template, one-line bullets\n"
            "at the inherited size, noAutofit.\n"
            "  fit/slide_01.png  : the most bullets the fitter accepts; all text inside the frame\n"
            "  over/slide_01.png : one bullet more; the last bullet below the frame")

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def _last_ink_and_bottom(self, name: str, n: int) -> tuple[int, float]:
        """Render `n` bullets; return the lowest dark pixel row under the body and the row of the
        frame's bottom inset, at DPI."""
        prs, body = _deck(n)
        deck = DIR / f"{name}.pptx"
        prs.save(str(deck))
        r = run_cli("export-slides", str(deck), str(DIR / name), "--dpi", str(DPI))
        self.assertEqual(r.returncode, 0, r.stderr)
        with Image.open(DIR / name / "slide_01.png") as im:
            gray = im.convert("L")
        x0 = int(body.left / EMU_PER_INCH * DPI) + 2
        x1 = int((body.left + body.width) / EMU_PER_INCH * DPI) - 2
        top = int(body.top / EMU_PER_INCH * DPI)
        ink = [y for y in range(top, gray.height) for x in range(x0, x1, 2) if gray.getpixel((x, y)) < 128]
        inset_bottom = (body.top + body.height - body.text_frame.margin_bottom) / EMU_PER_INCH * DPI
        return max(ink), inset_bottom

    def test_fitter_limit_matches_render(self) -> None:
        """The largest bullet count the fitter accepts at the inherited size renders with its last
        line inside the frame's bottom inset, and one more bullet renders past it. Guards the
        text-height rule (1.2 x size per line, inherited spcBef between paragraphs) against what
        LibreOffice draws."""
        prs, body = _deck(1)
        size = paragraph_base_sizes(body, _bullets(1))[0]
        fitter = TextFitter(min_font_size=size)
        accepted = max(n for n in range(1, 30) if fitter.find_fitting_reduction(
            body, {"paragraphs": _bullets(n)}, "slide-0", "shape-1").fits)

        fit_ink, bottom = self._last_ink_and_bottom("fit", accepted)
        self.assertLessEqual(fit_ink, bottom, f"{accepted} accepted bullets render past the frame")
        over_ink, bottom = self._last_ink_and_bottom("over", accepted + 1)
        self.assertGreater(over_ink, bottom, f"{accepted + 1} bullets still render inside the frame")


if __name__ == "__main__":
    unittest.main()
