"""Integration tests for the get command."""
import unittest

from tests.integration.pptx import cleanup_dir, create_test_pptx, fresh_dir, run_cli, write_readme

DIR = fresh_dir("test_get")


class TestGet(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = create_test_pptx(DIR, num_slides=3)
        write_readme(DIR,
            "get: stdout-only tests, no output files to inspect.\n"
            "test.pptx is the source (3 slides: 'Slide 0-2 Title').\n"
            "The get command prints a single shape's text content.")

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_get_title(self) -> None:
        """get slide-0/shape-0 prints that shape's text. Guards the slide-N/shape-N path resolution
        of get."""
        r = run_cli("get", str(self.source), "slide-0/shape-0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Slide 0 Title", r.stdout)

    def test_get_invalid_path_format(self) -> None:
        """get exits non-zero for a path that is not slide-N/shape-N. Guards the path format check."""
        r = run_cli("get", str(self.source), "bad-path")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_get_nonexistent_slide(self) -> None:
        """get exits non-zero for slide-99. Guards the slide range check."""
        r = run_cli("get", str(self.source), "slide-99/shape-0")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_get_nonexistent_shape(self) -> None:
        """get exits non-zero for shape-99. Guards the shape range check."""
        r = run_cli("get", str(self.source), "slide-0/shape-99")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_get_missing_file(self) -> None:
        """get exits non-zero when the input deck does not exist. Guards the input check of the
        command."""
        r = run_cli("get", "/nonexistent.pptx", "slide-0/shape-0")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
