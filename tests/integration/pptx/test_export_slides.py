"""Tests of the export-slides command.

`export-slides` is what the deck-authoring skills run their render checks
through: LibreOffice converts the deck to PDF and `pdftoppm` rasterizes it. The
naming, the input checks and the `pdftoppm` command line are tested without
LibreOffice; one end-to-end test runs both tools.
"""
import unittest
from pathlib import Path

from PIL import Image

from pptx_tool.cmd_export_slides import copy_exported_images, export_slides
from pptx_tool.exceptions import PptxError
from pptx_tool.pptx import build_parser
from pptx_tool.slide_render import ImageFormat, pdftoppm_command, rendered_images
from tests.prereq import requires
from tests.integration.pptx import (
    cleanup_dir, create_test_pptx, fresh_dir, has_libreoffice, write_readme,
)

DIR = fresh_dir("test_export_slides")


def _write_images(d: Path, names: list[str], fmt: str) -> list[Path]:
    """Write a small image in format `fmt` (a Pillow format name) for each of `names` into `d`."""
    d.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in names:
        path = d / name
        Image.new("RGB", (40, 30), "white").save(path, fmt)
        paths.append(path)
    return paths


class TestExportSlidesWithoutLibreOffice(unittest.TestCase):

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_copies_rendered_images_as_slide_nn(self) -> None:
        """copy_exported_images copies three rendered images, in order, to slide_01..slide_03 with
        the extension of the format, and returns the copies. Guards the file naming and count that
        the render checks of the deck-authoring skills rely on."""
        for fmt, pil_format in ((ImageFormat.PNG, "PNG"), (ImageFormat.JPG, "JPEG")):
            src = _write_images(DIR / f"rendered_{fmt.value}",
                                [f"slide-{n}.{fmt.value}" for n in (1, 2, 3)], pil_format)
            out = DIR / f"copied_{fmt.value}"
            out.mkdir()
            exported = copy_exported_images(src, out, fmt)
            names = [f"slide_0{n}.{fmt.value}" for n in (1, 2, 3)]
            self.assertEqual(exported, [out / n for n in names])
            self.assertEqual(sorted(p.name for p in out.iterdir()), names)
            for copy, original in zip(exported, src):
                self.assertEqual(copy.read_bytes(), original.read_bytes())

    def test_rendered_images_in_page_order_of_the_format(self) -> None:
        """rendered_images returns pdftoppm's page images of the requested format in page order and
        raises RuntimeError when there are none. Guards which files become slide_01, slide_02, ...
        and the error when pdftoppm wrote nothing."""
        work = DIR / "work"
        _write_images(work, ["slide-2.png", "slide-1.png", "slide-3.png"], "PNG")
        _write_images(work, ["slide-1.jpg"], "JPEG")
        self.assertEqual([p.name for p in rendered_images(work, ImageFormat.PNG)],
                         ["slide-1.png", "slide-2.png", "slide-3.png"])
        empty = DIR / "work_empty"
        empty.mkdir()
        with self.assertRaisesRegex(RuntimeError, "No images generated from PDF"):
            rendered_images(empty, ImageFormat.PNG)

    def test_pdftoppm_command_carries_format_and_dpi(self) -> None:
        """pdftoppm_command passes -png or -jpeg for the format and -r <dpi>, then the PDF and the
        output prefix. Guards that --format and --dpi reach pdftoppm."""
        pdf, prefix = Path("/w/deck.pdf"), Path("/w/slide")
        self.assertEqual(pdftoppm_command(pdf, prefix, 150, ImageFormat.PNG),
                         ["pdftoppm", "-png", "-r", "150", "/w/deck.pdf", "/w/slide"])
        self.assertEqual(pdftoppm_command(pdf, prefix, 72, ImageFormat.JPG),
                         ["pdftoppm", "-jpeg", "-r", "72", "/w/deck.pdf", "/w/slide"])

    def test_cli_defaults_png_at_150_dpi(self) -> None:
        """The export-slides parser defaults to --format png and --dpi 150. Guards the defaults that
        export-slides without options passes to the core function."""
        args = build_parser().parse_args(["export-slides", "deck.pptx", "out"])
        self.assertEqual((args.format, args.dpi), ("png", 150))

    def test_missing_input(self) -> None:
        """export_slides raises PptxError naming the path when the input deck does not exist, and
        creates no output directory. Guards the input check of the command, which the CLI prints
        as an error without a traceback."""
        out = DIR / "nope"
        with self.assertRaisesRegex(PptxError, "Input file not found: /nonexistent.pptx"):
            export_slides(Path("/nonexistent.pptx"), out)
        self.assertFalse(out.exists())

    def test_rejects_non_powerpoint_input(self) -> None:
        """export_slides raises PptxError for a text file and creates no output directory. Guards
        the input type check before LibreOffice is run, which the CLI prints as an error without a
        traceback."""
        not_a_deck = DIR / "notes.txt"
        not_a_deck.write_text("plain text")
        out = DIR / "nope2"
        with self.assertRaisesRegex(PptxError, r"Input must be a PowerPoint file \(.pptx or .ppt\)"):
            export_slides(not_a_deck, out)
        self.assertFalse(out.exists())


@requires(has_libreoffice(), "LibreOffice not installed")
class TestExportSlidesEndToEnd(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.dir = fresh_dir("test_export_slides_e2e")
        cls.source = create_test_pptx(cls.dir, num_slides=3)
        write_readme(cls.dir,
            "export-slides end to end: one image file per slide.\n"
            "Expected outputs:\n"
            "  nested/deeper/slide_01.jpg .. slide_03.jpg: 3 slides as JPEG at 72 dpi (720 px wide)\n"
            "Each image should show 'Slide N Title' with body text below it.")

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(cls.dir)

    def test_renders_each_slide_with_libreoffice(self) -> None:
        """export_slides on a 3-slide 10 in deck, as JPEG at 72 dpi into a missing nested directory,
        creates the directory and writes slide_01.jpg .. slide_03.jpg, non-empty JPEGs 720 px wide.
        Guards the integration with LibreOffice and pdftoppm: one image per slide, the directory
        creation, and that the format and dpi reach pdftoppm."""
        out = self.dir / "nested" / "deeper"
        exported = export_slides(self.source, out, dpi=72, fmt=ImageFormat.JPG)
        self.assertTrue(out.is_dir())
        self.assertEqual(exported, [out / f"slide_0{n}.jpg" for n in (1, 2, 3)])
        self.assertEqual(sorted(out.glob("slide_*")), exported)
        for img in exported:
            self.assertGreater(img.stat().st_size, 0, f"{img.name} is empty")
            with Image.open(img) as im:
                self.assertEqual(im.format, "JPEG")
                self.assertEqual(im.width, 720, "72 dpi did not reach pdftoppm")
