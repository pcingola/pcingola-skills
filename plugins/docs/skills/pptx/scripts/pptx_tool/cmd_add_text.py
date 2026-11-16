"""Add text to PowerPoint presentations with automatic overflow prevention.

The text data JSON structure matches the inventory output format.
All text shapes from the inventory are cleared unless "paragraphs" is specified.
Font sizes are automatically reduced (minimum 12pt) if text would overflow.
"""

import json
import sys
import tempfile
from pathlib import Path

from .cmd_extract_shapes import ExtractedShapesData, extract_text
from .exceptions import OverflowError, TextAdditionError, ValidationError
from .text_fitting import FittingResult, TextFitter, MIN_FONT_SIZE, paragraph_base_sizes
from .text_formatters import ParagraphProcessor
from .text_validators import TextAdditionValidator, WarningCollector
from pptx import Presentation


class PresentationTextAdder:
    """Main class for adding text to presentations with overflow prevention."""

    def __init__(self):
        self.processor = ParagraphProcessor()
        self.warning_collector = WarningCollector()
        self.text_fitter = TextFitter()

    def add_text(self, input_path: str, text_data_path: str, output_path: str) -> None:
        """Add text from JSON to PowerPoint presentation with auto-fitting."""
        prs = Presentation(input_path)
        extracted_shapes_data = extract_text(Path(input_path), prs)
        text_data = self._load_text_data(text_data_path)

        self._validate_text_data(extracted_shapes_data, text_data)

        # Pre-calculate fitting for all shapes
        fitting_results = self._calculate_all_fittings(extracted_shapes_data, text_data)

        # Check for unresolvable overflow
        failed_fittings = [r for r in fitting_results.values() if not r.fits]
        if failed_fittings:
            self._report_overflow_failures(failed_fittings, extracted_shapes_data)
            raise OverflowError(f"Text overflow cannot be resolved for {len(failed_fittings)} shape(s)")

        # Apply text with adjusted font sizes
        stats = self._process_shapes(prs, extracted_shapes_data, text_data, fitting_results)

        # Post-validation safety check
        self._check_results(prs)

        prs.save(output_path)

        # Report adjustments and results
        adjustments = [r for r in fitting_results.values() if r.adjusted]
        self._report_results(output_path, len(prs.slides), stats, adjustments)

    def _load_text_data(self, json_path: str) -> dict:
        """Load and validate JSON structure."""
        with open(json_path, "r") as f:
            return json.load(f, object_pairs_hook=self._check_duplicate_keys)

    @staticmethod
    def _check_duplicate_keys(pairs: list[tuple]) -> dict:
        """Check for duplicate keys when loading JSON."""
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValidationError(f"Duplicate key found in JSON: '{key}'")
            result[key] = value
        return result

    def _validate_text_data(self, extracted_shapes_data: ExtractedShapesData, text_data: dict) -> None:
        """Validate text data against extracted shapes data."""
        validator = TextAdditionValidator(extracted_shapes_data)
        errors = validator.validate(text_data)

        if errors:
            print("ERROR: Invalid shapes in text data JSON:")
            for error in errors:
                print(f"  - {error}")
            print("\nPlease check the inventory and update your text data JSON.")
            raise ValidationError(f"Found {len(errors)} validation error(s)")

    def _calculate_all_fittings(self, extracted_shapes_data: ExtractedShapesData, text_data: dict) -> dict[str, FittingResult]:
        """Pre-calculate fitting for all shapes with text data."""
        fitting_results = {}

        for slide_key, shapes_data in text_data.items():
            if not slide_key.startswith("slide-"):
                continue

            if slide_key not in extracted_shapes_data:
                continue

            for shape_key, shape_text_data in shapes_data.items():
                if "paragraphs" not in shape_text_data:
                    continue

                if shape_key not in extracted_shapes_data[slide_key]:
                    continue

                shape_data = extracted_shapes_data[slide_key][shape_key]
                if not getattr(shape_data.shape, "has_text_frame", False):
                    continue

                result = self.text_fitter.find_fitting_reduction(
                    shape_data.shape, shape_text_data, slide_key, shape_key
                )

                fitting_results[f"{slide_key}/{shape_key}"] = result

        return fitting_results

    def _report_overflow_failures(self, failed_fittings: list[FittingResult], extracted_shapes_data: ExtractedShapesData) -> None:
        """Report detailed information about shapes that cannot fit."""
        print("\nERROR: Text overflow cannot be resolved for the following shapes:\n")

        for result in failed_fittings:
            shape_data = extracted_shapes_data[result.slide_key][result.shape_key]
            shape_height = shape_data.height

            print(f"  {result.slide_key}/{result.shape_key}:")
            print(f"    - Shape height: {shape_height:.2f}\"")
            print(f"    - Reduction applied: {result.reduction}pt")
            if result.overflow_inches:
                print(f"    - Overflow at minimum font sizes: {result.overflow_inches:.2f}\"")
                reduction_pct = int((result.overflow_inches / (shape_height + result.overflow_inches)) * 100)
                print(f"    - Suggestion: Reduce content by ~{reduction_pct}% or use a larger placeholder")
            print()

    def _process_shapes(self, prs, extracted_shapes_data: ExtractedShapesData, text_data: dict, fitting_results: dict[str, FittingResult]) -> dict:
        """Process all shapes and add text with fitted font sizes."""
        stats = {"processed": 0, "cleared": 0, "added": 0}

        for slide_key, shapes_dict in extracted_shapes_data.items():
            if not slide_key.startswith("slide-"):
                continue

            slide_index = int(slide_key.split("-")[1])
            if slide_index >= len(prs.slides):
                print(f"Warning: Slide {slide_index} not found")
                continue

            for shape_key, shape_data in shapes_dict.items():
                stats["processed"] += 1

                shape = shape_data.shape
                if not shape:
                    print(f"Warning: {shape_key} has no shape reference")
                    continue

                # The inventory includes GraphicFrame tables, which have no
                # text_frame at all. Reaching for one raised AttributeError and
                # took the whole command down, so `add-text` failed on any deck
                # containing a table — including one it had just added.
                if not getattr(shape, "has_text_frame", False):
                    continue

                text_frame = shape.text_frame
                text_frame.clear()
                stats["cleared"] += 1

                shape_text_data = text_data.get(slide_key, {}).get(shape_key, {})
                if "paragraphs" not in shape_text_data:
                    continue

                stats["added"] += 1

                # Get fitting result for this shape
                fitting_key = f"{slide_key}/{shape_key}"
                fitting_result = fitting_results.get(fitting_key)
                reduction = fitting_result.reduction if fitting_result else 0

                # The size each paragraph starts from: font_size, else what it inherits from layout and master
                base_sizes = paragraph_base_sizes(shape, shape_text_data["paragraphs"])

                self._add_paragraphs(text_frame, shape_text_data["paragraphs"], reduction, base_sizes)

                # Apply shape-level formatting properties if present
                shape_level_keys = {
                    "fill_type", "fill_color", "fill_theme_color",
                    "border_visible", "border_color", "border_theme_color",
                    "border_weight_pt", "border_dash",
                    "word_wrap", "autofit",
                    "text_margin_top", "text_margin_left", "text_margin_bottom", "text_margin_right",
                    "vertical_alignment",
                }
                shape_props = {k: v for k, v in shape_text_data.items() if k in shape_level_keys}
                if shape_props:
                    from .text_formatters import ShapeFormatter
                    ShapeFormatter.apply_fill(shape, shape_props)
                    ShapeFormatter.apply_border(shape, shape_props)
                    ShapeFormatter.apply_text_frame_properties(shape, shape_props)

        return stats

    def _add_paragraphs(self, text_frame, paragraphs_data: list, reduction: float, base_sizes: list[float]) -> None:
        """Add paragraphs to a text frame with font size reduction.

        A paragraph without font_size gets no explicit size unless the shape needs a reduction: its
        text inherits the size from layout and master. `base_sizes` (`paragraph_base_sizes`) are the
        sizes a reduction starts from."""

        for i, (para_data, base_size) in enumerate(zip(paragraphs_data, base_sizes)):
            if i == 0:
                paragraph = text_frame.paragraphs[0]
            else:
                paragraph = text_frame.add_paragraph()

            final_size = max(MIN_FONT_SIZE, base_size - reduction)

            # Only pass an override when the shape needs a reduction
            override_font_size = final_size if reduction > 0 else None

            self.processor.apply_properties(paragraph, para_data, override_font_size)

    def _check_results(self, prs) -> None:
        """Post-validation safety check for overflow and warnings."""
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            prs.save(str(tmp_path))

        try:
            updated_shapes_data = extract_text(tmp_path)
            warnings = self.warning_collector.collect_warnings(updated_shapes_data)
        finally:
            tmp_path.unlink()

        if warnings:
            print("\nFormatting warnings detected:")
            for warning in warnings:
                print(f"  - {warning}")

    def _report_results(self, output_path: str, slide_count: int, stats: dict, adjustments: list[FittingResult]) -> None:
        """Report processing results including font size adjustments."""
        if adjustments:
            print("\nFont size adjustments made:")
            for result in adjustments:
                print(f"  - {result}")
            print()

        print(f"Saved updated presentation to: {output_path}")
        print(f"Processed {slide_count} slides")
        print(f"  - Shapes processed: {stats['processed']}")
        print(f"  - Shapes cleared: {stats['cleared']}")
        print(f"  - Shapes with text added: {stats['added']}")


def run_add_text(args) -> None:
    """Entry point from CLI dispatcher."""
    input_pptx = Path(args.input)
    text_data_json = Path(args.text_data)
    output_pptx = Path(args.output)

    if not input_pptx.exists():
        print(f"Error: Input file '{input_pptx}' not found")
        sys.exit(1)

    if not text_data_json.exists():
        print(f"Error: Text data JSON file '{text_data_json}' not found")
        sys.exit(1)

    try:
        text_adder = PresentationTextAdder()
        text_adder.add_text(str(input_pptx), str(text_data_json), str(output_pptx))
    except TextAdditionError as e:
        print(f"Error adding text: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
