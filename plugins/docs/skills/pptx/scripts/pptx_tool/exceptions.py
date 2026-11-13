"""Custom exceptions for text addition operations."""


class TextAdditionError(Exception):
    """Base exception for text addition operations."""
    pass


class ValidationError(TextAdditionError):
    """Raised when text addition data validation fails."""
    pass


class OverflowError(TextAdditionError):
    """Raised when text overflow is detected after adding text."""
    pass
