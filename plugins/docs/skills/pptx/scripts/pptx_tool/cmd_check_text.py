"""Flat text extraction from PowerPoint presentations.

extract-text  Dumps every non-empty paragraph as one line: slide number,
              layout name, shape label, and the paragraph text.
              Typical output: ~50-200 lines for a full deck vs 4000+ lines
              from extract-shapes — small enough to never hit a read truncation.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from .exceptions import PptxError

EMU_PER_INCH = 914400


def _placeholder_type(shape) -> str | None:
    try:
        if shape.is_placeholder and shape.placeholder_format:
            return str(shape.placeholder_format.type).split(".")[-1].split(" ")[0]
    except Exception:
        pass
    return None


def _pos_label(left_emu: int, top_emu: int) -> str:
    return f'{round(left_emu / EMU_PER_INCH, 2)}",{round(top_emu / EMU_PER_INCH, 2)}"'


def _shape_label(shape, abs_left: int, abs_top: int) -> str:
    pt = _placeholder_type(shape)
    return f"{pt or 'TEXT'}@{_pos_label(abs_left, abs_top)}"


def _iter_paragraphs(shape, parent_left=0, parent_top=0):
    """Yield (abs_left, abs_top, label, text) for every non-empty paragraph,
    recursing into groups and tables."""
    abs_left = parent_left + (shape.left or 0)
    abs_top = parent_top + (shape.top or 0)

    pt = _placeholder_type(shape)
    if pt == "SLIDE_NUMBER":
        return

    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        for child in shape.shapes:
            yield from _iter_paragraphs(child, abs_left, abs_top)
        return

    if hasattr(shape, "has_table") and shape.has_table:
        for r_idx, row in enumerate(shape.table.rows):
            for c_idx, cell in enumerate(row.cells):
                if getattr(cell, "is_spanned", False):
                    continue
                if not cell.text_frame:
                    continue
                for para in cell.text_frame.paragraphs:
                    text = para.text.strip()
                    if text:
                        label = f"TABLE[{r_idx},{c_idx}]@{_pos_label(abs_left, abs_top)}"
                        yield (abs_left, abs_top, label, text)
        return

    if hasattr(shape, "has_text_frame") and shape.has_text_frame:
        label = _shape_label(shape, abs_left, abs_top)
        for para in shape.text_frame.paragraphs:
            text = para.text.strip()
            if text:
                yield (abs_left, abs_top, label, text)


@dataclass(frozen=True)
class TextParagraph:
    """One non-empty paragraph: slide index, layout name, shape label, text."""
    slide: int
    layout: str
    shape: str
    text: str


def extract_paragraphs(input_path: Path, slide: int | None = None) -> list[TextParagraph]:
    """Every non-empty paragraph of the deck, or of one slide (0-based) when `slide` is set."""
    if not input_path.exists():
        raise PptxError(f"'{input_path}' not found")

    prs = Presentation(str(input_path))
    paragraphs = []
    for slide_idx, pptx_slide in enumerate(prs.slides):
        if slide is not None and slide_idx != slide:
            continue
        try:
            layout_name = pptx_slide.slide_layout.name
        except Exception:
            layout_name = "?"
        for shape in pptx_slide.shapes:
            for _left, _top, label, text in _iter_paragraphs(shape):
                paragraphs.append(TextParagraph(slide_idx, layout_name, label, text))
    return paragraphs


def format_paragraphs(paragraphs: list[TextParagraph], as_json: bool) -> str:
    """Paragraphs as a JSON array, or as one aligned line each (no trailing newline)."""
    if as_json:
        return json.dumps([asdict(p) for p in paragraphs], indent=2, ensure_ascii=False)
    return "\n".join(
        f"S{p.slide:02d}  {p.layout:<28}  {p.shape:<40}  {p.text}" for p in paragraphs
    )


def run_extract_text(args) -> None:
    paragraphs = extract_paragraphs(Path(args.input), args.slide)
    out = format_paragraphs(paragraphs, args.json)
    if not args.output:
        print(out)
        return
    # The plain-text file ends with a newline; the JSON file does not.
    Path(args.output).write_text(out if args.json else out + "\n", encoding="utf-8")
    print(f"Wrote {len(paragraphs)} paragraphs to {args.output}")
