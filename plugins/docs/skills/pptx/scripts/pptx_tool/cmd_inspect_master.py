"""Inspect slide master and slide layouts, surfacing all shapes and text.

Use this to detect:
- Confidentiality tags or compliance shapes on the master
- Spurious decorative or branding shapes on layout slides
- Any text baked into master/layout shapes that bleeds onto content slides

Output: JSON with 'slide_master' and 'slide_layouts' sections, each listing
shapes with their position, text content, fill, and any flags.
"""

import json
import sys
from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Inches

EMU_PER_INCH = 914400


def _shape_to_dict(shape, parent_left=0, parent_top=0) -> list[dict]:
    """Recursively flatten a shape (including groups) to a list of dicts."""
    results = []
    abs_left = parent_left + (shape.left or 0)
    abs_top = parent_top + (shape.top or 0)

    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        for child in shape.shapes:
            results.extend(_shape_to_dict(child, abs_left, abs_top))
        return results

    d: dict = {
        "name": shape.name,
        "left": round(abs_left / EMU_PER_INCH, 3),
        "top": round(abs_top / EMU_PER_INCH, 3),
        "width": round((shape.width or 0) / EMU_PER_INCH, 3),
        "height": round((shape.height or 0) / EMU_PER_INCH, 3),
    }

    # Shape type
    try:
        d["shape_type"] = str(shape.shape_type).split(".")[-1].split(" ")[0]
    except Exception:
        pass

    # Placeholder info
    try:
        if shape.is_placeholder and shape.placeholder_format:
            pf = shape.placeholder_format
            d["placeholder_type"] = str(pf.type).split(".")[-1].split(" ")[0]
            d["placeholder_idx"] = pf.idx
    except Exception:
        pass

    # Text content
    try:
        if shape.has_text_frame:
            text = shape.text_frame.text.strip()
            if text:
                d["text"] = text
            # Paragraphs with formatting
            paras = []
            for para in shape.text_frame.paragraphs:
                t = para.text.strip()
                if not t:
                    continue
                p: dict = {"text": t}
                if para.runs:
                    run = para.runs[0]
                    font = run.font
                    if font.name:
                        p["font_name"] = font.name
                    if font.size:
                        p["font_size"] = round(font.size.pt, 2)
                    if font.bold:
                        p["bold"] = True
                    try:
                        p["color"] = f"#{font.color.rgb}"
                    except Exception:
                        try:
                            if font.color.theme_color is not None:
                                p["theme_color"] = str(font.color.theme_color).split(".")[-1].split(" ")[0]
                        except Exception:
                            pass
                paras.append(p)
            if paras:
                d["paragraphs"] = paras
    except Exception:
        pass

    # Fill
    try:
        fill = shape.fill
        if fill.type is not None:
            fill_type = str(fill.type).split(".")[-1].split(" ")[0]
            d["fill_type"] = fill_type
            if fill_type == "SOLID":
                try:
                    d["fill_color"] = f"#{fill.fore_color.rgb}"
                except Exception:
                    try:
                        tc = fill.fore_color.theme_color
                        d["fill_theme_color"] = str(tc).split(".")[-1].split(" ")[0]
                    except Exception:
                        pass
        else:
            d["fill_type"] = "BACKGROUND"
    except Exception:
        pass

    # Rotation
    try:
        r = shape.rotation
        if r is not None and round(r, 1) != 0.0:
            d["rotation"] = round(r, 2)
    except Exception:
        pass

    # Off-canvas flag (slide dimensions are 13.33" x 7.5" widescreen)
    right = d["left"] + d["width"]
    bottom = d["top"] + d["height"]
    if right > 13.34 or bottom > 7.51 or d["left"] < -0.5 or d["top"] < -0.5:
        d["off_canvas"] = True

    # Flag suspicious content
    flags = []
    text_lower = d.get("text", "").lower()
    name_lower = d.get("name", "").lower()
    if "!" in d.get("text", "") or "confidential" in text_lower:
        flags.append("possible_confidentiality_tag")
    if "example" in text_lower or "template" in text_lower or "click to edit" in text_lower:
        flags.append("template_artifact")
    if d.get("rotation") and abs(d["rotation"]) > 10:
        flags.append("rotated_shape")
    if d.get("off_canvas"):
        flags.append("off_canvas")
    if flags:
        d["flags"] = flags

    results.append(d)
    return results


def inspect_master(pptx_path: Path) -> dict:
    prs = Presentation(str(pptx_path))
    output: dict = {}

    # --- Slide master(s) ---
    masters_out = []
    for master_idx, master in enumerate(prs.slide_masters):
        master_shapes = []
        for shape in master.shapes:
            master_shapes.extend(_shape_to_dict(shape))
        masters_out.append({
            "master_index": master_idx,
            "shape_count": len(master_shapes),
            "shapes": master_shapes,
        })
    output["slide_masters"] = masters_out

    # --- Slide layouts ---
    layouts_out = []
    for master_idx, master in enumerate(prs.slide_masters):
        for layout_idx, layout in enumerate(master.slide_layouts):
            layout_shapes = []
            for shape in layout.shapes:
                layout_shapes.extend(_shape_to_dict(shape))
            # Only include layouts that have non-placeholder shapes (potential bleed-through)
            non_ph = [s for s in layout_shapes if "placeholder_type" not in s]
            layouts_out.append({
                "master_index": master_idx,
                "layout_index": layout_idx,
                "layout_name": layout.name,
                "total_shapes": len(layout_shapes),
                "non_placeholder_shapes": len(non_ph),
                "shapes": layout_shapes,
            })
    output["slide_layouts"] = layouts_out

    return output


def run_inspect_master(args) -> None:
    pptx_path = Path(args.input)
    output_path = Path(args.output)

    if not pptx_path.exists():
        print(f"Error: File not found: {pptx_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Inspecting slide master: {pptx_path}")
    data = inspect_master(pptx_path)

    n_masters = len(data["slide_masters"])
    n_layouts = len(data["slide_layouts"])
    n_master_shapes = sum(m["shape_count"] for m in data["slide_masters"])
    flagged = [
        s for m in data["slide_masters"] for s in m["shapes"] if s.get("flags")
    ] + [
        s for l in data["slide_layouts"] for s in l["shapes"] if s.get("flags")
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Masters: {n_masters}, Layouts: {n_layouts}, Master shapes: {n_master_shapes}")
    if flagged:
        print(f"Flagged shapes: {len(flagged)}")
        for s in flagged:
            print(f"  [{', '.join(s['flags'])}] name={s['name']!r} text={s.get('text','')!r} pos=({s['left']}\", {s['top']}\")")
    else:
        print("No flagged shapes found on master or layouts.")
    print(f"Output saved to: {output_path}")
