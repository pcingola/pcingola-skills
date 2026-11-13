"""Export each slide in a PPTX as an individual image file."""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


CONVERSION_DPI = 150


def _libreoffice_to_pdf(pptx_path: Path, temp_dir: Path) -> Path:
    from . import find_libreoffice
    lo = find_libreoffice()
    if not lo:
        raise RuntimeError(
            "LibreOffice is required but not found. "
            "Install: brew install libreoffice (macOS) or apt-get install libreoffice (Linux)"
        )
    result = subprocess.run(
        [lo, "--headless", "--convert-to", "pdf", "--outdir", str(temp_dir), str(pptx_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice conversion failed: {result.stderr}")
    pdf = temp_dir / f"{pptx_path.stem}.pdf"
    if not pdf.exists():
        raise RuntimeError(f"Expected PDF not found: {pdf}")
    return pdf


def _pdf_to_images(pdf_path: Path, temp_dir: Path, dpi: int, fmt: str) -> list[Path]:
    if not shutil.which("pdftoppm"):
        raise RuntimeError(
            "pdftoppm (poppler) is required but not found. "
            "Install: brew install poppler (macOS) or apt-get install poppler-utils (Linux)"
        )
    prefix = temp_dir / "slide"
    flag = "-jpeg" if fmt == "jpg" else "-png"
    result = subprocess.run(
        ["pdftoppm", flag, "-r", str(dpi), str(pdf_path), str(prefix)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftoppm failed: {result.stderr}")
    ext = "jpg" if fmt == "jpg" else "png"
    images = sorted(temp_dir.glob(f"slide-*.{ext}"))
    if not images:
        raise RuntimeError("No images generated from PDF")
    return images


def run_export_slides(args) -> None:
    input_path: Path = args.input
    output_dir: Path = args.output
    dpi: int = args.dpi
    fmt: str = args.format

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    if input_path.suffix.lower() not in (".pptx", ".ppt"):
        print("Error: Input must be a PowerPoint file (.pptx or .ppt)", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        print(f"Converting {input_path} to images...")
        pdf = _libreoffice_to_pdf(input_path, tmp_path)
        images = _pdf_to_images(pdf, tmp_path, dpi, fmt)

        for i, img in enumerate(images, start=1):
            dest = output_dir / f"slide_{i:02d}.{fmt}"
            shutil.copy2(img, dest)

    print(f"Exported {len(images)} slide image(s) to: {output_dir}")
    for i in range(1, len(images) + 1):
        print(f"  {output_dir / f'slide_{i:02d}.{fmt}'}")
