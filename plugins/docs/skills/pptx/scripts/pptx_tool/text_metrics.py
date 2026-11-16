"""The one text-height model of a text frame, shared by overflow detection and add-text fitting.

`calculate_frame_overflow` (the inventory's overflow check, on a written deck) and `TextFitter`
(add-text, on text data before writing) both build `ParagraphMetrics` and call `text_height`,
`usable_box` and `overflow_inches` here, so they apply the same rule:

- style chain (`style_chain`): a paragraph property comes from the nearest of the paragraph's own
  pPr, the shape's lstStyle, the layout and master placeholder lstStyles, then the master
  titleStyle/bodyStyle/otherStyle (placeholders) or the presentation defaultTextStyle (other
  shapes), at the paragraph's level;
- font size: the first run's explicit size, else the chain's defRPr size, else 32 pt for
  TITLE/CENTER_TITLE and 18 pt for anything else;
- font name: the first run's explicit name, else Arial;
- line pitch: the chain's lnSpc in points, else its lnSpc percentage times `LINE_HEIGHT` (1.2)
  times the font size, 1.2 times the font size when unset; an empty paragraph takes one line;
- spacing: the chain's spcBef and spcAft, in points or as a percentage of the font size, counted
  between paragraphs only (not before the first nor after the last);
- width: frame width minus the left and right insets, minus the chain's left margin (marL);
  `measure.measure_text_lines` wraps text in that width, measuring at size * 96/72 pixels;
- usable height: frame height minus the top and bottom insets;
- overflow: text height minus usable height; a shape overflows when that exceeds
  `OVERFLOW_TOLERANCE_INCHES`, and the fitter accepts a size exactly when it does not.
"""

import re
from dataclasses import dataclass

from lxml import etree

from .common import EMU_PER_INCH, POINTS_PER_INCH
from .measure import measure_text_lines

LINE_HEIGHT = 1.2  # single line spacing as a multiple of the font size
DEFAULT_FONT_NAME = "Arial"
DEFAULT_FONT_SIZE = 18.0
DEFAULT_TITLE_FONT_SIZE = 32.0
OVERFLOW_TOLERANCE_INCHES = 0.05
MIN_TEXT_WIDTH_INCHES = 0.1
BULLET_MARGIN_EM = 1.6  # left margin per bullet level, in multiples of the font size
BULLET_HANGING_EM = 0.8  # hanging indent of a bullet, in multiples of the font size
EMU_PER_POINT = 12700

TITLE_PLACEHOLDER_TYPES = {"TITLE", "CENTER_TITLE"}
BODY_PLACEHOLDER_TYPES = {"BODY", "SUBTITLE", "OBJECT", "VERTICAL_BODY", "VERTICAL_OBJECT"}
MARGIN_KEYS = ("text_margin_left", "text_margin_right", "text_margin_top", "text_margin_bottom")

_LINE_BREAK = re.compile(r"[\n\v]")
_NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
}


def _xpath(element, path: str) -> list:
    """`path` evaluated on any lxml element (python-pptx oxml class or plain) with the a: and p:
    prefixes bound."""
    return etree._Element.xpath(element, path, namespaces=_NS)


@dataclass(frozen=True)
class ParagraphMetrics:
    """What the height of one paragraph depends on. Sizes and spacings in points, margin in inches."""
    text: str
    font_size: float
    font_name: str = DEFAULT_FONT_NAME
    left_margin: float = 0.0
    line_spacing_pt: float | None = None
    line_spacing_lines: float | None = None
    space_before: float = 0.0
    space_after: float = 0.0

    def line_count(self, frame_width: float) -> int:
        """Wrapped lines in a frame `frame_width` inches wide (insets already removed)."""
        width = max(MIN_TEXT_WIDTH_INCHES, frame_width - self.left_margin)
        return sum(measure_text_lines(segment, self.font_name, self.font_size, width)
                   for segment in _LINE_BREAK.split(self.text))

    def line_pitch(self) -> float:
        """Distance between baselines, in points."""
        if self.line_spacing_pt is not None:
            return self.line_spacing_pt
        return (self.line_spacing_lines or 1.0) * LINE_HEIGHT * self.font_size

    def height(self, frame_width: float) -> float:
        """Height in inches, spacing before and after included."""
        points = self.line_count(frame_width) * self.line_pitch() + self.space_before + self.space_after
        return points / POINTS_PER_INCH


def text_height(paragraphs: list[ParagraphMetrics], frame_width: float) -> float:
    """Height in inches of the paragraphs in a frame `frame_width` wide; 0 when none has text.

    Spacing counts only between paragraphs: LibreOffice renders the first paragraph at the top
    inset whatever its spcBef, and the last paragraph's spcAft holds no text."""
    if not any(p.text.strip() for p in paragraphs):
        return 0.0
    outer = (paragraphs[0].space_before + paragraphs[-1].space_after) / POINTS_PER_INCH
    return sum(p.height(frame_width) for p in paragraphs) - outer


def overflow_inches(paragraphs: list[ParagraphMetrics], usable_width: float, usable_height: float) -> float:
    """Text height minus usable height, in inches; negative when the text fits with room left."""
    return text_height(paragraphs, usable_width) - usable_height


def overflows(overflow: float) -> bool:
    """The one overflow decision: more than `OVERFLOW_TOLERANCE_INCHES` past the usable height."""
    return overflow > OVERFLOW_TOLERANCE_INCHES


def usable_box(shape, margin_overrides: dict | None = None) -> tuple[float, float]:
    """Usable (width, height) in inches inside `shape`'s text insets.

    The insets are the text frame's (python-pptx gives 0.1 in left/right and 0.05 in top/bottom when
    the shape sets none); `margin_overrides` maps `text_margin_left/right/top/bottom` in inches to
    insets add-text is about to write."""
    tf = shape.text_frame
    margins = {
        "text_margin_left": tf.margin_left / EMU_PER_INCH,
        "text_margin_right": tf.margin_right / EMU_PER_INCH,
        "text_margin_top": tf.margin_top / EMU_PER_INCH,
        "text_margin_bottom": tf.margin_bottom / EMU_PER_INCH,
    }
    for key in MARGIN_KEYS:
        if margin_overrides and margin_overrides.get(key) is not None:
            margins[key] = margin_overrides[key]
    width = shape.width / EMU_PER_INCH - margins["text_margin_left"] - margins["text_margin_right"]
    height = shape.height / EMU_PER_INCH - margins["text_margin_top"] - margins["text_margin_bottom"]
    return width, height


def bullet_margin_emu(font_size: float, level: int) -> tuple[int, int]:
    """The (marL, indent) add-text writes for a bullet at `font_size` and `level`, in EMU."""
    left = int(font_size * BULLET_MARGIN_EM * (1 + level) * EMU_PER_POINT)
    hanging = int(-font_size * BULLET_HANGING_EM * EMU_PER_POINT)
    return left, hanging


def get_placeholder_type(shape) -> str | None:
    """Placeholder type name of a shape (TITLE, BODY, ...), or None for a non-placeholder."""
    try:
        if hasattr(shape, "is_placeholder") and shape.is_placeholder:
            if hasattr(shape, "placeholder_format") and shape.placeholder_format:
                placeholder_type = str(shape.placeholder_format.type)
                return placeholder_type.split(".")[-1].split(" ")[0]
    except Exception:
        pass
    return None


def get_default_font_size_for_placeholder(placeholder_type: str | None) -> float:
    """The documented default when nothing sets a size: 32 pt for titles, 18 pt otherwise."""
    if placeholder_type in TITLE_PLACEHOLDER_TYPES:
        return DEFAULT_TITLE_FONT_SIZE
    return DEFAULT_FONT_SIZE


def _master_style(placeholder_type: str | None) -> str:
    if placeholder_type in TITLE_PLACEHOLDER_TYPES:
        return "titleStyle"
    if placeholder_type in BODY_PLACEHOLDER_TYPES:
        return "bodyStyle"
    return "otherStyle"


def style_chain(shape, level: int = 0, own_pPr=None, placeholder_type: str | None = None) -> list:
    """The paragraph-property elements that style a paragraph at `level` (0-based) in `shape`,
    nearest first: the paragraph's own `pPr`, the shape's lstStyle, the layout and master
    placeholder lstStyles and the master titleStyle, bodyStyle or otherStyle for a placeholder, or
    the presentation defaultTextStyle for any other shape. `placeholder_type` defaults to the
    shape's own."""
    chain = [own_pPr] if own_pPr is not None else []
    tag = f"a:lvl{level + 1}pPr"

    def add(element, path: str) -> None:
        if element is not None:
            chain.extend(_xpath(element, f"{path}/{tag}")[:1])

    try:
        add(shape._element, "./p:txBody/a:lstStyle")
        if getattr(shape, "is_placeholder", False):
            base = getattr(shape, "_base_placeholder", None)
            while base is not None:
                add(base._element, "./p:txBody/a:lstStyle")
                base = getattr(base, "_base_placeholder", None)
            if placeholder_type is None:
                placeholder_type = get_placeholder_type(shape)
            master = shape.part.slide.slide_layout.slide_master._element
            add(master, f"./p:txStyles/p:{_master_style(placeholder_type)}")
        else:
            add(shape.part.package.presentation_part._element, "./p:defaultTextStyle")
    except (AttributeError, KeyError, ValueError):
        pass
    return chain


def _first(chain: list, path: str):
    """The first match of `path` along `chain`, or None."""
    for element in chain:
        found = _xpath(element, path)
        if found:
            return found[0]
    return None


def chain_font_size(chain: list) -> float | None:
    """The run size in points `chain` sets (defRPr sz), or None."""
    size = _first(chain, "./a:defRPr/@sz")
    return int(size) / 100 if size is not None else None


def _spacing_points(chain: list, tag: str, font_size: float) -> float:
    """spcBef or spcAft along `chain` in points: spcPts as given, spcPct as a share of the font
    size; 0 when unset."""
    spacing = _first(chain, f"./a:{tag}")
    if spacing is None:
        return 0.0
    points = _xpath(spacing, "./a:spcPts/@val")
    if points:
        return int(points[0]) / 100
    percent = _xpath(spacing, "./a:spcPct/@val")
    return int(percent[0]) / 100000 * font_size if percent else 0.0


def chain_metrics(chain: list, text: str, font_size: float, font_name: str) -> ParagraphMetrics:
    """`ParagraphMetrics` of a paragraph styled by `chain`: line spacing (lnSpc spcPts in points,
    spcPct in lines), spacing before and after, and left margin (marL), each from the nearest
    element of `chain` that sets it."""
    line_spacing_pt = line_spacing_lines = None
    line_spacing = _first(chain, "./a:lnSpc")
    if line_spacing is not None:
        points = _xpath(line_spacing, "./a:spcPts/@val")
        percent = _xpath(line_spacing, "./a:spcPct/@val")
        if points:
            line_spacing_pt = int(points[0]) / 100
        elif percent:
            line_spacing_lines = int(percent[0]) / 100000
    mar_l = _first(chain, "./@marL")
    return ParagraphMetrics(
        text=text,
        font_size=font_size,
        font_name=font_name,
        left_margin=int(mar_l) / EMU_PER_INCH if mar_l is not None else 0.0,
        line_spacing_pt=line_spacing_pt,
        line_spacing_lines=line_spacing_lines,
        space_before=_spacing_points(chain, "spcBef", font_size),
        space_after=_spacing_points(chain, "spcAft", font_size),
    )


def inherited_font_size(shape, placeholder_type: str | None, level: int = 0) -> float | None:
    """The font size in points a run without `sz` inherits at `level` in `shape` along
    `style_chain`, or None when the chain sets none."""
    return chain_font_size(style_chain(shape, level, placeholder_type=placeholder_type))


def shape_base_font_size(shape, level: int = 0, own_pPr=None) -> float:
    """The size of a run without `sz` at `level` in `shape`: inherited, else the placeholder-type
    default."""
    placeholder_type = get_placeholder_type(shape)
    size = chain_font_size(style_chain(shape, level, own_pPr, placeholder_type))
    return size or get_default_font_size_for_placeholder(placeholder_type)


def paragraph_metrics(paragraph, shape) -> ParagraphMetrics:
    """`ParagraphMetrics` of a written python-pptx paragraph of `shape`."""
    pPr = paragraph._element.pPr
    run_font = paragraph.runs[0].font if paragraph.runs else None
    if run_font is not None and run_font.size:
        font_size = run_font.size.pt
    else:
        font_size = shape_base_font_size(shape, paragraph.level, pPr)
    font_name = run_font.name if run_font is not None and run_font.name else DEFAULT_FONT_NAME
    chain = style_chain(shape, paragraph.level, pPr)
    return chain_metrics(chain, paragraph.text, font_size, font_name)


def frame_overflow(shape) -> float | None:
    """Text overflow of a written shape in inches, or None when the text fits within the tolerance
    or the shape has no usable text frame."""
    if not getattr(shape, "has_text_frame", False):
        return None
    usable_width, usable_height = usable_box(shape)
    if usable_width <= 0 or usable_height <= 0:
        return None
    paragraphs = [paragraph_metrics(p, shape) for p in shape.text_frame.paragraphs]
    overflow = overflow_inches(paragraphs, usable_width, usable_height)
    return overflow if overflows(overflow) else None
