"""Exceptions of the pptx tool."""


class PptxError(Exception):
    """Base exception of the pptx tool. The CLI prints its message and exits with 1."""


class TextAdditionError(PptxError):
    """Base exception for text addition operations."""


class ValidationError(TextAdditionError):
    """Raised when input data validation fails."""


class TextOverflowError(TextAdditionError):
    """Raised when text overflow is detected after adding text."""
