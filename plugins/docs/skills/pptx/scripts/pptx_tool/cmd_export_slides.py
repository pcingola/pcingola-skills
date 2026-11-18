"""Export each slide in a PPTX as an individual image file."""

import shutil
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from .slide_render import ImageFormat, render_slides, require_powerpoint

DEFAULT_DPI = 150


def export_image_name(slide_number: int, fmt: ImageFormat) -> str:
    """File name of the exported image of slide `slide_number` (1-based): slide_NN.<ext>."""
    return f"slide_{slide_number:02d}.{fmt.value}"


def copy_exported_images(images: Sequence[Path], output_dir: Path, fmt: ImageFormat) -> list[Path]:
    """Copy rendered images, in slide order, to `output_dir` as slide_01.<ext>, slide_02.<ext>, ...;
    return the copies."""
    exported = []
    for number, image in enumerate(images, start=1):
        dest = output_dir / export_image_name(number, fmt)
        shutil.copy2(image, dest)
        exported.append(dest)
    return exported


def export_slides(input_path: Path, output_dir: Path, dpi: int = DEFAULT_DPI,
                  fmt: ImageFormat = ImageFormat.PNG,
                  progress: Callable[[str], None] = lambda _: None) -> list[Path]:
    """Render each slide of `input_path` and write it to `output_dir` (created if missing) as
    slide_NN.<fmt> at `dpi`; return the written paths in slide order.

    `progress` receives the progress message before rendering starts. An invalid input raises
    PptxError; a missing or failing LibreOffice or pdftoppm raises RuntimeError.
    """
    require_powerpoint(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        progress(f"Converting {input_path} to images...")
        images = render_slides(input_path, Path(tmp), dpi, fmt)
        return copy_exported_images(images, output_dir, fmt)


def run_export_slides(args) -> None:
    """Entry point from CLI dispatcher."""
    output_dir: Path = args.output
    exported = export_slides(args.input, output_dir, args.dpi, ImageFormat(args.format), progress=print)
    print(f"Exported {len(exported)} slide image(s) to: {output_dir}")
    for path in exported:
        print(f"  {path}")
