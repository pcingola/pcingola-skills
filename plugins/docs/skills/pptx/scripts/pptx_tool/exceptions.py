"""Exceptions of the pptx tool."""

from collections.abc import Sequence


class PptxError(Exception):
    """Base exception of the pptx tool. The CLI prints its message and exits with 1.

    `details` are lines the CLI prints before the message, on the same stream (for
    example the list of validation errors behind "Found 2 validation error(s)").
    """

    def __init__(self, message: str, details: Sequence[str] = ()):
        super().__init__(message)
        self.details = tuple(details)


class InvalidIndicesError(PptxError, ValueError):
    """A comma-separated list of slide indices that does not parse as integers."""


class SlidePositionError(PptxError):
    """An insert position outside the target deck's slide range."""


class TextAdditionError(PptxError):
    """Base exception for text addition operations."""


class ValidationError(TextAdditionError):
    """Raised when input data validation fails."""


class TextOverflowError(TextAdditionError):
    """Raised when text overflow is detected after adding text."""
