"""Validation and detection classes for text addition operations."""

from .cmd_extract_shapes import ExtractedShapesData


class TextAdditionValidator:
    """Validates text addition data against presentation inventory."""

    def __init__(self, extracted_shapes_data: ExtractedShapesData):
        self.extracted_shapes_data = extracted_shapes_data

    def validate(self, text_data: dict) -> list[str]:
        """Validate that all referenced shapes exist in the extracted shapes data.

        Args:
            text_data: Dictionary of text addition data

        Returns:
            List of error messages (empty if validation passes)
        """
        errors = []

        for slide_key, shapes_data in text_data.items():
            if not slide_key.startswith("slide-"):
                continue

            if slide_key not in self.extracted_shapes_data:
                errors.append(f"Slide '{slide_key}' not found in extracted shapes data")
                continue

            for shape_key in shapes_data.keys():
                if shape_key not in self.extracted_shapes_data[slide_key]:
                    unused_shapes = self._get_unused_shapes(slide_key, shapes_data)
                    errors.append(
                        f"Shape '{shape_key}' not found on '{slide_key}'. "
                        f"Shapes without text data: {', '.join(sorted(unused_shapes)) if unused_shapes else 'none'}"
                    )

        return errors

    def _get_unused_shapes(self, slide_key: str, shapes_data: dict) -> list[str]:
        """Get list of shapes without text data with content preview.

        Args:
            slide_key: Slide identifier
            shapes_data: Dictionary of shape text data

        Returns:
            List of shape identifiers with content preview
        """
        unused = []
        for shape_key in self.extracted_shapes_data[slide_key].keys():
            if shape_key not in shapes_data:
                shape_data = self.extracted_shapes_data[slide_key][shape_key]
                paragraphs = shape_data.paragraphs
                if paragraphs and paragraphs[0].text:
                    preview = paragraphs[0].text[:50]
                    if len(paragraphs[0].text) > 50:
                        preview += "..."
                    unused.append(f"{shape_key} ('{preview}')")
                else:
                    unused.append(shape_key)
        return unused


class OverflowDetector:
    """Detects text overflow issues in presentations."""

    @staticmethod
    def detect_frame_overflow(extracted_shapes_data: ExtractedShapesData) -> dict[str, dict[str, float]]:
        """Detect text overflow within shape boundaries.

        Args:
            extracted_shapes_data: Extracted shapes data from presentation

        Returns:
            Dictionary mapping slide_key -> shape_key -> overflow_inches
        """
        overflow_map = {}

        for slide_key, shapes_dict in extracted_shapes_data.items():
            for shape_key, shape_data in shapes_dict.items():
                if shape_data.frame_overflow_bottom is not None:
                    if slide_key not in overflow_map:
                        overflow_map[slide_key] = {}
                    overflow_map[slide_key][shape_key] = shape_data.frame_overflow_bottom

        return overflow_map

    @staticmethod
    def check_overflow_increase(
        original: dict[str, dict[str, float]],
        updated: dict[str, dict[str, float]],
        tolerance: float = 0.01
    ) -> list[str]:
        """Check if overflow has increased after adding text.

        Args:
            original: Original overflow data
            updated: Updated overflow data after adding text
            tolerance: Tolerance for rounding errors in inches

        Returns:
            List of error messages for increased overflow
        """
        errors = []

        for slide_key, shape_overflows in updated.items():
            for shape_key, new_overflow in shape_overflows.items():
                original_overflow = original.get(slide_key, {}).get(shape_key, 0.0)

                if new_overflow > original_overflow + tolerance:
                    increase = new_overflow - original_overflow
                    errors.append(
                        f'{slide_key}/{shape_key}: overflow worsened by {increase:.2f}" '
                        f'(was {original_overflow:.2f}", now {new_overflow:.2f}")'
                    )

        return errors


class WarningCollector:
    """Collects warnings from inventory data."""

    @staticmethod
    def collect_warnings(extracted_shapes_data: ExtractedShapesData) -> list[str]:
        """Collect all warnings from extracted shapes data.

        Args:
            extracted_shapes_data: Extracted shapes data from presentation

        Returns:
            List of warning messages
        """
        warnings = []
        for slide_key, shapes_dict in extracted_shapes_data.items():
            for shape_key, shape_data in shapes_dict.items():
                if shape_data.warnings:
                    for warning in shape_data.warnings:
                        warnings.append(f"{slide_key}/{shape_key}: {warning}")
        return warnings
