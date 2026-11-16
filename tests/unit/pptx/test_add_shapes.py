"""Unit tests for add-shapes.

Focus is the command's own logic: the
duplicate-key guard, the slide/type/coord validation rules, and — most
importantly — that a JSON spec is translated into the right shape properties
(fill, border, radius, arrow head, Calibri default). The property assertions
read the saved deck back so they verify the translation, not python-pptx.
"""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Pt

from pptx_tool.cmd_add_shapes import PresentationShapesAdder
from pptx_tool.cmd_new_deck import create_deck
from pptx_tool.exceptions import ValidationError


def _make_png(dir_path: str, name: str = "logo.png", size: tuple = (200, 80)) -> str:
    """Write a tiny solid-color PNG and return its path (200x80 -> 2.5 aspect)."""
    from PIL import Image

    path = str(Path(dir_path) / name)
    Image.new("RGB", size, (30, 120, 200)).save(path)
    return path


class TestDuplicateKeyGuard(unittest.TestCase):

    def test_duplicate_key_rejected(self) -> None:
        """cmd_add_shapes.PresentationShapesAdder._check_duplicate_keys raises ValidationError when
        the shapes JSON repeats a slide key. Guards against json.load silently keeping only the
        last list of a duplicate key."""
        pairs = [("slide-0", []), ("slide-0", [])]
        with self.assertRaises(ValidationError):
            PresentationShapesAdder._check_duplicate_keys(pairs)

    def test_unique_keys_ok(self) -> None:
        """PresentationShapesAdder._check_duplicate_keys returns the pairs as a dict when the keys
        are unique. Guards that the object_pairs_hook keeps every slide of a valid shapes file."""
        pairs = [("slide-0", []), ("slide-1", [])]
        result = PresentationShapesAdder._check_duplicate_keys(pairs)
        self.assertEqual(result, {"slide-0": [], "slide-1": []})


class TestValidation(unittest.TestCase):
    """One-slide deck (indices 0-0); everything else should be rejected."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        deck = str(Path(self.tmp.name) / "in.pptx")
        create_deck(deck, slides=1, size="16:9")
        self.prs = Presentation(deck)
        self.adder = PresentationShapesAdder()

    def _err(self, data: dict) -> str:
        with self.assertRaises(ValidationError) as ctx:
            self.adder._validate_shape_data(self.prs, data)
        return str(ctx.exception)

    def test_non_slide_key_rejected(self) -> None:
        """PresentationShapesAdder._validate_shape_data rejects a key that does not start with
        slide-. Guards the slide-N key format of the shapes JSON."""
        self._err({"sheet-0": [{"type": "rect", "left": 1, "top": 1, "width": 1, "height": 1}]})

    def test_out_of_range_slide_rejected(self) -> None:
        """PresentationShapesAdder._validate_shape_data rejects slide-5 on a one-slide deck. Guards
        the slide index range check before any shape is drawn."""
        self._err({"slide-5": [{"type": "rect", "left": 1, "top": 1, "width": 1, "height": 1}]})

    def test_unknown_type_lists_valid_types(self) -> None:
        """PresentationShapesAdder._validate_shape_data rejects a shape type not in VALID_TYPES.
        Guards the type check that names the allowed types."""
        # A helpful error must name the allowed types.
        with self.assertRaises(ValidationError):
            self.adder._validate_shape_data(
                self.prs, {"slide-0": [{"type": "triangle", "left": 1, "top": 1, "width": 1, "height": 1}]}
            )

    def test_line_missing_coords_rejected(self) -> None:
        """PresentationShapesAdder._validate_shape_data rejects a line without x2 and y2. Guards the
        endpoint coordinates required by line shapes."""
        self._err({"slide-0": [{"type": "line", "x1": 1, "y1": 1}]})  # missing x2/y2

    def test_autoshape_missing_coords_rejected(self) -> None:
        """PresentationShapesAdder._validate_shape_data rejects a rect without width and height.
        Guards the box coordinates required by autoshapes."""
        self._err({"slide-0": [{"type": "rect", "left": 1, "top": 1}]})  # missing width/height

    def test_image_missing_coords_rejected(self) -> None:
        """PresentationShapesAdder._validate_shape_data rejects an image without width. Guards the
        rule that an image needs left, top and width, height being optional."""
        # path present but width missing.
        img = _make_png(self.tmp.name)
        self._err({"slide-0": [{"type": "image", "path": img, "left": 1, "top": 1}]})

    def test_image_missing_file_rejected(self) -> None:
        """PresentationShapesAdder._validate_shape_data rejects an image whose path does not exist.
        Guards the file check before the deck is modified."""
        missing = str(Path(self.tmp.name) / "nope.png")
        self._err({"slide-0": [{"type": "image", "path": missing,
                                "left": 1, "top": 1, "width": 2}]})

    def test_chip_row_missing_chips_rejected(self) -> None:
        """PresentationShapesAdder._validate_shape_data rejects a chip_row without chips. Guards the
        required chips list of chip_row."""
        self._err({"slide-0": [{"type": "chip_row", "left": 1, "top": 1}]})

    def test_chip_row_chip_without_text_rejected(self) -> None:
        """PresentationShapesAdder._validate_shape_data rejects a chip without text. Guards the text
        each chip is sized by."""
        self._err({"slide-0": [{"type": "chip_row", "left": 1, "top": 1, "chips": [{"fill": "#fff"}]}]})

    def test_icon_label_missing_size_rejected(self) -> None:
        """PresentationShapesAdder._validate_shape_data rejects an icon_label with neither
        icon_height nor height. Guards the icon size icon_label needs to place its label."""
        img = _make_png(self.tmp.name)
        # no icon_height and no height
        self._err({"slide-0": [{"type": "icon_label", "path": img, "left": 1, "top": 1, "label": "x"}]})

    def test_icon_label_missing_label_rejected(self) -> None:
        """PresentationShapesAdder._validate_shape_data rejects an icon_label without label. Guards
        the required label text."""
        img = _make_png(self.tmp.name)
        self._err({"slide-0": [{"type": "icon_label", "path": img, "left": 1, "top": 1, "icon_height": 0.4}]})

    def test_icon_label_missing_file_rejected(self) -> None:
        """PresentationShapesAdder._validate_shape_data rejects an icon_label whose icon path does
        not exist. Guards the file check for icons."""
        missing = str(Path(self.tmp.name) / "nope.png")
        self._err({"slide-0": [{"type": "icon_label", "path": missing,
                                "left": 1, "top": 1, "icon_height": 0.4, "label": "x"}]})


class TestTranslation(unittest.TestCase):
    """Build shapes from JSON, reopen the deck, assert the properties landed."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.deck = str(Path(self.tmp.name) / "in.pptx")
        create_deck(self.deck, slides=1, size="16:9")

    def _build(self, shapes: list) -> Presentation:
        data_path = str(Path(self.tmp.name) / "shapes.json")
        out = str(Path(self.tmp.name) / "out.pptx")
        with open(data_path, "w") as f:
            json.dump({"slide-0": shapes}, f)
        PresentationShapesAdder().add_shapes(self.deck, data_path, out)
        return Presentation(out)

    def _first_shape(self, prs):
        return list(prs.slides[0].shapes)[0]

    def test_solid_fill_color(self) -> None:
        """PresentationShapesAdder.add_shapes sets a solid fill from a #RRGGBB fill value. Guards
        the hex colour mapping of shape fills."""
        prs = self._build([
            {"type": "rect", "left": 1, "top": 1, "width": 2, "height": 1, "fill": "#FFFFFF"}
        ])
        shp = self._first_shape(prs)
        self.assertEqual(shp.fill.fore_color.rgb, RGBColor.from_string("FFFFFF"))

    def test_fill_none_is_background(self) -> None:
        """PresentationShapesAdder.add_shapes maps fill "none" to a background (no) fill. Guards
        that "none" is not parsed as a colour or left at the theme default."""
        from pptx.enum.dml import MSO_FILL
        prs = self._build([
            {"type": "rect", "left": 1, "top": 1, "width": 2, "height": 1, "fill": "none"}
        ])
        self.assertEqual(self._first_shape(prs).fill.type, MSO_FILL.BACKGROUND)

    def test_border_color_and_weight(self) -> None:
        """PresentationShapesAdder.add_shapes applies the line colour and weight in points. Guards
        the border mapping of the line object."""
        prs = self._build([{
            "type": "rect", "left": 1, "top": 1, "width": 2, "height": 1,
            "line": {"color": "#E0E0E5", "weight": 1.0, "dash": "solid"},
        }])
        shp = self._first_shape(prs)
        self.assertEqual(shp.line.color.rgb, RGBColor.from_string("E0E0E5"))
        self.assertEqual(shp.line.width, Pt(1.0))

    def test_rounded_rect_radius(self) -> None:
        """PresentationShapesAdder.add_shapes sets a rounded_rect's radius as its first adjustment.
        Guards the radius mapping of rounded rectangles."""
        prs = self._build([{
            "type": "rounded_rect", "left": 1, "top": 1, "width": 2, "height": 1, "radius": 0.25,
        }])
        self.assertAlmostEqual(self._first_shape(prs).adjustments[0], 0.25, places=4)

    def test_shadow_off_writes_empty_effect_list(self) -> None:
        """PresentationShapesAdder.add_shapes writes an empty a:effectLst for shadow false. Guards
        the shadow removal; without it the theme's shadow applies."""
        prs = self._build([{
            "type": "rect", "left": 1, "top": 1, "width": 2, "height": 1, "shadow": False,
        }])
        self.assertIn("<a:effectLst/>", self._first_shape(prs)._element.xml)

    def test_text_defaults_to_calibri(self) -> None:
        """PresentationShapesAdder.add_shapes sets runs to Calibri when the text spec gives no font.
        Guards the default font of add-shapes text."""
        prs = self._build([{
            "type": "textbox", "left": 1, "top": 1, "width": 3, "height": 1,
            "text": {"paragraphs": [{"text": "Hi", "bold": True}]},
        }])
        run = self._first_shape(prs).text_frame.paragraphs[0].runs[0]
        self.assertEqual(run.text, "Hi")
        self.assertEqual(run.font.name, "Calibri")

    def test_arrow_sets_line_ends(self) -> None:
        """PresentationShapesAdder.add_shapes maps arrow "end" to a:tailEnd only, "start" to a:headEnd
        only and "both" to both; an unknown value prints a warning and adds neither. Guards the
        ARROW_MAP directions (OOXML's tailEnd is the line's end point) and the unknown-value branch of
        _apply_arrow."""
        cases = {"end": (False, True), "start": (True, False), "both": (True, True), "up": (False, False)}
        for arrow, (head, tail) in cases.items():
            with self.subTest(arrow=arrow):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    prs = self._build([{
                        "type": "line", "x1": 1, "y1": 1, "x2": 3, "y2": 1,
                        "line": {"color": "#C8C8CE", "weight": 1.0}, "arrow": arrow,
                    }])
                xml = self._first_shape(prs)._element.xml
                self.assertEqual("headEnd" in xml, head)
                self.assertEqual("tailEnd" in xml, tail)
                warned = "WARNING: Unknown arrow 'up' (use start/end/both)" in out.getvalue()
                self.assertEqual(warned, arrow == "up")

    def test_image_preserves_aspect_ratio_when_height_omitted(self) -> None:
        """PresentationShapesAdder.add_shapes computes an image's height from its pixel aspect ratio
        when only width is given. Guards undistorted images."""
        from pptx.util import Emu
        img = _make_png(self.tmp.name)  # 200x80 -> width:height 2.5:1
        prs = self._build([{"type": "image", "path": img, "left": 1, "top": 1, "width": 2.5}])
        pic = self._first_shape(prs)
        self.assertAlmostEqual(Emu(pic.width).inches, 2.5, places=3)
        self.assertAlmostEqual(Emu(pic.height).inches, 1.0, places=3)

    def test_image_honors_explicit_height(self) -> None:
        """PresentationShapesAdder.add_shapes uses an explicit image height instead of the aspect
        ratio. Guards that a given height overrides the computed one."""
        from pptx.util import Emu
        img = _make_png(self.tmp.name)
        prs = self._build([{"type": "image", "path": img,
                            "left": 1, "top": 1, "width": 2, "height": 0.5}])
        self.assertAlmostEqual(Emu(self._first_shape(prs).height).inches, 0.5, places=3)

    def test_chip_row_widths_track_text_with_equal_padding(self) -> None:
        """PresentationShapesAdder.add_shapes sizes each chip to measure.text_width of its text plus
        twice the padding. Guards chip widths that follow their text instead of a fixed width."""
        # Chips of very different text lengths each fit their own text with the
        # same horizontal padding (2 x padding beyond the rendered text width).
        from pptx.util import Emu
        from pptx_tool.measure import text_width

        pad = 0.15
        prs = self._build([{
            "type": "chip_row", "left": 0.5, "top": 0.5, "font_size": 12, "padding": pad,
            "chips": [{"text": "OK"}, {"text": "a much longer chip label"}, {"text": "mid"}],
        }])
        shapes = [s for s in prs.slides[0].shapes if s.has_text_frame]
        by_text = {s.text_frame.text: s for s in shapes}
        for text in ("OK", "a much longer chip label", "mid"):
            w = Emu(by_text[text].width).inches
            self.assertAlmostEqual(w, text_width(text, "Calibri", 12) + 2 * pad, places=2)

    def test_chip_row_packs_left_to_right(self) -> None:
        """PresentationShapesAdder.add_shapes places each chip at the previous chip's right edge
        plus gap, on the same row. Guards the horizontal packing of chip_row."""
        from pptx.util import Emu
        prs = self._build([{
            "type": "chip_row", "left": 0.5, "top": 0.5, "gap": 0.1,
            "chips": [{"text": "AAA"}, {"text": "BBB"}],
        }])
        chips = [s for s in prs.slides[0].shapes if s.has_text_frame]
        a = next(s for s in chips if s.text_frame.text == "AAA")
        b = next(s for s in chips if s.text_frame.text == "BBB")
        a_right = Emu(a.left).inches + Emu(a.width).inches
        self.assertAlmostEqual(Emu(b.left).inches, a_right + 0.1, places=2)
        self.assertEqual(Emu(a.top).inches, Emu(b.top).inches)  # same row

    def test_chip_row_wraps_at_max_width(self) -> None:
        """PresentationShapesAdder.add_shapes moves a chip that would exceed max_width to a new row
        at the row's left. Guards the wrap of chip_row."""
        from pptx.util import Emu
        from pptx_tool.measure import text_width
        first_w = text_width("AAA", "Calibri", 12) + 0.3
        prs = self._build([{
            "type": "chip_row", "left": 0.5, "top": 0.5, "font_size": 12, "padding": 0.15,
            "max_width": first_w + 0.05, "row_gap": 0.12, "height": 0.34,
            "chips": [{"text": "AAA"}, {"text": "BBB"}],
        }])
        chips = [s for s in prs.slides[0].shapes if s.has_text_frame]
        a = next(s for s in chips if s.text_frame.text == "AAA")
        b = next(s for s in chips if s.text_frame.text == "BBB")
        self.assertGreater(Emu(b.top).inches, Emu(a.top).inches)  # wrapped to next row
        self.assertAlmostEqual(Emu(b.left).inches, 0.5, places=3)  # back to row start

    def test_icon_label_icon_undistorted_and_label_after_icon(self) -> None:
        """PresentationShapesAdder.add_shapes keeps each icon's aspect ratio at the given
        icon_height and places the label at the icon's right edge plus gap. Guards a label offset
        that follows the icon width instead of a constant."""
        # Two icons of very different aspect ratios, one target height: both
        # render undistorted and the label sits at each icon's right edge + gap.
        from pptx.util import Emu
        from pptx.shapes.picture import Picture

        wide = _make_png(self.tmp.name, "wide.png", (300, 100))  # 3:1
        tall = _make_png(self.tmp.name, "tall.png", (100, 200))  # 1:2
        prs = self._build([
            {"type": "icon_label", "path": wide, "left": 0.5, "top": 1.0,
             "icon_height": 0.4, "gap": 0.2, "label": "wide"},
            {"type": "icon_label", "path": tall, "left": 0.5, "top": 2.0,
             "icon_height": 0.4, "gap": 0.2, "label": "tall"},
        ])
        shapes = list(prs.slides[0].shapes)
        pics = [s for s in shapes if isinstance(s, Picture)]
        labels = {s.text_frame.text: s for s in shapes
                  if not isinstance(s, Picture) and s.has_text_frame}

        for pic, ratio in ((pics[0], 3.0), (pics[1], 0.5)):
            self.assertAlmostEqual(Emu(pic.width).inches / Emu(pic.height).inches, ratio, places=2)

        for pic, txt in ((pics[0], "wide"), (pics[1], "tall")):
            icon_right = Emu(pic.left).inches + Emu(pic.width).inches
            self.assertAlmostEqual(Emu(labels[txt].left).inches, icon_right + 0.2, places=2)

        # The two label offsets differ — offset adapts to icon width, not a constant.
        self.assertNotAlmostEqual(
            Emu(labels["wide"].left).inches, Emu(labels["tall"].left).inches, places=1
        )


if __name__ == "__main__":
    unittest.main()
