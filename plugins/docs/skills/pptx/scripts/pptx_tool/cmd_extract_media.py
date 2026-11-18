"""list-images / extract-images for pptx."""

import io
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from .exceptions import PptxError


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


@dataclass(frozen=True)
class EmbeddedImage:
    """One picture of a deck: slide (0-based), index among that slide's pictures,
    extension, pixel size (0x0 when Pillow cannot read it) and size in bytes."""
    slide: int
    index: int
    ext: str
    width: int
    height: int
    size: int


@dataclass(frozen=True)
class ExtractedImage:
    """A picture written by `extract_images`: its file name in the output directory and its data."""
    file: str
    image: EmbeddedImage

    def sidecar_entry(self) -> dict:
        """The image's entry in images.json."""
        img = self.image
        return {
            "file": self.file,
            "slide": img.slide,
            "index": img.index,
            "width": img.width,
            "height": img.height,
            "bytes": img.size,
            "ext": img.ext,
        }


def _open_deck(input_path: Path) -> Presentation:
    if not input_path.exists():
        raise PptxError(f"input file not found: {input_path}")
    return Presentation(str(input_path))


def _iter_images(prs) -> Iterator[tuple[EmbeddedImage, bytes]]:
    """Yield each picture of the deck, groups included, with its bytes."""
    for slide_idx, slide in enumerate(prs.slides):
        img_index = 0
        for shape in _iter_shapes(slide.shapes):
            if shape.shape_type != MSO_SHAPE_TYPE.PICTURE:
                continue
            image = shape.image
            blob = image.blob
            width_px, height_px = _image_dims(image)
            yield EmbeddedImage(slide_idx, img_index, image.ext, width_px, height_px, len(blob)), blob
            img_index += 1


def list_images(input_path: Path) -> list[EmbeddedImage]:
    """Every picture of the deck, in slide order."""
    return [img for img, _blob in _iter_images(_open_deck(input_path))]


def extract_images(
    input_path: Path, output_dir: Path, min_bytes: int = 2048, min_pixels: tuple[int, int] = (50, 50)
) -> list[ExtractedImage]:
    """Write each picture of at least `min_bytes` and `min_pixels` (width, height) to
    `output_dir`, plus the sidecar images.json, and return the pictures written."""
    prs = _open_deck(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    min_w, min_h = min_pixels

    extracted: list[ExtractedImage] = []
    for img, blob in _iter_images(prs):
        if img.size < min_bytes:
            continue
        if img.width < min_w or img.height < min_h:
            continue
        # File names number slides from 1, like export-slides and extract-shapes.
        name = f"slide_{img.slide + 1:02d}_img_{img.index:02d}.{img.ext}"
        (output_dir / name).write_bytes(blob)
        extracted.append(ExtractedImage(name, img))

    (output_dir / "images.json").write_text(
        json.dumps([e.sidecar_entry() for e in extracted], indent=2), encoding="utf-8"
    )
    return extracted


def run_list_images(args) -> None:
    images = list_images(Path(args.input))
    if not images:
        print("No images found.")
        return
    print("slide  idx  ext  width  height  bytes")
    for img in images:
        print(f"{img.slide:5d}  {img.index:3d}  {img.ext:3s}  {img.width:5d}  {img.height:6d}  {img.size:6d}")


def run_extract_images(args) -> None:
    output_dir = Path(args.output)
    extracted = extract_images(
        Path(args.input), output_dir, args.min_bytes, _parse_min_pixels(args.min_pixels)
    )
    print(f"Extracted {len(extracted)} image(s) to {output_dir}/")
