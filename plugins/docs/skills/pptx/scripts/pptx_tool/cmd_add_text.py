"""Add text to PowerPoint presentations with automatic overflow prevention.

The text data JSON structure matches the inventory output format.
All text shapes from the inventory are cleared unless "paragraphs" is specified.
Font sizes are automatically reduced (minimum 12pt) if text would overflow.
"""

import tempfile
from dataclasses import dataclass
from pathlib import Path

from .cmd_extract_shapes import ExtractedShapesData, extract_text
from .common import load_data_json, require_file
from .exceptions import PptxError, TextAdditionError, TextOverflowError, ValidationError
from .pptx import print_unexpected_error
from .text_fitting import FittingResult, TextFitter, MIN_FONT_SIZE, paragraph_base_sizes
from .text_formatters import ParagraphProcessor
from .text_validators import TextAdditionValidator, WarningCollector
from pptx import Presentation


@dataclass
class ShapeStats:
    """Shape counts of one add-text run: shapes walked, text frames cleared, shapes given text."""
    processed: int = 0
    cleared: int = 0
    added: int = 0


@dataclass(frozen=True)
class TextAdded:
    """What `add_text` did, in the order the CLI reports it: warnings while writing, formatting
    warnings of the result, font size adjustments, the output path, slide count and shape counts."""
    warnings: list[str]
    formatting_warnings: list[str]
    adjustments: list[FittingResult]
    output_path: Path
    slide_count: int
    stats: ShapeStats


class PresentationTextAdder:
    """Main class for adding text to presentations with overflow prevention."""

    def __init__(self):
        self.processor = ParagraphProcessor()
        self.warning_collector = WarningCollector()
        self.text_fitter = TextFitter()
        self.warnings: list[str] = []

    def add_text(self, input_path: Path, text_data: dict, output_path: Path) -> TextAdded:
        """Add text from the text data JSON (`text_data`) to the deck with auto-fitting and save it.

        Invalid data raises ValidationError, and text that cannot fit raises TextOverflowError,
        each with detail lines.
        """
        require_file(input_path, f"Input file '{input_path}' not found")
        prs = Presentation(str(input_path))
        extracted_shapes_data = extract_text(input_path, prs)

        self._validate_text_data(extracted_shapes_data, text_data)

        # Pre-calculate fitting for all shapes
        fitting_results = self._calculate_all_fittings(extracted_shapes_data, text_data)

        # Check for unresolvable overflow
        failed_fittings = [r for r in fitting_results.values() if not r.fits]
        if failed_fittings:
            raise TextOverflowError(
                f"Text overflow cannot be resolved for {len(failed_fittings)} shape(s)",
                self._overflow_report(failed_fittings, extracted_shapes_data),
            )

        # Apply text with adjusted font sizes
        stats = self._process_shapes(prs, extracted_shapes_data, text_data, fitting_results)

        # Post-validation safety check
        formatting_warnings = self._check_results(prs)

        prs.save(str(output_path))

        adjustments = [r for r in fitting_results.values() if r.adjusted]
        return TextAdded(list(self.warnings), formatting_warnings, adjustments, output_path, len(prs.slides), stats)

    def _validate_text_data(self, extracted_shapes_data: ExtractedShapesData, text_data: dict) -> None:
        """Validate text data against extracted shapes data."""
        validator = TextAdditionValidator(extracted_shapes_data)
        errors = validator.validate(text_data)

        if errors:
            raise ValidationError(
                f"Found {len(errors)} validation error(s)",
                [
                    "ERROR: Invalid shapes in text data JSON:",
                    *(f"  - {error}" for error in errors),
                    "\nPlease check the inventory and update your text data JSON.",
                ],
            )

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

    def _overflow_report(self, failed_fittings: list[FittingResult], extracted_shapes_data: ExtractedShapesData) -> list[str]:
        """Lines that describe the shapes that cannot fit, printed before the overflow error."""
        lines = ["\nERROR: Text overflow cannot be resolved for the following shapes:\n"]

        for result in failed_fittings:
            shape_data = extracted_shapes_data[result.slide_key][result.shape_key]
            shape_height = shape_data.height

            lines.append(f"  {result.slide_key}/{result.shape_key}:")
            lines.append(f"    - Shape height: {shape_height:.2f}\"")
            lines.append(f"    - Reduction applied: {result.reduction}pt")
            if result.overflow_inches:
                lines.append(f"    - Overflow at minimum font sizes: {result.overflow_inches:.2f}\"")
                reduction_pct = int((result.overflow_inches / (shape_height + result.overflow_inches)) * 100)
                lines.append(f"    - Suggestion: Reduce content by ~{reduction_pct}% or use a larger placeholder")
            lines.append("")
        return lines

    def _process_shapes(self, prs, extracted_shapes_data: ExtractedShapesData, text_data: dict, fitting_results: dict[str, FittingResult]) -> ShapeStats:
        """Process all shapes and add text with fitted font sizes."""
        stats = ShapeStats()

        for slide_key, shapes_dict in extracted_shapes_data.items():
            if not slide_key.startswith("slide-"):
                continue

            slide_index = int(slide_key.split("-")[1])
            if slide_index >= len(prs.slides):
                self.warnings.append(f"Warning: Slide {slide_index} not found")
                continue

            for shape_key, shape_data in shapes_dict.items():
                stats.processed += 1

                shape = shape_data.shape
                if not shape:
                    self.warnings.append(f"Warning: {shape_key} has no shape reference")
                    continue

                # The inventory includes GraphicFrame tables, which have no
                # text_frame at all. Reaching for one raised AttributeError and
                # took the whole command down, so `add-text` failed on any deck
                # containing a table — including one it had just added.
                if not getattr(shape, "has_text_frame", False):
                    continue

                text_frame = shape.text_frame
                text_frame.clear()
                stats.cleared += 1

                shape_text_data = text_data.get(slide_key, {}).get(shape_key, {})
                if "paragraphs" not in shape_text_data:
                    continue

                stats.added += 1

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

    def _check_results(self, prs) -> list[str]:
        """Post-validation safety check: the formatting warnings of the deck as it will be saved."""
        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            prs.save(str(tmp_path))

        try:
            updated_shapes_data = extract_text(tmp_path)
            return self.warning_collector.collect_warnings(updated_shapes_data)
        finally:
            tmp_path.unlink()


def print_text_added(result: TextAdded) -> None:
    """Print the add-text report."""
    for line in result.warnings:
        print(line)
    if result.formatting_warnings:
        print("\nFormatting warnings detected:")
        for warning in result.formatting_warnings:
            print(f"  - {warning}")
    if result.adjustments:
        print("\nFont size adjustments made:")
        for adjustment in result.adjustments:
            print(f"  - {adjustment}")
        print()

    print(f"Saved updated presentation to: {result.output_path}")
    print(f"Processed {result.slide_count} slides")
    print(f"  - Shapes processed: {result.stats.processed}")
    print(f"  - Shapes cleared: {result.stats.cleared}")
    print(f"  - Shapes with text added: {result.stats.added}")


def run_add_text(args) -> int:
    """Entry point from CLI dispatcher. A TextAdditionError prints as `Error adding text: <message>`."""
    input_pptx = Path(args.input)
    output_pptx = Path(args.output)
    # The CLI reports a missing input before a missing or malformed text data file.
    require_file(input_pptx, f"Input file '{input_pptx}' not found")
    try:
        text_data = load_data_json(Path(args.text_data), "Text data")
        result = PresentationTextAdder().add_text(input_pptx, text_data, output_pptx)
    except TextAdditionError as e:
        for line in e.details:
            print(line)
        print(f"Error adding text: {e}")
        return 1
    except PptxError:
        raise
    except Exception as e:
        return print_unexpected_error(e)
    print_text_added(result)
    return 0
