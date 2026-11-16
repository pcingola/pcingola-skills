"""Integration tests for the export-slides command.

`export-slides` is what the deck-authoring skills run their render checks
through, which rasterizes with `pdftoppm`.
"""
import unittest

from PIL import Image

from tests.prereq import requires
from tests.integration.pptx import (
    cleanup_dir, create_test_pptx, fresh_dir, has_libreoffice, run_cli, write_readme,
)

DIR = fresh_dir("test_export_slides")


@requires(has_libreoffice(), "LibreOffice not installed")
class TestExportSlides(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = create_test_pptx(DIR, num_slides=3)
        write_readme(DIR,
            "export-slides: one image file per slide.\n"
            "Expected outputs:\n"
            "  png/slide_01.png .. slide_03.png  — 3 slides at the default 150 dpi\n"
            "  jpg/slide_01.jpg .. slide_03.jpg  — same 3 slides as JPEG at 72 dpi\n"
            "Each image should show 'Slide N Title' with body text below it.")

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_exports_one_png_per_slide(self) -> None:
        """export-slides writes one non-empty PNG per slide named slide_NN.png. Guards the file
        naming and count that the render checks of the deck-authoring skills rely on."""
        out = DIR / "png"
        r = run_cli("export-slides", str(self.source), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        images = sorted(out.glob("slide_*.png"))
        self.assertEqual([p.name for p in images],
                         ["slide_01.png", "slide_02.png", "slide_03.png"])
        for img in images:
            self.assertGreater(img.stat().st_size, 0, f"{img.name} is empty")
            with Image.open(img) as im:
                self.assertEqual(im.format, "PNG")

    def test_jpg_format_and_dpi(self) -> None:
        """export-slides --format jpg writes JPEGs and --dpi 150 gives wider images than --dpi 72.
        Guards that both options reach `pdftoppm`."""
        low = DIR / "jpg"
        r = run_cli("export-slides", str(self.source), str(low), "--format", "jpg", "--dpi", "72")
        self.assertEqual(r.returncode, 0, r.stderr)
        jpgs = sorted(low.glob("slide_*.jpg"))
        self.assertEqual(len(jpgs), 3)
        with Image.open(jpgs[0]) as im:
            self.assertEqual(im.format, "JPEG")
            low_width = im.width

        high = DIR / "jpg_high"
        r = run_cli("export-slides", str(self.source), str(high), "--format", "jpg", "--dpi", "150")
        self.assertEqual(r.returncode, 0, r.stderr)
        with Image.open(sorted(high.glob("slide_*.jpg"))[0]) as im:
            self.assertGreater(im.width, low_width,
                               "150 dpi produced no more pixels than 72 dpi")

    def test_creates_output_directory(self) -> None:
        """export-slides creates a missing nested output directory. Guards the directory creation
        before rasterizing."""
        out = DIR / "nested" / "deeper"
        r = run_cli("export-slides", str(self.source), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(out.is_dir())
        self.assertEqual(len(list(out.glob("slide_*.png"))), 3)

    def test_missing_input(self) -> None:
        """export-slides exits non-zero when the input deck does not exist. Guards the input check
        of the command."""
        r = run_cli("export-slides", "/nonexistent.pptx", str(DIR / "nope"))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_rejects_non_powerpoint_input(self) -> None:
        """export-slides exits non-zero for a text file. Guards the input type check before
        LibreOffice is run."""
        not_a_deck = DIR / "notes.txt"
        not_a_deck.write_text("plain text")
        r = run_cli("export-slides", str(not_a_deck), str(DIR / "nope2"))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
