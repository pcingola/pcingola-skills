"""`Ollama`: the Ollama server behind the model server, at `model_server.ollama_url`.

`forward` passes a request through unchanged: method, path, query, body and headers (except `Host`), and streams
the answer back as Ollama sends it (server-sent events of a streamed chat included). `resident`, `size` and `unload`
are the memory calls of `Residency`: `GET /api/ps`, the size of a pulled model in `GET /api/tags`, and
`POST /api/generate` with `keep_alive: 0`, which unloads any model, embedding models included.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable

import httpx
from fastapi import Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from .ollama_resident import OllamaResident
from .server_error import ErrorType, ServerError

CONNECT_TIMEOUT_SECONDS = 10.0
# Headers that describe one hop of the connection; the answer of `forward` sets its own.
HOP_HEADERS = frozenset({"host", "content-length", "transfer-encoding", "connection", "keep-alive",
                         "content-encoding"})


class Ollama:
    """An HTTP client of the Ollama server at `url` (no `/v1`), with `timeout` seconds per request."""

    def __init__(self, url: str, timeout: float) -> None:
        self.url = url.rstrip("/").removesuffix("/v1")
        self.http = httpx.AsyncClient(base_url=self.url,
                                      timeout=httpx.Timeout(timeout, connect=CONNECT_TIMEOUT_SECONDS))

    async def aclose(self) -> None:
        await self.http.aclose()

    def _unreachable(self, e: httpx.HTTPError) -> ServerError:
        return ServerError(502, f"Ollama at {self.url} did not answer: {type(e).__name__}: {e}", ErrorType.UPSTREAM,
                           "ollama_unreachable")

    async def forward(self, request: Request, body: bytes, done: Callable[[], None] | None = None) -> StreamingResponse:
        """Ollama's answer to `request` (with `body`, already read), streamed. `done` runs when the answer
        ends, also when the client goes away or Ollama does not answer; it may be called twice (the stream's end
        and the response's background task), so it must be idempotent (`Lease.release`)."""
        headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_HEADERS}
        req = self.http.build_request(request.method, request.url.path, params=request.query_params,
                                      headers=headers, content=body)
        try:
            resp = await self.http.send(req, stream=True)
        except httpx.HTTPError as e:
            if done is not None:
                done()
            raise self._unreachable(e) from e

        async def chunks() -> AsyncIterator[bytes]:
            try:
                async for chunk in resp.aiter_raw():
                    yield chunk
            finally:
                await resp.aclose()
                if done is not None:
                    done()

        out = {k: v for k, v in resp.headers.items() if k.lower() not in HOP_HEADERS}
        return StreamingResponse(chunks(), status_code=resp.status_code, headers=out,
                                 background=BackgroundTask(done) if done is not None else None)

    async def get_json(self, path: str) -> dict:
        """The JSON answer of `GET <path>`; `ServerError` 502 when Ollama does not answer or fails."""
        try:
            r = await self.http.get(path)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise self._unreachable(e) from e

    async def resident(self) -> list[OllamaResident]:
        """The models Ollama holds in memory; none when it does not answer."""
        try:
            data = await self.get_json("/api/ps")
        except ServerError:
            return []
        return [OllamaResident.model_validate(m) for m in data.get("models") or []]

    async def size(self, model: str) -> int | None:
        """The bytes of the pulled model `model` (`/api/tags`), None when it is not pulled or Ollama does not
        answer."""
        try:
            data = await self.get_json("/api/tags")
        except ServerError:
            return None
        names = {model, f"{model}:latest"}
        return next((int(m.get("size") or 0) for m in data.get("models") or [] if m.get("name") in names), None)

    async def unload(self, model: str) -> None:
        """Ask Ollama to unload `model` now (`keep_alive: 0`); a failure is ignored, the caller reads the memory
        after it."""
        try:
            await self.http.post("/api/generate", json={"model": model, "keep_alive": 0})
        except httpx.HTTPError:
            pass

    async def models(self) -> list[dict]:
        """The `data` of Ollama's `GET /v1/models`; empty when Ollama does not answer."""
        try:
            return list((await self.get_json("/v1/models")).get("data") or [])
        except ServerError:
            return []
