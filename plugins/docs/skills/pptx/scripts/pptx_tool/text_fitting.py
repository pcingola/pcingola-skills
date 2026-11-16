"""Font-size reduction for add-text: the largest common reduction at which a shape's text fits.

The text height comes from `text_metrics`, the same model the inventory's overflow check applies to
the written deck, so a size the fitter accepts is never flagged as overflowing and vice versa.
"""

from dataclasses import dataclass, replace

from .text_metrics import (
    DEFAULT_FONT_NAME,
    DEFAULT_FONT_SIZE,
    ParagraphMetrics,
    bullet_margin_emu,
    chain_font_size,
    chain_metrics,
    get_default_font_size_for_placeholder,
    get_placeholder_type,
    overflow_inches,
    overflows,
    style_chain,
    usable_box,
)
from .common import EMU_PER_INCH

MIN_FONT_SIZE = 12.0
FONT_SIZE_STEP = 2.0


@dataclass
class FittingResult:
    """Result of text fitting calculation for a shape."""
    fits: bool
    reduction: float  # Amount to reduce each font size by (0 = no change)
    shape_key: str
    slide_key: str
    overflow_inches: float | None = None

    @property
    def adjusted(self) -> bool:
        return self.reduction > 0

    def __str__(self) -> str:
        if self.adjusted:
            return f"{self.slide_key}/{self.shape_key}: reduced by {self.reduction}pt"
        return f"{self.slide_key}/{self.shape_key}: no change needed"


def paragraph_chains(shape, paragraphs: list[dict]) -> list[list]:
    """The `style_chain` of each paragraph add-text writes into `shape`, at the level it writes:
    `level` for a bullet, else the level of the pPr that `TextFrame.clear` keeps on the first
    paragraph, else 0. The first paragraph's chain starts with that kept pPr."""
    kept = shape.text_frame.paragraphs[0]._element.pPr
    kept_level = int(kept.get("lvl", 0)) if kept is not None else 0
    chains = []
    for i, para in enumerate(paragraphs):
        if para.get("bullet", False):
            level = para.get("level", 0)
        else:
            level = kept_level if i == 0 else 0
        chains.append(style_chain(shape, level, kept if i == 0 else None))
    return chains


def paragraph_base_sizes(shape, paragraphs: list[dict], chains: list[list] | None = None) -> list[float]:
    """The size each paragraph starts from before a reduction: its `font_size`, else the size its
    chain inherits, else the placeholder-type default."""
    chains = chains if chains is not None else paragraph_chains(shape, paragraphs)
    default = get_default_font_size_for_placeholder(get_placeholder_type(shape))
    return [para.get("font_size") or chain_font_size(chain) or default
            for para, chain in zip(paragraphs, chains)]


def written_paragraph_metrics(para: dict, chain: list, font_size: float, reduced: bool) -> ParagraphMetrics:
    """`ParagraphMetrics` of what add-text writes for paragraph data `para` at `font_size`.

    Spacing and line spacing come from `chain` unless `para` gives them (in points), as
    `ParagraphProcessor.apply_properties` writes them. marL is always written: a bullet's follows
    the written run size (`font_size` when given or when the shape is reduced, else 18 pt), any
    other paragraph gets 0."""
    metrics = chain_metrics(chain, para.get("text", ""), font_size, para.get("font_name", DEFAULT_FONT_NAME))
    left_margin = 0.0
    if para.get("bullet", False):
        written_size = font_size if ("font_size" in para or reduced) else DEFAULT_FONT_SIZE
        left_margin = bullet_margin_emu(written_size, para.get("level", 0))[0] / EMU_PER_INCH
    overrides = {"left_margin": left_margin}
    if "line_spacing" in para:
        overrides.update(line_spacing_pt=para["line_spacing"], line_spacing_lines=None)
    if "space_before" in para:
        overrides["space_before"] = para["space_before"]
    if "space_after" in para:
        overrides["space_after"] = para["space_after"]
    return replace(metrics, **overrides)


class TextFitter:
    """Finds the common font-size reduction that makes a shape's text fit."""

    def __init__(self, min_font_size: float = MIN_FONT_SIZE, font_size_step: float = FONT_SIZE_STEP):
        self.min_font_size = min_font_size
        self.font_size_step = font_size_step

    def find_fitting_reduction(self, shape, shape_text_data: dict, slide_key: str, shape_key: str) -> FittingResult:
        """Find the smallest reduction, in `font_size_step` steps, at which the text fits `shape`.

        `shape_text_data` is the add-text entry of the shape: `paragraphs` and any
        `text_margin_*` insets it writes. Each paragraph starts at `paragraph_base_sizes`; all drop
        by the same amount, none below `min_font_size`."""
        paragraphs = shape_text_data["paragraphs"]
        usable_width, usable_height = usable_box(shape, shape_text_data)
        if usable_width <= 0 or usable_height <= 0:
            return FittingResult(fits=False, reduction=0, slide_key=slide_key, shape_key=shape_key)

        chains = paragraph_chains(shape, paragraphs)
        base_sizes = paragraph_base_sizes(shape, paragraphs, chains)

        reduction = 0.0
        while True:
            sizes = [max(self.min_font_size, size - reduction) for size in base_sizes]
            metrics = [written_paragraph_metrics(para, chain, size, reduction > 0)
                       for para, chain, size in zip(paragraphs, chains, sizes)]
            overflow = overflow_inches(metrics, usable_width, usable_height)
            if not overflows(overflow):
                return FittingResult(fits=True, reduction=reduction, slide_key=slide_key, shape_key=shape_key)
            if min(sizes) <= self.min_font_size:
                return FittingResult(fits=False, reduction=reduction, slide_key=slide_key,
                                     shape_key=shape_key, overflow_inches=round(overflow, 2))
            reduction += self.font_size_step
