"""`create_app`: the FastAPI app of the model server, with its routes and its error bodies.

Every error is an OpenAI-style JSON body `{"error": {"message", "type", "param", "code"}}`: `ServerError` with its
own status; a request that does not validate 400; `ai_models.LocalMemoryError` 507; any other `AIModelsError` and
a Pydantic-AI `UserError` 400 (a request the model cannot serve, or a failed model call; the message says which);
any other exception 500.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from plugin_settings import ModelServerSettings

from . import routes_audio, routes_images, routes_models, routes_ollama, routes_videos
from .server import Server
from .server_error import ErrorType, ServerError


def create_app(settings: ModelServerSettings) -> FastAPI:
    """The app of a `Server` with `settings`; the server starts its keep-alive sweep at startup and unloads every
    model at shutdown. `app.state.server` is the `Server`."""
    from ai_models import AIModelsError, LocalMemoryError
    from pydantic_ai.exceptions import UserError

    server = Server(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await server.start()
        try:
            yield
        finally:
            await server.stop()

    app = FastAPI(title="model-server", lifespan=lifespan)
    app.state.server = server
    for module in (routes_images, routes_audio, routes_videos, routes_models, routes_ollama):
        app.include_router(module.router)

    @app.exception_handler(ServerError)
    async def server_error(request: Request, e: ServerError) -> JSONResponse:
        return e.response()

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, e: RequestValidationError) -> JSONResponse:
        return ServerError(400, str(e)).response()

    @app.exception_handler(LocalMemoryError)
    async def memory(request: Request, e: LocalMemoryError) -> JSONResponse:
        return ServerError(507, str(e), ErrorType.INSUFFICIENT_MEMORY, "insufficient_memory").response()

    @app.exception_handler(AIModelsError)
    async def model_error(request: Request, e: AIModelsError) -> JSONResponse:
        return ServerError(400, str(e), code="model_error").response()

    @app.exception_handler(UserError)
    async def user_error(request: Request, e: UserError) -> JSONResponse:
        return ServerError(400, str(e)).response()

    @app.exception_handler(Exception)
    async def failure(request: Request, e: Exception) -> JSONResponse:
        return ServerError(500, f"{type(e).__name__}: {e}", ErrorType.SERVER).response()

    return app
