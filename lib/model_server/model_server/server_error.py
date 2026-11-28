"""`ServerError`: an error the server answers as an OpenAI-style JSON error body."""

from __future__ import annotations

from enum import StrEnum

from fastapi.responses import JSONResponse
from openai.types.shared import ErrorObject


class ErrorType(StrEnum):
    """The `type` of an error body, as the OpenAI API names them."""

    INVALID_REQUEST = "invalid_request_error"
    NOT_FOUND = "not_found_error"
    INSUFFICIENT_MEMORY = "insufficient_memory_error"
    UPSTREAM = "upstream_error"
    SERVER = "server_error"
    CANCELLED = "cancelled_error"


class ServerError(Exception):
    """An HTTP error with an OpenAI-style body: `{"error": {"message", "type", "param", "code"}}`."""

    def __init__(self, status: int, message: str, type: ErrorType = ErrorType.INVALID_REQUEST,
                 code: str | None = None, param: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.error = ErrorObject(message=message, type=type.value, code=code, param=param)

    def response(self) -> JSONResponse:
        """The JSON response of this error."""
        return JSONResponse(status_code=self.status, content={"error": self.error.model_dump(exclude_none=False)})
