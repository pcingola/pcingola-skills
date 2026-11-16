"""Draw free native shapes at explicit inch coordinates onto existing slides.

The shape data JSON uses slide-N keys, each a list of shape specs. Every shape is
a real, editable PowerPoint shape. Supported types: rect, rounded_rect, oval,
textbox, line, image. All coordinates are in inches. The `image` type places a
real, editable picture object (from a PNG/JPG file) — not a flattened slide.
"""

import json
import sys
from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches

from PIL import Image as PILImage

from .exceptions import ValidationError
from .measure import text_width
from .text_formatters import ParagraphProcessor, ShapeFormatter


# JSON type -> MSO_SHAPE autoshape enum (line/textbox handled separately)
AUTOSHAPE_MAP = {
    "rect": MSO_SHAPE.RECTANGLE,
    "rounded_rect": MSO_SHAPE.ROUNDED_RECTANGLE,
    "oval": MSO_SHAPE.OVAL,
}
# chip_row / icon_label are computed-layout types: they expand into the same
# native shapes above, positioned from the actual rendered size of their text
# (chip_row) or source image (icon_label) rather than from caller-supplied coords.
COMPUTED_TYPES = ["chip_row", "icon_label"]
VALID_TYPES = sorted(list(AUTOSHAPE_MAP) + ["textbox", "line", "image"] + COMPUTED_TYPES)

DEFAULT_RADIUS = 0.08

# chip_row defaults (inches unless noted)
CHIP_DEFAULTS = {
    "height": 0.34,
    "radius": 0.5,      # full pill: fraction of the shorter (vertical) side
    "gap": 0.12,        # horizontal gap between chips
    "row_gap": 0.12,    # vertical gap between wrapped rows
    "padding": 0.14,    # horizontal padding each side of the text
    "font_name": "Calibri",
    "font_size": 11,
    "bold": False,
    "fill": "#EEEEEE",
    "text_color": "#000000",
}

# icon_label defaults
ICON_LABEL_DEFAULTS = {
    "gap": 0.12,        # gap between icon right edge and label left edge
    "valign": "MIDDLE",
    "font_name": "Calibri",
    "font_size": 18,
}

# arrow direction -> line-end tags (headEnd = line start, tailEnd = line end)
ARROW_MAP = {
    "start": ["a:headEnd"],
    "end": ["a:tailEnd"],
    "both": ["a:headEnd", "a:tailEnd"],
}


class PresentationShapesAdder:
    """Adds free native shapes and file-backed pictures to presentations from JSON definitions."""

    def add_shapes(self, input_path: str, shape_data_path: str, output_path: str) -> None:
        prs = Presentation(input_path)
        shape_data = self._load_shape_data(shape_data_path)
        self._validate_shape_data(prs, shape_data)

        per_slide = {}

        for slide_key, shapes in shape_data.items():
            slide_index = int(slide_key.split("-")[1])
            slide = prs.slides[slide_index]

            shape_list = shapes if isinstance(shapes, list) else [shapes]
            for shape_spec in shape_list:
                self._add_shape(slide, shape_spec)
            per_slide[slide_key] = len(shape_list)

        prs.save(output_path)
        print(f"Saved presentation to: {output_path}")
        for slide_key in sorted(per_slide, key=lambda k: int(k.split("-")[1])):
            print(f"  {slide_key}: {per_slide[slide_key]} shape(s) added")

    def _load_shape_data(self, json_path: str) -> dict:
        with open(json_path, "r") as f:
            return json.load(f, object_pairs_hook=self._check_duplicate_keys)

    @staticmethod
    def _check_duplicate_keys(pairs: list[tuple]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValidationError(f"Duplicate key found in JSON: '{key}'")
            result[key] = value
        return result

    def _validate_shape_data(self, prs, shape_data: dict) -> None:
        errors = []
        slide_count = len(prs.slides)

        for slide_key, shapes in shape_data.items():
            if not slide_key.startswith("slide-"):
                errors.append(f"Invalid key '{slide_key}': must be 'slide-N'")
                continue
            try:
                slide_index = int(slide_key.split("-")[1])
            except (IndexError, ValueError):
                errors.append(f"Invalid slide key '{slide_key}'")
                continue
            if slide_index < 0 or slide_index >= slide_count:
                errors.append(f"Slide index {slide_index} out of range (0-{slide_count - 1})")
                continue

            shape_list = shapes if isinstance(shapes, list) else [shapes]
            for i, spec in enumerate(shape_list):
                prefix = f"{slide_key} shape {i}"
                stype = spec.get("type")
                if stype not in VALID_TYPES:
                    errors.append(
                        f"{prefix}: invalid or missing 'type' {stype!r}. "
                        f"Valid types: {', '.join(VALID_TYPES)}"
                    )
                    continue
                if stype == "line":
                    missing = [k for k in ("x1", "y1", "x2", "y2") if k not in spec]
                    if missing:
                        errors.append(f"{prefix} (line): missing coords {missing}")
                elif stype == "image":
                    missing = [k for k in ("path", "left", "top", "width") if k not in spec]
                    if missing:
                        errors.append(f"{prefix} (image): missing {missing}")
                    elif not Path(spec["path"]).is_file():
                        errors.append(f"{prefix} (image): file not found: {spec['path']}")
                elif stype == "chip_row":
                    missing = [k for k in ("left", "top") if k not in spec]
                    if missing:
                        errors.append(f"{prefix} (chip_row): missing {missing}")
                    chips = spec.get("chips")
                    if not isinstance(chips, list) or not chips:
                        errors.append(f"{prefix} (chip_row): 'chips' must be a non-empty list")
                    else:
                        for j, chip in enumerate(chips):
                            if not isinstance(chip, dict) or "text" not in chip:
                                errors.append(f"{prefix} (chip_row): chip {j} missing 'text'")
                elif stype == "icon_label":
                    missing = [k for k in ("path", "left", "top") if k not in spec]
                    if missing:
                        errors.append(f"{prefix} (icon_label): missing {missing}")
                    elif not Path(spec["path"]).is_file():
                        errors.append(f"{prefix} (icon_label): file not found: {spec['path']}")
                    if "icon_height" not in spec and "height" not in spec:
                        errors.append(f"{prefix} (icon_label): need 'icon_height' or 'height'")
                    if "label" not in spec and "text" not in spec:
                        errors.append(f"{prefix} (icon_label): need 'label' or 'text'")
                else:
                    missing = [k for k in ("left", "top", "width", "height") if k not in spec]
                    if missing:
                        errors.append(f"{prefix} ({stype}): missing coords {missing}")

        if errors:
            print("ERROR: Invalid shape data:")
            for error in errors:
                print(f"  - {error}")
            raise ValidationError(f"Found {len(errors)} validation error(s)")

    def _add_shape(self, slide, spec: dict) -> None:
        stype = spec["type"]
        if stype == "line":
            self._add_line(slide, spec)
        elif stype == "textbox":
            self._add_textbox(slide, spec)
        elif stype == "image":
            self._add_image(slide, spec)
        elif stype == "chip_row":
            self._add_chip_row(slide, spec)
        elif stype == "icon_label":
            self._add_icon_label(slide, spec)
        else:
            self._add_autoshape(slide, spec)

    def _add_autoshape(self, slide, spec: dict) -> None:
        shape = slide.shapes.add_shape(
            AUTOSHAPE_MAP[spec["type"]],
            Inches(spec["left"]), Inches(spec["top"]),
            Inches(spec["width"]), Inches(spec["height"]),
        )

        if spec["type"] == "rounded_rect":
            radius = spec.get("radius", DEFAULT_RADIUS)
            try:
                shape.adjustments[0] = radius
            except Exception:
                pass

        _apply_fill(shape, spec.get("fill"))
        _apply_line(shape, spec.get("line"), default_none=True)
        _apply_shadow(shape, spec.get("shadow", False))

        if "text" in spec:
            _apply_text(shape, spec["text"])

    def _add_textbox(self, slide, spec: dict) -> None:
        shape = slide.shapes.add_textbox(
            Inches(spec["left"]), Inches(spec["top"]),
            Inches(spec["width"]), Inches(spec["height"]),
        )
        # Textboxes have no fill/line by default; honor them only if explicitly given.
        if "fill" in spec:
            _apply_fill(shape, spec.get("fill"))
        if "line" in spec:
            _apply_line(shape, spec.get("line"), default_none=True)
        _apply_shadow(shape, spec.get("shadow", False))

        if "text" in spec:
            _apply_text(shape, spec["text"])

    def _add_image(self, slide, spec: dict) -> None:
        # Real, editable picture object; works on a blank slide (no placeholder needed).
        # Width is required; height omitted -> python-pptx preserves the aspect ratio.
        height = Inches(spec["height"]) if "height" in spec else None
        slide.shapes.add_picture(
            spec["path"],
            Inches(spec["left"]), Inches(spec["top"]),
            Inches(spec["width"]), height,
        )

    def _add_line(self, slide, spec: dict) -> None:
        connector = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT,
            Inches(spec["x1"]), Inches(spec["y1"]),
            Inches(spec["x2"]), Inches(spec["y2"]),
        )
        # Connectors keep their default line unless a spec is provided.
        if "line" in spec:
            _apply_line(connector, spec.get("line"), default_none=False)
        _apply_shadow(connector, spec.get("shadow", False))

        arrow = spec.get("arrow")
        if arrow:
            _apply_arrow(connector, arrow)

    def _add_chip_row(self, slide, spec: dict) -> None:
        """Expand a chip_row into a packed row of rounded_rect pill shapes.

        Each chip's width is the rendered width of its own text (shared measurer
        in measure) plus equal horizontal padding, so every chip fits its
        text with the same padding. Chips pack left-to-right by the configured
        gap; with `max_width` set, a chip that would overflow the row starts a
        new row `row_gap` below. This is sugar over hand-placing N rounded_rects
        — same fill/border/text conventions, no new visual primitive.
        """
        d = CHIP_DEFAULTS
        left0 = spec["left"]
        top = spec["top"]
        gap = spec.get("gap", d["gap"])
        row_gap = spec.get("row_gap", d["row_gap"])
        padding = spec.get("padding", d["padding"])
        height = spec.get("height", d["height"])
        radius = spec.get("radius", d["radius"])
        max_width = spec.get("max_width")
        font_name = spec.get("font_name", d["font_name"])
        font_size = spec.get("font_size", d["font_size"])
        bold = spec.get("bold", d["bold"])
        default_fill = spec.get("fill", d["fill"])
        default_text_color = spec.get("text_color", d["text_color"])
        line = spec.get("line")
        shadow = spec.get("shadow", False)

        x = left0
        y = top
        for chip in spec["chips"]:
            text = chip["text"]
            width = text_width(text, font_name, font_size) + 2 * padding

            # Wrap to a new row if this chip would exceed max_width — but never
            # wrap the first chip of a row (a lone over-wide chip must still land).
            if max_width is not None and x > left0 and (x - left0) + width > max_width:
                x = left0
                y += height + row_gap

            shape = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE,
                Inches(x), Inches(y), Inches(width), Inches(height),
            )
            try:
                shape.adjustments[0] = radius
            except Exception:
                pass

            _apply_fill(shape, chip.get("fill", default_fill))
            _apply_line(shape, line, default_none=True)
            _apply_shadow(shape, shadow)
            _apply_text(shape, {
                "vertical_alignment": "MIDDLE",
                "wrap": False,
                "paragraphs": [{
                    "text": text,
                    "bold": bold,
                    "font_size": font_size,
                    "font_name": font_name,
                    "color": chip.get("text_color", default_text_color),
                    "alignment": "CENTER",
                }],
            })

            x += width + gap

    def _add_icon_label(self, slide, spec: dict) -> None:
        """Place an icon image and a label as one unit, label auto-positioned.

        The icon's on-slide width is derived from the source file's own pixel
        aspect ratio scaled to the target height, so the icon never distorts when
        its source crop changes. The label's left edge is the icon's computed
        right edge plus `gap` — never a fixed offset — so it adapts to the icon.
        """
        d = ICON_LABEL_DEFAULTS
        path = spec["path"]
        left = spec["left"]
        top = spec["top"]
        icon_height = spec.get("icon_height", spec.get("height"))
        row_height = spec.get("height", icon_height)
        gap = spec.get("gap", d["gap"])
        valign = str(spec.get("valign", d["valign"])).upper()

        with PILImage.open(path) as im:
            px_w, px_h = im.size
        icon_width = icon_height * (px_w / px_h)

        # Vertically place the icon within the row per valign.
        if valign == "MIDDLE":
            icon_top = top + (row_height - icon_height) / 2
        elif valign == "BOTTOM":
            icon_top = top + (row_height - icon_height)
        else:  # TOP
            icon_top = top
        slide.shapes.add_picture(
            path, Inches(left), Inches(icon_top), Inches(icon_width), Inches(icon_height),
        )

        # Build the label's text object: either an explicit `text` object (full
        # paragraphs schema, like every other shape) or convenience label keys.
        if isinstance(spec.get("text"), dict):
            text_def = dict(spec["text"])
            text_def.setdefault("vertical_alignment", valign)
        else:
            para = {"text": spec.get("label", ""), "font_name": spec.get("font_name", d["font_name"])}
            if "font_size" in spec:
                para["font_size"] = spec["font_size"]
            if "bold" in spec:
                para["bold"] = spec["bold"]
            if "color" in spec:
                para["color"] = spec["color"]
            text_def = {
                "vertical_alignment": valign,
                "wrap": spec.get("wrap", False),
                "paragraphs": [para],
            }

        # Label box width: explicit, or the natural single-line width of the
        # first paragraph's text (so a one-line label is not clipped).
        if "label_width" in spec:
            label_width = spec["label_width"]
        else:
            p0 = text_def["paragraphs"][0]
            label_width = text_width(
                p0.get("text", ""), p0.get("font_name", d["font_name"]),
                p0.get("font_size", d["font_size"]),
            ) + 0.15

        label_left = left + icon_width + gap
        textbox = slide.shapes.add_textbox(
            Inches(label_left), Inches(top), Inches(label_width), Inches(row_height),
        )
        _apply_text(textbox, text_def)


def _apply_fill(shape, fill) -> None:
    """Solid hex fill, or no fill for 'none'/absent. Never leaves the theme default.

    Translates add-shapes' `fill` (hex string / 'none') into the shared
    ShapeFormatter key set so add-shapes and add-text apply fills through one path.
    """
    if fill is None or (isinstance(fill, str) and fill.lower() == "none"):
        ShapeFormatter.apply_fill(shape, {"fill_type": "NONE"})
    else:
        ShapeFormatter.apply_fill(shape, {"fill_type": "SOLID", "fill_color": fill})


def _apply_line(shape, line, default_none: bool) -> None:
    """Apply border/line styling from a {color, weight, dash} dict.

    'none' or absent removes the line when default_none is True (rects/ovals/textboxes);
    for connectors (default_none False) an absent spec leaves the native default line.
    Translates into the shared ShapeFormatter border key set — one code path with add-text.
    """
    if line is None or (isinstance(line, str) and line.lower() == "none"):
        if default_none:
            ShapeFormatter.apply_border(shape, {"border_visible": False})
        return

    props = {"border_visible": True}
    color = line.get("color")
    if color and str(color).lower() != "none":
        props["border_color"] = color
    if line.get("weight") is not None:
        props["border_weight_pt"] = line.get("weight")
    if line.get("dash"):
        props["border_dash"] = line.get("dash")
    ShapeFormatter.apply_border(shape, props)


def _apply_shadow(shape, shadow_on) -> None:
    """Default off. Leave the inherited default only when shadow is true.

    `shape.shadow.inherit = False` alone only writes an empty <a:effectLst/>
    override. Autoshapes (rect/rounded_rect/oval) from the blank new-deck
    template also carry a <p:style><a:effectRef idx="N"> theme reference, and
    LibreOffice (and PowerPoint in some cases) still renders that inherited
    shadow despite the empty override. Neutralize the reference itself
    (idx="0" = no effect style) rather than relying on the override alone.
    """
    if shadow_on:
        return
    try:
        shape.shadow.inherit = False
    except Exception:
        pass
    try:
        style = shape._element.find(qn("p:style"))
        if style is not None:
            effect_ref = style.find(qn("a:effectRef"))
            if effect_ref is not None:
                effect_ref.set("idx", "0")
    except Exception:
        pass


def _apply_arrow(connector, arrow: str) -> None:
    """Append triangle line-end(s) to the connector's <a:ln> element."""
    tags = ARROW_MAP.get(str(arrow).lower())
    if not tags:
        print(f"  WARNING: Unknown arrow '{arrow}' (use start/end/both)")
        return
    ln = connector.line._get_or_add_ln()
    for tag in tags:
        el = OxmlElement(tag)
        el.set("type", "triangle")
        ln.append(el)


def _apply_text(shape, text_def: dict) -> None:
    """Fill a shape's text frame from a paragraphs spec, reusing the shared formatters."""
    tf = shape.text_frame
    tf.auto_size = MSO_AUTO_SIZE.NONE

    processor = ParagraphProcessor()
    paragraphs = text_def.get("paragraphs", [])
    for i, para in enumerate(paragraphs):
        para = dict(para)
        para.setdefault("font_name", "Calibri")
        paragraph = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        processor.apply_properties(paragraph, para)

    # Translate text-frame keys to ShapeFormatter's expected names.
    tf_props = {}
    if "vertical_alignment" in text_def:
        tf_props["vertical_alignment"] = text_def["vertical_alignment"]
    if "wrap" in text_def:
        tf_props["word_wrap"] = text_def["wrap"]
    margins = text_def.get("margins")
    if margins:
        for jk, sk in (
            ("top", "text_margin_top"),
            ("left", "text_margin_left"),
            ("bottom", "text_margin_bottom"),
            ("right", "text_margin_right"),
        ):
            if jk in margins:
                tf_props[sk] = margins[jk]
    if tf_props:
        ShapeFormatter.apply_text_frame_properties(shape, tf_props)


def run_add_shapes(args) -> None:
    """Entry point from CLI dispatcher."""
    input_pptx = Path(args.input)
    shape_data_json = Path(args.shape_data)
    output_pptx = Path(args.output)

    if not input_pptx.exists():
        print(f"Error: Input file '{input_pptx}' not found")
        sys.exit(1)

    if not shape_data_json.exists():
        print(f"Error: Shape data JSON file '{shape_data_json}' not found")
        sys.exit(1)

    try:
        adder = PresentationShapesAdder()
        adder.add_shapes(str(input_pptx), str(shape_data_json), str(output_pptx))
    except ValidationError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
