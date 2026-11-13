"""Integration tests for inspect-template and inspect-master on the neutral template."""
import json
import unittest

from tests.integration.pptx_author import (
    PRESENTATION_TEMPLATE, cleanup_dir, fresh_dir, run_cli, write_readme,
)

DIR = fresh_dir("test_inspect_template")
LAYOUTS = ["Title Slide", "Section Header", "Title and Content", "Two Content", "Blank"]


class TestInspectTemplate(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        write_readme(DIR,
            "inspect-template and inspect-master on the neutral template.\n"
            "  presentation.json: slide_dimensions and no slides\n"
            "  layouts.json: slide_layouts with the five layout names")

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_inspect_presentation_template(self) -> None:
        """pptx inspect-template on the neutral template writes 13.33 in wide slide_dimensions and
        no slides. Guards the sidecar JSON pptx-author reads to find example slides to drop."""
        out = DIR / "presentation.json"
        r = run_cli("inspect-template", str(PRESENTATION_TEMPLATE), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(out.read_text())
        self.assertEqual(data["slides"], {})
        self.assertAlmostEqual(data["slide_dimensions"]["width_inches"], 13.33, places=1)

    def test_inspect_master_lists_layouts(self) -> None:
        """pptx inspect-master on the neutral template lists the five layouts by name. Guards the
        layout list pptx-author's phase 3 reads."""
        out = DIR / "layouts.json"
        r = run_cli("inspect-master", str(PRESENTATION_TEMPLATE), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        names = [l["layout_name"] for l in json.loads(out.read_text())["slide_layouts"]]
        self.assertEqual(names, LAYOUTS)


if __name__ == "__main__":
    unittest.main()
