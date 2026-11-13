"""Integration tests for the add-chart command.

Runs on the synthetic multi-layout fixture. The assertion that matters is that
the result is a real CHART shape carrying its data, not a picture of one.
"""
import json
import unittest

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from tests.integration.pptx import (
    cleanup_dir, create_multilayout_pptx, fresh_dir, run_cli, stamp_description, write_readme,
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


def _write(name: str, payload: dict):
    path = DIR / name
    path.write_text(json.dumps(payload))
    return path


class TestAddChart(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.source = create_multilayout_pptx(DIR)
        cls.column_json = _write("chart_data.json", COLUMN_CHART)
        cls.pie_json = _write("pie_chart_data.json", PIE_CHART)
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
        r = run_cli("add-chart", str(self.source), str(out), str(ONE_OBJECT_SLIDE),
                    str(self.column_json))
        self.assertEqual(r.returncode, 0, r.stderr)

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
        r = run_cli("add-chart", str(self.source), str(out), str(ONE_OBJECT_SLIDE),
                    str(self.column_json))
        self.assertEqual(r.returncode, 0, r.stderr)
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
        r = run_cli("add-chart", str(self.source), str(out), str(ONE_OBJECT_SLIDE),
                    str(self.pie_json))
        self.assertEqual(r.returncode, 0, r.stderr)
        charts = self._charts(out)
        self.assertEqual(len(charts), 1)
        self.assertTrue(charts[0].chart.plots[0].has_data_labels)
        stamp_description(out,
            "add-chart: pie chart with three labelled slices on slide 1.")

    def test_index_targets_the_second_placeholder(self) -> None:
        """add-chart --index 1 fills the second OBJECT placeholder and leaves the first in place.
        Guards placeholder selection by index."""
        out = DIR / "second.pptx"
        r = run_cli("add-chart", str(self.source), str(out), str(TWO_OBJECT_SLIDE),
                    str(self.column_json), "--index", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        slide = Presentation(str(out)).slides[TWO_OBJECT_SLIDE]
        self.assertEqual(
            len([s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.CHART]), 1)
        # The first OBJECT placeholder must survive untouched.
        remaining = [
            s for s in slide.shapes
            if s.is_placeholder and s.placeholder_format.type == 7
        ]
        self.assertEqual(len(remaining), 1)

    def test_slide_out_of_range_errors(self) -> None:
        """add-chart exits non-zero with "out of range" for slide 999. Guards the slide range check."""
        r = run_cli("add-chart", str(self.source), str(DIR / "nope.pptx"), "999",
                    str(self.column_json))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        self.assertIn("out of range", r.stderr)

    def test_placeholder_index_out_of_range_errors(self) -> None:
        """add-chart exits non-zero with "out of range" for --index 5 on a slide with one OBJECT
        placeholder. Guards the placeholder index check."""
        r = run_cli("add-chart", str(self.source), str(DIR / "nope.pptx"),
                    str(ONE_OBJECT_SLIDE), str(self.column_json), "--index", "5")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        self.assertIn("out of range", r.stderr)

    def test_no_object_placeholder_errors(self) -> None:
        """add-chart exits non-zero with "No OBJECT placeholders" on a slide without one. Guards the
        explicit error instead of adding a free-floating chart."""
        r = run_cli("add-chart", str(self.source), str(DIR / "nope.pptx"), "4",
                    str(self.column_json))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        self.assertIn("No OBJECT placeholders", r.stderr)

    def test_unsupported_chart_type_errors(self) -> None:
        """add-chart exits non-zero with "Unsupported chart_type" for chart_type 999. Guards the
        chart type check before python-pptx is called."""
        bad = _write("bad_type.json", {"chart_type": 999,
                                       "data": {"categories": ["A"], "series": []}})
        r = run_cli("add-chart", str(self.source), str(DIR / "nope.pptx"),
                    str(ONE_OBJECT_SLIDE), str(bad))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        self.assertIn("Unsupported chart_type", r.stderr)

    def test_missing_required_data_key_errors(self) -> None:
        """add-chart exits non-zero with "missing required key" when the data has no series. Guards
        the validation of the chart data JSON."""
        bad = _write("missing_series.json", {"chart_type": 51, "data": {"categories": ["A"]}})
        r = run_cli("add-chart", str(self.source), str(DIR / "nope.pptx"),
                    str(ONE_OBJECT_SLIDE), str(bad))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        self.assertIn("missing required key", r.stderr)

    def test_missing_chart_data_file_errors(self) -> None:
        """add-chart exits non-zero when the chart data JSON does not exist. Guards the data file
        check."""
        r = run_cli("add-chart", str(self.source), str(DIR / "nope.pptx"),
                    str(ONE_OBJECT_SLIDE), "/nonexistent.json")
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_missing_input_errors(self) -> None:
        """add-chart exits non-zero when the input deck does not exist. Guards the input check of
        the command."""
        r = run_cli("add-chart", "/nonexistent.pptx", str(DIR / "nope.pptx"),
                    str(ONE_OBJECT_SLIDE), str(self.column_json))
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
