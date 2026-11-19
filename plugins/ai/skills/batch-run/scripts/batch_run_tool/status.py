from enum import StrEnum


class Status(StrEnum):
    """
    Unified status for both journal items and agent terminal signals.

    PENDING         — item not yet processed
    DONE            — completed successfully
    ERROR_TRANSIENT — failed with a transient error; safe to retry
    ERROR_FATAL     — failed with a permanent error; do not retry
    """
    PENDING         = "pending"
    DONE            = "done"
    ERROR_TRANSIENT = "error_transient"
    ERROR_FATAL     = "error_fatal"
