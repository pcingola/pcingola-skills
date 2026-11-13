"""What the neutral presentation template must be, asserted against the binary and the slot map.

Checked here, stated in pptx-author's references and verified nowhere else:

1. No author identity in the template.
2. 16:9, the five layouts that 03-layout-mapping.md lists, and no example slides.
3. Every line of the slot map in 03-layout-mapping.md: a new slide of that layout, numbered by
   extract-shapes as add-text numbers it, has exactly those shape-N keys, placeholder types and idx.

After an edit of the slot map block in 03-layout-mapping.md, run this suite.
"""

import json
import re
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from pptx import Presentation

from pptx_tool.cmd_add_slide import add_slides
from pptx_tool.cmd_extract_shapes import extract_text

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent.parent
SKILL_DIR = PROJECT_DIR / "plugins" / "media" / "skills" / "pptx-author"
NEUTRAL = PROJECT_DIR / "plugins" / "brand" / "skills" / "brand" / "brands" / "neutral"
TEMPLATE = NEUTRAL / "pptx" / "presentation.pptx"
TEMPLATE_JSON = NEUTRAL / "pptx" / "presentation.json"
LAYOUT_MAPPING = SKILL_DIR / "references" / "03-layout-mapping.md"

CORE_NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
}
LEAKY_PARTS = ("ppt/authors.xml", "ppt/commentAuthors.xml")
LAYOUTS = ["Title Slide", "Section Header", "Title and Content", "Two Content", "Blank"]
# `role=shape-N TYPE:idx`
SLOT_RE = re.compile(r"([\w.]+)=shape-(\d+)\s+([A-Z_]+):(\d+)")


def parse_slot_map() -> list[tuple[str, str]]:
    """Return (layout_name, slots) per line of the ```slotmap block."""
    text = LAYOUT_MAPPING.read_text(encoding="utf-8")
    blocks = re.findall(r"```slotmap\n(.*?)```", text, re.DOTALL)
    assert len(blocks) == 1, f"expected exactly one ```slotmap block, found {len(blocks)}"
    rows = []
    for line in blocks[0].splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split("|")]
        assert len(parts) == 2, f"malformed slot map line: {line!r}"
        rows.append((parts[0], parts[1]))
    return rows


class TestTemplate(unittest.TestCase):

    def test_no_author_identity(self) -> None:
        """The neutral template has no authors or commentAuthors part and empty dc:creator and
        cp:lastModifiedBy. Guards against shipping a template stamped with a person's identity."""
        with zipfile.ZipFile(TEMPLATE) as z:
            leaked = [part for part in LEAKY_PARTS if part in z.namelist()]
            self.assertFalse(leaked)
            core = ElementTree.fromstring(z.read("docProps/core.xml"))
        self.assertEqual(core.findtext("dc:creator", default="", namespaces=CORE_NS), "")
        self.assertEqual(core.findtext("cp:lastModifiedBy", default="", namespaces=CORE_NS), "")

    def test_layouts_size_and_no_slides(self) -> None:
        """The neutral template is 13.33 x 7.5 in with the five documented layouts and no slides,
        and its JSON lists no slides. Guards the layout table of 03-layout-mapping.md and the
        build that starts from layouts, not example slides."""
        prs = Presentation(str(TEMPLATE))
        self.assertAlmostEqual(prs.slide_width.inches, 13.33, places=2)
        self.assertAlmostEqual(prs.slide_height.inches, 7.5, places=2)
        self.assertEqual([l.name for l in prs.slide_layouts], LAYOUTS)
        self.assertEqual(len(prs.slides), 0)
        self.assertEqual(json.loads(TEMPLATE_JSON.read_text(encoding="utf-8"))["slides"], {})


class TestSlotMap(unittest.TestCase):
    """references/03-layout-mapping.md, line by line, against new slides of each layout."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = parse_slot_map()
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        deck = Path(tmp.name) / "probe.pptx"
        prs = Presentation(str(TEMPLATE))
        add_slides(prs, [name for name, _ in cls.rows], None)
        prs.save(str(deck))
        cls.shapes = extract_text(deck)

    def test_covers_every_layout(self) -> None:
        """The slotmap block lists every layout of the neutral template once. Guards a layout
        without a slot map line."""
        self.assertEqual(sorted(name for name, _ in self.rows), sorted(LAYOUTS))

    def test_every_slot_resolves_and_every_shape_is_mapped(self) -> None:
        """Each role=shape-N TYPE:idx entry names a shape with that placeholder type and idx on a
        new slide of its layout, and the line names every shape extract-shapes lists there.
        Guards the shape keys agents pass to add-text."""
        for i, (layout, slots) in enumerate(self.rows):
            shapes = self.shapes.get(f"slide-{i}", {})
            if slots == "none":
                self.assertEqual(shapes, {}, layout)
                continue
            parsed = SLOT_RE.findall(slots)
            self.assertEqual(len(parsed), slots.count("="), f"{layout}: unparsable slot in {slots!r}")
            self.assertEqual({f"shape-{n}" for _, n, _, _ in parsed}, set(shapes), layout)
            for role, n, ph_type, ph_idx in parsed:
                fmt = shapes[f"shape-{n}"].shape.placeholder_format
                self.assertEqual(fmt.type.name, ph_type, f"{layout}/{role} type")
                self.assertEqual(fmt.idx, int(ph_idx), f"{layout}/{role} idx")


if __name__ == "__main__":
    unittest.main()
