"""Integration tests for inspect-template and inspect-master on the neutral template."""
import json
import unittest

from pptx_tool.cmd_inspect_master import inspect_master_to_file
from pptx_tool.cmd_inspect_template import inspect_template

from tests.integration.pptx_author import (
    PRESENTATION_TEMPLATE, cleanup_dir, fresh_dir, write_readme,
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
        """inspect_template on the neutral template writes 13.33 in wide slide_dimensions and
        no slides, and counts no slides. Guards the sidecar JSON pptx-author reads to find
        example slides to drop."""
        out = DIR / "presentation.json"
        result = inspect_template(PRESENTATION_TEMPLATE, out)
        self.assertEqual(result.slide_count, 0)
        data = json.loads(out.read_text())
        self.assertEqual(data["slides"], {})
        self.assertAlmostEqual(data["slide_dimensions"]["width_inches"], 13.33, places=1)

    def test_inspect_master_lists_layouts(self) -> None:
        """inspect_master_to_file on the neutral template writes the five layouts by name and
        counts them. Guards the layout list pptx-author's phase 3 reads."""
        out = DIR / "layouts.json"
        result = inspect_master_to_file(PRESENTATION_TEMPLATE, out)
        self.assertEqual(result.layout_count, len(LAYOUTS))
        names = [l["layout_name"] for l in json.loads(out.read_text())["slide_layouts"]]
        self.assertEqual(names, LAYOUTS)


if __name__ == "__main__":
    unittest.main()
