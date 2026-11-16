"""Unit tests for the agreement of the add-text fitter and the inventory's overflow check: on real text
boxes and template placeholders, text the fitter accepts is never flagged as overflowing, and text
it rejects is flagged by the same amount. The text-height rule is in docs/pptx.md, "Text
measurement and fitting"; tests/integration/pptx/test_fit_render.py checks it against renders."""
import tempfile
import unittest
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.util import Inches

from pptx_tool.cmd_add_slide import add_slides
from pptx_tool.cmd_add_text import PresentationTextAdder
from pptx_tool.cmd_edit import apply_operations
from pptx_tool.cmd_extract_shapes import calculate_frame_overflow, extract_text
from pptx_tool.text_fitting import TextFitter, paragraph_base_sizes
from pptx_tool.text_metrics import inherited_font_size, shape_base_font_size

TEMPLATE = (Path(__file__).resolve().parents[3]
            / "plugins/brand/skills/brand/brands/neutral/pptx/presentation.pptx")
WORD_COUNTS = range(2, 80, 3)


class TestFitOverflowAgreement(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "deck.pptx"

    def _agree(self, prs, shape_index: int, paragraphs: list[dict], label: str) -> bool:
        """Fit `paragraphs` into shape `shape_index` of slide 0 without reduction, write them as
        add-text does, save, reload, and assert both checks give the same verdict and overflow.
        Returns the fitter's verdict."""
        shape = prs.slides[0].shapes[shape_index]
        base = max(p.get("font_size", shape_base_font_size(shape)) for p in paragraphs)
        result = TextFitter(min_font_size=base).find_fitting_reduction(
            shape, {"paragraphs": paragraphs}, "slide-0", "shape-x")
        self.assertEqual(result.reduction, 0)

        shape.text_frame.clear()
        PresentationTextAdder()._add_paragraphs(
            shape.text_frame, paragraphs, 0, paragraph_base_sizes(shape, paragraphs))
        prs.save(str(self.path))
        written = Presentation(str(self.path)).slides[0].shapes[shape_index]
        flagged = calculate_frame_overflow(written)

        self.assertEqual(result.fits, flagged is None,
                         f"{label}: fitter fits={result.fits}, overflow check={flagged}")
        if flagged is not None:
            self.assertAlmostEqual(result.overflow_inches, round(flagged, 2), places=2, msg=label)
        return result.fits

    def test_explicit_size_text_box(self) -> None:
        """A 3 x 1 in text box with 18 pt text of growing length: the fitter verdict equals the
        overflow check on the written deck at every length, and both verdicts occur. Guards the
        old split of 1.4x line height and 95% height in the fitter against 1.0x in the check."""
        verdicts = set()
        for n in WORD_COUNTS:
            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            slide.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1))
            text = " ".join(["measured"] * n)
            verdicts.add(self._agree(prs, 0, [{"text": text, "font_size": 18}], f"{n} words"))
        self.assertEqual(verdicts, {True, False})

    def test_bullets_and_spacing(self) -> None:
        """Bulleted paragraphs with space_after in a 4 x 2 in box: same verdict and overflow from
        both checks. Guards the bullet margin and spacing the fitter assumed but never wrote."""
        verdicts = set()
        for n in range(1, 12):
            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(2))
            paragraphs = [{"text": f"Point {i} carries a few words", "bullet": True,
                           "font_size": 16, "space_after": 4} for i in range(n)]
            verdicts.add(self._agree(prs, 0, paragraphs, f"{n} bullets"))
        self.assertEqual(verdicts, {True, False})

    def test_inherited_size_placeholder(self) -> None:
        """Paragraphs without font_size in the OBJECT placeholder of the neutral template's Title and
        Content layout: the fitter measures at the inherited size, the written runs carry no size,
        and the overflow check resolves the same inherited size, so the verdicts match. Guards the
        old 18 pt fallback of the overflow check on inherited-size text."""
        verdicts = set()
        for n in range(1, 16):
            prs = Presentation(str(TEMPLATE))
            add_slides(prs, ["Title and Content"], None)
            body = prs.slides[0].shapes[1]
            self.assertNotEqual(inherited_font_size(body, "OBJECT"), 18.0)
            paragraphs = [{"text": f"Item {i} with enough words to wrap across the placeholder width once"}
                          for i in range(n)]
            verdicts.add(self._agree(prs, 1, paragraphs, f"{n} inherited paragraphs"))
        self.assertEqual(verdicts, {True, False})

    def test_template_bullet_count_follows_inherited_spacing(self) -> None:
        """At the inherited 32 pt, the fitter accepts as many one-line bullets in the Title and
        Content body as the template's own values allow: n lines of 1.2 x size plus spcBef (a
        percentage of the size, from the master bodyStyle) between paragraphs, within the usable
        height plus the 0.05 in tolerance. Guards the inherited spcBef the fitter used to ignore,
        which let it accept one bullet more than the frame holds."""
        ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main",
              "p": "http://schemas.openxmlformats.org/presentationml/2006/main"}

        def xp(element, path: str) -> list:
            return etree.XPath(path, namespaces=ns)(element)

        prs = Presentation(str(TEMPLATE))
        add_slides(prs, ["Title and Content"], None)
        body = prs.slides[-1].shapes[1]
        base = body._base_placeholder
        while base is not None:  # layout and master placeholders leave level 1 to the master bodyStyle
            self.assertFalse(xp(base._element, "./p:txBody/a:lstStyle/a:lvl1pPr/"
                                "*[self::a:spcBef or self::a:lnSpc or self::a:defRPr]"))
            base = getattr(base, "_base_placeholder", None)
        lvl1 = xp(prs.slide_master._element, "./p:txStyles/p:bodyStyle/a:lvl1pPr")[0]
        self.assertFalse(xp(lvl1, "./a:lnSpc"))
        size = int(xp(lvl1, "./a:defRPr/@sz")[0]) / 100
        before = int(xp(lvl1, "./a:spcBef/a:spcPct/@val")[0]) / 100000 * size
        tf = body.text_frame
        usable_pt = (body.height - tf.margin_top - tf.margin_bottom) / 914400 * 72 + 0.05 * 72

        expected = max(n for n in range(1, 30) if n * 1.2 * size + (n - 1) * before <= usable_pt)
        without_spacing = max(n for n in range(1, 30) if n * 1.2 * size <= usable_pt)
        self.assertGreater(without_spacing, expected)

        fitter = TextFitter(min_font_size=size)
        accepted = [n for n in range(1, 30) if fitter.find_fitting_reduction(
            body, {"paragraphs": [{"text": f"Short item {i}", "bullet": True} for i in range(n)]},
            "slide-0", "shape-1").fits]
        self.assertEqual(max(accepted), expected)

    def test_add_text_reduction_is_not_flagged(self) -> None:
        """add-text shrinks overflowing inherited-size bullets, and the inventory of the written deck
        flags no frame overflow on that shape. Guards a fitted size reported as overflowing."""
        bullets = [{"text": f"Point {i} with enough words to wrap across the placeholder width once",
                    "bullet": True} for i in range(8)]
        apply_operations(TEMPLATE, self.path, [
            {"action": "add-slide", "layouts": ["Title and Content"]},
            {"action": "add-text", "data": {"slide-0": {"shape-1": {"paragraphs": bullets}}}},
        ])
        shape = extract_text(self.path)["slide-0"]["shape-1"]
        self.assertTrue(any(run.font.size for p in shape.shape.text_frame.paragraphs for run in p.runs))
        self.assertIsNone(shape.frame_overflow_bottom)


if __name__ == "__main__":
    unittest.main()
