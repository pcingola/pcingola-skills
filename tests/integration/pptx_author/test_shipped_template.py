"""Smoke test of the template path's pptx commands against the neutral brand's presentation.pptx."""
import unittest

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx_tool.cmd_edit import EditAction, apply_operations
from pptx_tool.cmd_validate import validate_deck

from tests.integration.pptx_author import (
    PRESENTATION_TEMPLATE, cleanup_dir, fresh_dir, write_readme,
)

DIR = fresh_dir("test_shipped_template")


class TestShippedTemplate(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        write_readme(DIR, "One edit spec (add-slide, add-text, add-chart, add-table, add-notes) "
                          "applied to the shipped neutral template.")

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def test_edit_spec_builds_a_clean_deck(self) -> None:
        """apply_operations (pptx edit) on the neutral template runs all five operations, adds
        slides from layouts, fills them by the slot map's shape keys, adds a chart, a table and
        notes, and validate_deck finds no problem. Guards the native build of 04-native-build.md
        on the shipped template."""
        spec = {"operations": [
            {"action": "add-slide", "layouts": ["Title Slide", "Two Content", "Title and Content"]},
            {"action": "add-text", "data": {
                "slide-0": {"shape-0": {"paragraphs": [{"text": "Smoke title"}]},
                            "shape-1": {"paragraphs": [{"text": "Subtitle"}]}},
                "slide-1": {"shape-0": {"paragraphs": [{"text": "Chart slide"}]},
                            "shape-1": {"paragraphs": [{"text": "Point", "bullet": True, "level": 0}]}},
                "slide-2": {"shape-0": {"paragraphs": [{"text": "Table slide"}]}}}},
            {"action": "add-chart", "slide": 1, "index": 1, "data": {"chart_type": 51, "data": {
                "categories": ["Q1", "Q2"], "series": [{"name": "Revenue", "values": [10, 20]}]}}},
            {"action": "add-table", "data": {"slide-2": {
                "rows": [{"header": True, "cells": ["A", "B"]}, {"cells": ["1", "2"]}],
                "placeholder_index": 1}}},
            {"action": "add-notes", "data": {"slide-0": "Talk track"}},
        ]}
        out = DIR / "deck.pptx"
        edited = apply_operations(PRESENTATION_TEMPLATE, out, spec["operations"])
        self.assertEqual([s.action for s in edited.steps],
                         [EditAction(op["action"]) for op in spec["operations"]])

        report = validate_deck(out)
        self.assertFalse(report.has_problems, report.to_json())

        slides = Presentation(str(out)).slides
        self.assertEqual([s.slide_layout.name for s in slides],
                         ["Title Slide", "Two Content", "Title and Content"])
        self.assertIn("Smoke title", slides[0].shapes.title.text_frame.text)
        charts = [s for s in slides[1].shapes if s.shape_type == MSO_SHAPE_TYPE.CHART]
        self.assertEqual(len(charts), 1)
        self.assertEqual(list(charts[0].chart.series[0].values), [10.0, 20.0])
        self.assertEqual(sum(1 for s in slides[2].shapes if s.has_table), 1)


if __name__ == "__main__":
    unittest.main()
