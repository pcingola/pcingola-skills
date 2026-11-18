"""Render a PowerPoint deck to one image per slide: LibreOffice to PDF, then pdftoppm.

Shared by `export-slides` and `visual-preview`. The command lines are built by
`soffice_command` and `pdftoppm_command`, so a test can check the options we pass
without running either tool. A missing or failing tool raises RuntimeError with
an actionable message.
"""

import shutil
import subprocess
from enum import StrEnum
from pathlib import Path

from .exceptions import PptxError

POWERPOINT_SUFFIXES = (".pptx", ".ppt")
# pdftoppm writes <prefix>-<page>.<ext>; the prefix is <work dir>/<RENDER_PREFIX>.
RENDER_PREFIX = "slide"


class ImageFormat(StrEnum):
    """Image format of the rendered slides; the value is the file extension."""
    JPG = "jpg"
    PNG = "png"

    @property
    def pdftoppm_flag(self) -> str:
        """The pdftoppm option that selects this format."""
        return "-jpeg" if self is ImageFormat.JPG else "-png"


def require_powerpoint(path: Path) -> None:
    """Raise PptxError unless `path` exists and has a PowerPoint suffix (.pptx or .ppt)."""
    if not path.exists():
        raise PptxError(f"Input file not found: {path}")
    if path.suffix.lower() not in POWERPOINT_SUFFIXES:
        raise PptxError("Input must be a PowerPoint file (.pptx or .ppt)")


def soffice_command(soffice: str, pptx_path: Path, out_dir: Path) -> list[str]:
    """Command line that converts `pptx_path` to `<out_dir>/<stem>.pdf` with LibreOffice `soffice`."""
    return [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(pptx_path)]


def pdftoppm_command(pdf_path: Path, prefix: Path, dpi: int, fmt: ImageFormat) -> list[str]:
    """Command line that rasterizes every page of `pdf_path` to `<prefix>-<page>.<fmt>` at `dpi`."""
    return ["pdftoppm", fmt.pdftoppm_flag, "-r", str(dpi), str(pdf_path), str(prefix)]


def rendered_images(work_dir: Path, fmt: ImageFormat) -> list[Path]:
    """The page images pdftoppm wrote into `work_dir`, in page order; RuntimeError if there are none."""
    images = sorted(work_dir.glob(f"{RENDER_PREFIX}-*.{fmt.value}"))
    if not images:
        raise RuntimeError("No images generated from PDF")
    return images


def libreoffice_to_pdf(pptx_path: Path, work_dir: Path) -> Path:
    """Convert `pptx_path` to a PDF in `work_dir` with LibreOffice and return the PDF path."""
    from . import find_libreoffice
    soffice = find_libreoffice()
    if not soffice:
        raise RuntimeError(
            "LibreOffice is required but not found. "
            "Install: brew install libreoffice (macOS) or apt-get install libreoffice (Linux)"
        )
    result = subprocess.run(soffice_command(soffice, pptx_path, work_dir), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice conversion failed: {result.stderr}")
    pdf = work_dir / f"{pptx_path.stem}.pdf"
    if not pdf.exists():
        raise RuntimeError(f"Expected PDF not found: {pdf}")
    return pdf


def pdf_to_images(pdf_path: Path, work_dir: Path, dpi: int, fmt: ImageFormat) -> list[Path]:
    """Rasterize every page of `pdf_path` into `work_dir` with pdftoppm; return the images in page order."""
    if not shutil.which("pdftoppm"):
        raise RuntimeError(
            "pdftoppm (poppler) is required but not found. "
            "Install: brew install poppler (macOS) or apt-get install poppler-utils (Linux)"
        )
    result = subprocess.run(pdftoppm_command(pdf_path, work_dir / RENDER_PREFIX, dpi, fmt),
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"pdftoppm failed: {result.stderr}")
    return rendered_images(work_dir, fmt)


def render_slides(pptx_path: Path, work_dir: Path, dpi: int, fmt: ImageFormat) -> list[Path]:
    """Render each slide of `pptx_path` to an image in `work_dir`; return the images in slide order."""
    return pdf_to_images(libreoffice_to_pdf(pptx_path, work_dir), work_dir, dpi, fmt)
