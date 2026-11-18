"""Replace an OBJECT placeholder with a native, editable chart.

The chart is a real PowerPoint chart object with its data table intact — not a
picture of one. That matters twice over: the numbers stay editable in
PowerPoint, and they cannot drift from an image regenerated at another time.
"""

import json
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import ChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.util import Length, Pt

from .common import CHART_COLORS, require_file
from .exceptions import PptxError
from .placeholders import find_object_placeholders, remove_shape

CHART_TYPE_COLUMN_CLUSTERED = 51
CHART_TYPE_PIE = 5

# XL_CHART_TYPE members can't be built from an integer; map on demand.
CHART_TYPE_MAP = {
    CHART_TYPE_COLUMN_CLUSTERED: XL_CHART_TYPE.COLUMN_CLUSTERED,
    CHART_TYPE_PIE: XL_CHART_TYPE.PIE,
}


def prepare_chart_data(data: dict) -> ChartData:
    """Build a pptx ChartData from the categories / series block in the JSON."""
    chart_data = ChartData()
    chart_data.categories = data.get("categories", [])
    for series in data.get("series", []):
        chart_data.add_series(series.get("name", ""), series.get("values", []))
    return chart_data


def apply_column_chart_formatting(chart: object, data: dict) -> None:
    """Axis titles, per-series colours, legend (only when multi-series), optional title."""
    x_title = data.get("x_axis_title")
    y_title = data.get("y_axis_title")
    if x_title and hasattr(chart, "category_axis"):
        chart.category_axis.has_title = True
        chart.category_axis.axis_title.text_frame.text = x_title
    if y_title and hasattr(chart, "value_axis"):
        chart.value_axis.has_title = True
        chart.value_axis.axis_title.text_frame.text = y_title

    for i, series in enumerate(chart.series):
        color = CHART_COLORS[i % len(CHART_COLORS)]
        series.format.fill.solid()
        series.format.fill.fore_color.rgb = color

    if len(data.get("series", [])) > 1:
        chart.has_legend = True
        chart.legend.include_in_layout = False

    title = data.get("title")
    if title:
        chart.has_title = True
        chart.chart_title.text_frame.text = title


def apply_pie_chart_formatting(chart: object, data: dict) -> None:
    """Legend, data labels (raw values — percentages must be pre-computed), slice colours."""
    chart.has_legend = True
    chart.legend.include_in_layout = False
    chart.legend.font.size = Pt(10)
    chart.plots[0].has_data_labels = True

    data_labels = chart.plots[0].data_labels
    data_labels.number_format = "General"
    data_labels.position = XL_LABEL_POSITION.OUTSIDE_END

    for series in chart.plots[0].series:
        for j, point in enumerate(series.points):
            color = CHART_COLORS[j % len(CHART_COLORS)]
            point.format.fill.solid()
            point.format.fill.fore_color.rgb = color

    title = data.get("title")
    if title:
        chart.has_title = True
        chart.chart_title.text_frame.text = title


def add_chart_to_slide(slide: object, placeholder: object, chart_config: dict) -> None:
    """Replace an OBJECT placeholder with a native chart at the same geometry."""
    chart_type_int = chart_config.get("chart_type", CHART_TYPE_COLUMN_CLUSTERED)
    data = chart_config.get("data", {})
    for key in ("categories", "series"):
        if key not in data:
            raise ValueError(f"chart_data.json missing required key in 'data': '{key}'")

    left, top, width, height = placeholder.left, placeholder.top, placeholder.width, placeholder.height

    # Chart frame: 95% of the placeholder width, 90% of its height, horizontally centred.
    chart_width = Length(int(width * 0.95))
    chart_height = Length(int(height * 0.90))
    chart_left = Length(left + (width - chart_width) // 2)
    chart_top = Length(top + (height - chart_height) // 8)

    xl_type = CHART_TYPE_MAP.get(chart_type_int)
    if xl_type is None:
        raise ValueError(f"Unsupported chart_type {chart_type_int}. Use 51 (column) or 5 (pie).")

    chart_data = prepare_chart_data(data)
    remove_shape(slide, placeholder)
    chart_shape = slide.shapes.add_chart(xl_type, chart_left, chart_top, chart_width, chart_height, chart_data)
    chart = chart_shape.chart

    if chart_type_int == CHART_TYPE_PIE:
        apply_pie_chart_formatting(chart, data)
    else:
        apply_column_chart_formatting(chart, data)


def add_chart(input_path: Path, output_path: Path, slide_index: int, chart_config: dict, index: int = 0) -> None:
    """Replace the OBJECT placeholder at `index` on one slide with the chart `chart_config`
    (the chart data JSON) and save the deck to output_path."""
    require_file(input_path, f"Input file not found: {input_path}")
    prs = Presentation(str(input_path))
    if not 0 <= slide_index < len(prs.slides):
        raise PptxError(f"Slide index {slide_index} out of range (0-{len(prs.slides) - 1})")

    slide = prs.slides[slide_index]
    placeholders = find_object_placeholders(slide)
    if not placeholders:
        raise PptxError(f"No OBJECT placeholders found on slide {slide_index}")
    if index >= len(placeholders):
        raise PptxError(
            f"Placeholder index {index} out of range. "
            f"Found {len(placeholders)} OBJECT placeholder(s)."
        )

    try:
        add_chart_to_slide(slide, placeholders[index], chart_config)
    except (ValueError, RuntimeError) as exc:
        raise PptxError(str(exc)) from None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(output_path))


def run_add_chart(args) -> None:
    """Entry point from CLI dispatcher."""
    input_path = Path(args.input)
    output_path = Path(args.output)
    data_path = Path(args.chart_data)

    # The CLI reports a missing input before a missing or malformed chart data file.
    require_file(input_path, f"Input file not found: {input_path}")
    require_file(data_path, f"chart data JSON not found: {data_path}")
    with open(data_path, encoding="utf-8") as f:
        chart_config = json.load(f)

    add_chart(input_path, output_path, args.slide, chart_config, args.index)
    print(f"Inserted chart into slide {args.slide}, placeholder {args.index}")
    print(f"Saved to: {output_path}")
