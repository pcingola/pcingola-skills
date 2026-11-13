"""Integration tests for the inspect-template command.

The template is the synthetic multi-layout deck built with python-pptx
(`create_multilayout_pptx`).
"""
import json
import unittest

from tests.integration.pptx import (
    cleanup_dir, create_multilayout_pptx, fresh_dir, run_cli, write_readme,
)

DIR = fresh_dir("test_inspect_template")


class TestInspectTemplate(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.template = create_multilayout_pptx(DIR, "template.pptx")
        write_readme(DIR,
            "inspect-template: JSON output tests.\n"
            "Expected JSON output:\n"
            "  template.json: template metadata (slide_dimensions, slides)\n"
            "with 'slide_dimensions' and 'slides' keys and slide-N entries.")

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_inspect_template(self) -> None:
        """inspect-template writes slide_dimensions (13.33 in wide for 16:9) and one slide-N entry
        per template slide. Guards the template JSON that the authoring skills
        read."""
        out = DIR / "template.json"
        r = run_cli("inspect-template", str(self.template), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(out.exists())
        data = json.loads(out.read_text())
        self.assertIn("slide_dimensions", data)
        self.assertIn("slides", data)
        self.assertIn("slide-0", data["slides"])
        self.assertIn("slide-4", data["slides"])
        dims = data["slide_dimensions"]
        self.assertAlmostEqual(dims["width_inches"], 13.33, places=1)

    def test_inspect_missing_file(self) -> None:
        """inspect-template exits non-zero when the input deck does not exist. Guards the input
        check of the command."""
        out = DIR / "missing.json"
        r = run_cli("inspect-template", "/nonexistent.pptx", str(out))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
