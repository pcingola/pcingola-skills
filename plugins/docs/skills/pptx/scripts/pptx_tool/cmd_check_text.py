"""Flat text extraction from PowerPoint presentations.

extract-text  Dumps every non-empty paragraph as one line: slide number,
              layout name, shape label, and the paragraph text.
              Typical output: ~50-200 lines for a full deck vs 4000+ lines
              from extract-shapes — small enough to never hit a read truncation.
"""

import json
import sys
from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

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


def run_extract_text(args) -> None:
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: '{input_path}' not found", file=sys.stderr)
        sys.exit(1)

    prs = Presentation(str(input_path))
    slide_filter = args.slide  # 0-based int or None

    records = []
    for slide_idx, slide in enumerate(prs.slides):
        if slide_filter is not None and slide_idx != slide_filter:
            continue
        try:
            layout_name = slide.slide_layout.name
        except Exception:
            layout_name = "?"
        for shape in slide.shapes:
            for left, top, label, text in _iter_paragraphs(shape):
                records.append({
                    "slide": slide_idx + 1,
                    "layout": layout_name,
                    "shape": label,
                    "text": text,
                })

    if args.json:
        out = json.dumps(records, indent=2, ensure_ascii=False)
        if args.output:
            Path(args.output).write_text(out, encoding="utf-8")
            print(f"Wrote {len(records)} paragraphs to {args.output}")
        else:
            print(out)
    else:
        lines = [
            f"S{r['slide']:02d}  {r['layout']:<28}  {r['shape']:<40}  {r['text']}"
            for r in records
        ]
        output_text = "\n".join(lines)
        if args.output:
            Path(args.output).write_text(output_text + "\n", encoding="utf-8")
            print(f"Wrote {len(records)} paragraphs to {args.output}")
        else:
            print(output_text)
