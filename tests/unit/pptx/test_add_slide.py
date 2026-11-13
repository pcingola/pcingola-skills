"""Unit tests for add-slide: new slides from a deck's own layouts, and their empty placeholders in
the extract-shapes inventory that add-text fills."""
import tempfile
import unittest
from pathlib import Path

from pptx import Presentation

from pptx_tool.cmd_add_slide import add_slides
from pptx_tool.cmd_edit import apply_operations
from pptx_tool.cmd_extract_shapes import extract_text


def _layout_deck(path: Path) -> None:
    """A deck with the default layouts and no slides, like a brand presentation template."""
    Presentation().save(str(path))


class TestAddSlides(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.deck = Path(self.tmp.name) / "template.pptx"
        _layout_deck(self.deck)

    def test_slides_follow_layout_names(self) -> None:
        """add_slides adds one slide per name with that layout, in order. Guards the template path of
        a template that has layouts and no example slides."""
        prs = Presentation(str(self.deck))
        landed = add_slides(prs, ["Title Slide", "Title and Content", "Blank"], None)
        self.assertEqual(landed, [0, 1, 2])
        self.assertEqual([s.slide_layout.name for s in prs.slides], ["Title Slide", "Title and Content", "Blank"])

    def test_position_inserts(self) -> None:
        """add_slides with a position inserts the new slides there in order. Guards --position."""
        prs = Presentation(str(self.deck))
        add_slides(prs, ["Blank", "Blank"], None)
        landed = add_slides(prs, ["Title Slide", "Title Only"], 1)
        self.assertEqual(landed, [1, 2])
        self.assertEqual([s.slide_layout.name for s in prs.slides], ["Blank", "Title Slide", "Title Only", "Blank"])

    def test_unknown_layout_rejected(self) -> None:
        """add_slides raises ValueError naming the deck's layouts for an unknown name. Guards a typo
        from adding nothing or the wrong layout."""
        prs = Presentation(str(self.deck))
        with self.assertRaisesRegex(ValueError, "Title Slide"):
            add_slides(prs, ["No Such Layout"], None)

    def test_empty_placeholders_are_fillable(self) -> None:
        """A new slide's empty title and body placeholders appear in extract_text, and an edit spec of
        add-slide then add-text fills them. Guards the inventory that add-text checks its keys against."""
        out = Path(self.tmp.name) / "out.pptx"
        apply_operations(self.deck, out, [
            {"action": "add-slide", "layouts": ["Title and Content"]},
            {"action": "add-text", "data": {"slide-0": {
                "shape-0": {"paragraphs": [{"text": "Heading"}]},
                "shape-1": {"paragraphs": [{"text": "Point", "bullet": True}]},
            }}},
        ])
        shapes = extract_text(out)["slide-0"]
        self.assertEqual([shapes[k].shape.text_frame.text for k in ("shape-0", "shape-1")], ["Heading", "Point"])

    def test_edit_layout_name_with_comma(self) -> None:
        """An edit spec add-slide passes its layout list as is, so a layout name with a comma
        resolves. Guards the list being joined with commas and split again."""
        prs = Presentation(str(self.deck))
        prs.slide_layouts[1].name = "Title, and Content"
        prs.save(str(self.deck))
        out = Path(self.tmp.name) / "comma.pptx"
        apply_operations(self.deck, out, [{"action": "add-slide", "layouts": ["Title, and Content"]}])
        self.assertEqual([s.slide_layout.name for s in Presentation(str(out)).slides], ["Title, and Content"])

    def test_table_replaces_empty_placeholder(self) -> None:
        """add-table with placeholder_index on a new slide removes the empty OBJECT placeholder it
        covers. Guards against an empty placeholder under the table, which extract-shapes reports
        as an overlap and validate as an unfilled visual slot."""
        out = Path(self.tmp.name) / "table.pptx"
        apply_operations(self.deck, out, [
            {"action": "add-slide", "layouts": ["Title and Content"]},
            {"action": "add-table", "data": {"slide-0": {
                "rows": [{"header": True, "cells": ["A", "B"]}, {"cells": ["1", "2"]}],
                "placeholder_index": 1}}},
        ])
        slide = Presentation(str(out)).slides[0]
        self.assertEqual([p.placeholder_format.idx for p in slide.placeholders], [0])
        self.assertEqual(sum(1 for s in slide.shapes if s.has_table), 1)


if __name__ == "__main__":
    unittest.main()
