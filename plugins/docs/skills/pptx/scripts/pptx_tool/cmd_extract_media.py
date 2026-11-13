"""list-images / extract-images for pptx."""

import io
import json
import re
import sys
from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE


def _parse_min_pixels(spec: str) -> tuple[int, int]:
    m = re.fullmatch(r"(\d+)\s*[xX]\s*(\d+)", spec.strip())
    if not m:
        raise ValueError(f"invalid --min-pixels '{spec}' (expected: WxH, e.g. 50x50)")
    return int(m.group(1)), int(m.group(2))


def _iter_shapes(shapes):
    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _iter_shapes(shape.shapes)
        else:
            yield shape


def _image_dims(image) -> tuple[int, int]:
    """Return (width_px, height_px) for a pptx Image, via Pillow."""
    try:
        from PIL import Image as PILImage
        img = PILImage.open(io.BytesIO(image.blob))
        return img.size
    except Exception:
        return (0, 0)


def _require_input(path: str) -> Path:
    p = Path(path)
    if not p.exists():
        print(f"Error: input file not found: {p}", file=sys.stderr)
        sys.exit(1)
    return p


def run_list_images(args) -> None:
    input_path = _require_input(args.input)
    prs = Presentation(str(input_path))

    rows: list[tuple[int, int, str, int, int, int]] = []
    for slide_idx, slide in enumerate(prs.slides, start=1):
        img_index = 0
        for shape in _iter_shapes(slide.shapes):
            if shape.shape_type != MSO_SHAPE_TYPE.PICTURE:
                continue
            image = shape.image
            width_px, height_px = _image_dims(image)
            rows.append(
                (
                    slide_idx,
                    img_index,
                    image.ext,
                    width_px,
                    height_px,
                    len(image.blob),
                )
            )
            img_index += 1

    if not rows:
        print("No images found.")
        return
    print("slide  idx  ext  width  height  bytes")
    for slide, idx, ext, w, h, n in rows:
        print(f"{slide:5d}  {idx:3d}  {ext:3s}  {w:5d}  {h:6d}  {n:6d}")


def run_extract_images(args) -> None:
    input_path = _require_input(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    min_bytes = int(getattr(args, "min_bytes", 2048))
    min_w, min_h = _parse_min_pixels(getattr(args, "min_pixels", "50x50"))

    prs = Presentation(str(input_path))
    sidecar: list[dict] = []
    count = 0
    for slide_idx, slide in enumerate(prs.slides, start=1):
        img_index = 0
        for shape in _iter_shapes(slide.shapes):
            if shape.shape_type != MSO_SHAPE_TYPE.PICTURE:
                continue
            image = shape.image
            blob = image.blob
            width_px, height_px = _image_dims(image)
            ext = image.ext
            this_idx = img_index
            img_index += 1
            if len(blob) < min_bytes:
                continue
            if width_px < min_w or height_px < min_h:
                continue
            name = f"slide_{slide_idx:02d}_img_{this_idx:02d}.{ext}"
            (output_dir / name).write_bytes(blob)
            sidecar.append(
                {
                    "file": name,
                    "slide": slide_idx,
                    "index": this_idx,
                    "width": width_px,
                    "height": height_px,
                    "bytes": len(blob),
                    "ext": ext,
                }
            )
            count += 1

    (output_dir / "images.json").write_text(
        json.dumps(sidecar, indent=2), encoding="utf-8"
    )
    print(f"Extracted {count} image(s) to {output_dir}/")
