"""Integration tests for the inspect-master command.

`inspect-master` shipped with no coverage in either tier. It is the slide-master
audit — spurious shapes, confidentiality tags, template artifacts — so a silent
failure here means those go unreported, which looks identical to a clean deck.
"""
import json
import unittest

from pptx import Presentation
from pptx.util import Inches, Pt

from tests.integration.pptx import (
    cleanup_dir, create_test_pptx, fresh_dir, run_cli, write_readme,
)

DIR = fresh_dir("test_inspect_master")


def _deck_with_master_tag(path, text: str):
    """Put a text box carrying `text` on the slide master, then save.

    python-pptx's MasterShapes has no add_textbox, so the box is built on a
    scratch slide and its element moved into the master's shape tree — which is
    exactly the kind of hand-placed master shape inspect-master exists to find.
    """
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "Content"

    box = slide.shapes.add_textbox(Inches(0.3), Inches(6.8), Inches(4), Inches(0.4))
    box.text_frame.paragraphs[0].text = text
    box.text_frame.paragraphs[0].font.size = Pt(9)

    element = box._element
    element.getparent().remove(element)
    prs.slide_masters[0].shapes._spTree.append(element)

    prs.save(str(path))
    return path


class TestInspectMaster(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.plain = create_test_pptx(DIR, name="plain.pptx", num_slides=2)
        cls.tagged = _deck_with_master_tag(DIR / "tagged.pptx", "CONFIDENTIAL — internal use only")
        write_readme(DIR,
            "inspect-master: slide master / layout audit JSON.\n"
            "Expected outputs:\n"
            "  plain.json  — masters and layouts of an untouched deck, no flags\n"
            "  tagged.json — same, but the master carries a CONFIDENTIAL text box\n"
            "                which must appear under flags as possible_confidentiality_tag")

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_reports_masters_and_layouts(self) -> None:
        """inspect-master writes one record per slide master and per layout (11 in the stock theme),
        each layout with its name and non_placeholder_shapes. Guards the structure of the master
        audit JSON."""
        out = DIR / "plain.json"
        r = run_cli("inspect-master", str(self.plain), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(out.read_text())
        self.assertIn("slide_masters", data)
        self.assertIn("slide_layouts", data)
        self.assertEqual(len(data["slide_masters"]), 1)
        # The stock theme has 11 layouts; each record carries its name.
        self.assertEqual(len(data["slide_layouts"]), 11)
        names = {layout["layout_name"] for layout in data["slide_layouts"]}
        self.assertIn("Title and Content", names)
        for layout in data["slide_layouts"]:
            self.assertIn("non_placeholder_shapes", layout)

    def test_flags_confidentiality_tag_on_master(self) -> None:
        """inspect-master flags a CONFIDENTIAL text box on the slide master as
        possible_confidentiality_tag with its text. Guards the confidentiality tag detection on
        masters."""
        out = DIR / "tagged.json"
        r = run_cli("inspect-master", str(self.tagged), str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads(out.read_text())
        flagged = [
            shape
            for master in data["slide_masters"]
            for shape in master["shapes"]
            if "possible_confidentiality_tag" in shape.get("flags", [])
        ]
        self.assertTrue(flagged, "CONFIDENTIAL text on the master was not flagged")
        self.assertIn("CONFIDENTIAL", flagged[0]["text"])

    def test_missing_file(self) -> None:
        """inspect-master exits non-zero when the input deck does not exist. Guards the input check
        of the command."""
        r = run_cli("inspect-master", "/nonexistent.pptx", str(DIR / "nope.json"))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
