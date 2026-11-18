"""Integration tests for the add-chart command.

Runs on the synthetic multi-layout fixture. The tests call the core function `add_chart`;
the test of the chart data file check calls the CLI in process, because the CLI layer loads
that file. The result must be a real CHART shape carrying its data, not a picture of one.
"""
import json
import unittest
from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from pptx_tool.cmd_add_chart import add_chart
from pptx_tool.exceptions import PptxError
from tests.integration.pptx import (
    cleanup_dir, cli, create_multilayout_pptx, fresh_dir, stamp_description, write_readme,
)

DIR = fresh_dir("test_add_chart")

# Fixture slides carrying OBJECT placeholders (see create_multilayout_pptx).
ONE_OBJECT_SLIDE = 0
TWO_OBJECT_SLIDE = 2

COLUMN_CHART = {
    "chart_type": 51,
    "data": {
        "categories": ["Q1", "Q2", "Q3", "Q4"],
        "series": [{"name": "Revenue", "values": [10, 20, 15, 25]}],
        "x_axis_title": "Quarter",
        "y_axis_title": "Revenue",
        "title": "Revenue by quarter",
    },
}

PIE_CHART = {
    "chart_type": 5,
    "data": {
        "categories": ["Alpha", "Beta", "Gamma"],
        "series": [{"name": "Share", "values": [50, 30, 20]}],
    },
}


class TestAddChart(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = create_multilayout_pptx(DIR)
        write_readme(DIR,
            "add-chart: native charts inserted into OBJECT placeholders.\n"
            "Expected outputs:\n"
            "  column.pptx — slide 1 carries a clustered column chart of Q1-Q4 revenue\n"
            "  pie.pptx    — slide 1 carries a pie chart with labelled slices\n"
            "  second.pptx — slide 3's SECOND column holds the chart, the first is untouched\n"
            "In PowerPoint each must be selectable as a chart with an editable data table.")

    @classmethod
    def tearDownClass(cls) -> None:
        cleanup_dir(DIR)

    def _charts(self, path):
        slide = Presentation(str(path)).slides[ONE_OBJECT_SLIDE]
        return [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.CHART]

    def test_column_chart_is_native_and_keeps_its_data(self) -> None:
        """add-chart inserts a native chart with the JSON's categories, values and title into the
        slide's OBJECT placeholder. Guards that the result is an editable chart, not a picture of
        one."""
        out = DIR / "column.pptx"
        add_chart(self.source, out, ONE_OBJECT_SLIDE, COLUMN_CHART)

        charts = self._charts(out)
        self.assertEqual(len(charts), 1)
        chart = charts[0].chart
        # A picture of a chart has none of this.
        self.assertEqual(list(chart.plots[0].categories), ["Q1", "Q2", "Q3", "Q4"])
        self.assertEqual(list(chart.series[0].values), [10, 20, 15, 25])
        self.assertEqual(chart.chart_title.text_frame.text, "Revenue by quarter")
        stamp_description(out,
            "add-chart: clustered column chart of Q1-Q4 revenue on slide 1.\n"
            "Expected: a selectable chart object with an editable data table.")

    def test_placeholder_is_replaced_not_overlaid(self) -> None:
        """add-chart removes the OBJECT placeholder it fills. Guards against an empty placeholder
        prompt left behind the chart."""
        out = DIR / "replaced.pptx"
        add_chart(self.source, out, ONE_OBJECT_SLIDE, COLUMN_CHART)
        slide = Presentation(str(out)).slides[ONE_OBJECT_SLIDE]
        objects = [
            s for s in slide.shapes
            if s.is_placeholder and s.placeholder_format.type == 7  # OBJECT
        ]
        self.assertEqual(objects, [])

    def test_pie_chart(self) -> None:
        """add-chart with chart_type 5 (pie) turns on data labels. Guards the pie-specific labelling
        of add-chart."""
        out = DIR / "pie.pptx"
        add_chart(self.source, out, ONE_OBJECT_SLIDE, PIE_CHART)
        charts = self._charts(out)
        self.assertEqual(len(charts), 1)
        self.assertTrue(charts[0].chart.plots[0].has_data_labels)
        stamp_description(out,
            "add-chart: pie chart with three labelled slices on slide 1.")

    def test_index_targets_the_second_placeholder(self) -> None:
        """add_chart with index 1 fills the second OBJECT placeholder and leaves the first in place.
        Guards placeholder selection by index."""
        out = DIR / "second.pptx"
        result = add_chart(self.source, out, TWO_OBJECT_SLIDE, COLUMN_CHART, index=1)
        self.assertEqual(result.placeholder_index, 1)
        slide = Presentation(str(out)).slides[TWO_OBJECT_SLIDE]
        self.assertEqual(
            len([s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.CHART]), 1)
        # The first OBJECT placeholder must survive untouched.
        remaining = [
            s for s in slide.shapes
            if s.is_placeholder and s.placeholder_format.type == 7
        ]
        self.assertEqual(len(remaining), 1)

    def test_cli_forwards_index(self) -> None:
        """add-chart on the command line with --index 1 fills the right OBJECT placeholder of the
        two-column slide and leaves the left one in place. Guards that --index reaches add_chart."""
        data = DIR / "column.json"
        data.write_text(json.dumps(COLUMN_CHART))
        out = DIR / "second_cli.pptx"
        r = cli("add-chart", str(self.source), str(out), str(TWO_OBJECT_SLIDE), str(data),
                "--index", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        slide = Presentation(str(out)).slides[TWO_OBJECT_SLIDE]
        charts = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.CHART]
        remaining = [
            s for s in slide.shapes
            if s.is_placeholder and s.placeholder_format.type == 7  # OBJECT
        ]
        self.assertEqual((len(charts), len(remaining)), (1, 1))
        self.assertLess(remaining[0].left, charts[0].left, "the chart filled the first placeholder")

    def test_slide_out_of_range_errors(self) -> None:
        """add_chart raises PptxError with "out of range" for slide 999. Guards the slide range check."""
        with self.assertRaisesRegex(PptxError, r"Slide index 999 out of range \(0-4\)"):
            add_chart(self.source, DIR / "nope.pptx", 999, COLUMN_CHART)

    def test_placeholder_index_out_of_range_errors(self) -> None:
        """add_chart raises PptxError with "out of range" for index 5 on a slide with one OBJECT
        placeholder. Guards the placeholder index check."""
        with self.assertRaisesRegex(PptxError, "Placeholder index 5 out of range"):
            add_chart(self.source, DIR / "nope.pptx", ONE_OBJECT_SLIDE, COLUMN_CHART, index=5)

    def test_no_object_placeholder_errors(self) -> None:
        """add_chart raises PptxError with "No OBJECT placeholders" on a slide without one. Guards
        the explicit error instead of adding a free-floating chart."""
        with self.assertRaisesRegex(PptxError, "No OBJECT placeholders found on slide 4"):
            add_chart(self.source, DIR / "nope.pptx", 4, COLUMN_CHART)

    def test_unsupported_chart_type_errors(self) -> None:
        """add_chart raises PptxError with "Unsupported chart_type" for chart_type 999. Guards the
        chart type check before python-pptx is called."""
        bad = {"chart_type": 999, "data": {"categories": ["A"], "series": []}}
        with self.assertRaisesRegex(PptxError, "Unsupported chart_type 999"):
            add_chart(self.source, DIR / "nope.pptx", ONE_OBJECT_SLIDE, bad)

    def test_missing_required_data_key_errors(self) -> None:
        """add_chart raises PptxError with "missing required key" when the data has no series.
        Guards the validation of the chart data JSON."""
        bad = {"chart_type": 51, "data": {"categories": ["A"]}}
        with self.assertRaisesRegex(PptxError, "missing required key in 'data': 'series'"):
            add_chart(self.source, DIR / "nope.pptx", ONE_OBJECT_SLIDE, bad)

    def test_missing_chart_data_file_errors(self) -> None:
        """The add-chart CLI exits with 1 and prints the not-found error when the chart data JSON
        does not exist. Guards the data file check of the CLI layer, which loads the file."""
        r = cli("add-chart", str(self.source), str(DIR / "nope.pptx"),
                str(ONE_OBJECT_SLIDE), "/nonexistent.json")
        self.assertEqual(r.returncode, 1)
        self.assertIn("Error: chart data JSON not found: /nonexistent.json", r.stderr)

    def test_missing_input_errors(self) -> None:
        """add_chart raises PptxError naming the input deck when it does not exist. Guards the input
        check of the command."""
        with self.assertRaisesRegex(PptxError, "Input file not found: /nonexistent.pptx"):
            add_chart(Path("/nonexistent.pptx"), DIR / "nope.pptx", ONE_OBJECT_SLIDE, COLUMN_CHART)
