"""`Ollama`: the Ollama server behind the model server, at `model_server.ollama_url`.

`forward` passes a request through: method, path, query, body and headers (except `Host`), and streams the answer
back as Ollama sends it (server-sent events of a streamed chat included). With `model`, the `model` of each JSON
object of the answer is set to `model` (`with_model`): of a JSON body, of each `data:` line of server-sent events and
of each line of NDJSON, so an answer names the model id the client sent. `model` and `role` describe one model for
the model list: `GET /v1/models/{tag}`, and its role from the `capabilities` of `POST /api/show` (`embedding`, else
`chat`), kept for the process. `resident`, `size` and `unload` are the memory calls of `Residency`: `GET /api/ps`,
the size of a pulled model in `GET /api/tags`, and `POST /api/generate` with `keep_alive: 0`, which unloads any
model, embedding models included.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable

import httpx
from fastapi import Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from .model_role import ModelRole
from .ollama_resident import OllamaResident
from .server_error import ErrorType, ServerError

CONNECT_TIMEOUT_SECONDS = 10.0
# Headers that describe one hop of the connection; the answer of `forward` sets its own.
HOP_HEADERS = frozenset({"host", "content-length", "transfer-encoding", "connection", "keep-alive",
                         "content-encoding"})

# The answer media types whose JSON objects are one per line: server-sent events and NDJSON.
LINE_TYPES = ("text/event-stream", "application/x-ndjson")


def with_model(data: bytes, model: str) -> bytes:
    """`data` with its `model` set to `model` when it is a JSON object that has a `model`, else `data` unchanged."""
    try:
        obj = json.loads(data)
    except ValueError:
        return data
    if not isinstance(obj, dict) or "model" not in obj:
        return data
    obj["model"] = model
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()


def line_with_model(line: bytes, model: str) -> bytes:
    """One line of server-sent events (`data: <JSON>`) or NDJSON (`<JSON>`) with its object's `model` set to
    `model` (`with_model`); its line ending is kept."""
    text = line.rstrip(b"\r\n")
    end = line[len(text):]
    if text.startswith(b"data:"):
        return b"data: " + with_model(text[5:].strip(), model) + end
    return with_model(text, model) + end


async def rewritten(chunks: AsyncIterator[bytes], media_type: str, model: str) -> AsyncIterator[bytes]:
    """`chunks` of an answer of `media_type` with the `model` of its JSON objects set to `model`: line by line for
    `LINE_TYPES`, the whole body for JSON, unchanged for another type."""
    if media_type in LINE_TYPES:
        rest = b""
        async for chunk in chunks:
            *lines, rest = (rest + chunk).split(b"\n")
            if lines:
                yield b"".join(line_with_model(line + b"\n", model) for line in lines)
        if rest:
            yield line_with_model(rest, model)
    elif media_type == "application/json":
        yield with_model(b"".join([chunk async for chunk in chunks]), model)
    else:
        async for chunk in chunks:
            yield chunk


class Ollama:
    """An HTTP client of the Ollama server at `url` (no `/v1`), with `timeout` seconds per request."""

    def __init__(self, url: str, timeout: float) -> None:
        self.url = url.rstrip("/").removesuffix("/v1")
        self.http = httpx.AsyncClient(base_url=self.url,
                                      timeout=httpx.Timeout(timeout, connect=CONNECT_TIMEOUT_SECONDS))
        self.roles: dict[str, ModelRole] = {}

    async def aclose(self) -> None:
        await self.http.aclose()

    def _unreachable(self, e: httpx.HTTPError) -> ServerError:
        return ServerError(502, f"Ollama at {self.url} did not answer: {type(e).__name__}: {e}", ErrorType.UPSTREAM,
                           "ollama_unreachable")

    async def forward(self, request: Request, body: bytes, done: Callable[[], None] | None = None,
                      model: str | None = None) -> StreamingResponse:
        """Ollama's answer to `request` (with `body`, already read), streamed, with `model` in the answer's JSON
        objects when given (module docstring). `done` runs when the answer ends, also when the client goes away or
        Ollama does not answer; it may be called twice (the stream's end and the response's background task), so it
        must be idempotent (`Lease.release`)."""
        headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_HEADERS}
        req = self.http.build_request(request.method, request.url.path, params=request.query_params,
                                      headers=headers, content=body)
        try:
            resp = await self.http.send(req, stream=True)
        except httpx.HTTPError as e:
            if done is not None:
                done()
            raise self._unreachable(e) from e

        media_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()

        async def chunks() -> AsyncIterator[bytes]:
            try:
                body = resp.aiter_bytes()
                async for chunk in (body if model is None else rewritten(body, media_type, model)):
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

    async def model(self, tag: str) -> dict | None:
        """Ollama's object of the model `tag` (`GET /v1/models/{tag}`), None when Ollama has no such model;
        `ServerError` 502 when it does not answer."""
        try:
            r = await self.http.get(f"/v1/models/{tag}")
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise self._unreachable(e) from e

    async def role(self, tag: str) -> ModelRole | None:
        """The role of the model `tag`: embedding when the `capabilities` of `POST /api/show` hold `embedding`,
        else chat; kept for the process. None, and not kept, when Ollama does not answer."""
        if tag not in self.roles:
            try:
                r = await self.http.post("/api/show", json={"model": tag})
                r.raise_for_status()
                caps = r.json().get("capabilities") or []
            except (httpx.HTTPError, ValueError, AttributeError):
                return None
            self.roles[tag] = ModelRole.EMBEDDING if "embedding" in caps else ModelRole.CHAT
        return self.roles[tag]

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
