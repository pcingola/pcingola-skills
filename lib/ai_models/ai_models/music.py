"""Music (Pydantic-AI has no music call).

    google      A model with `predict: true` (`providers.<p>.models.<m>`):
                `POST <base_url>/v1/publishers/google/models/<model>:predict` with the key as
                `x-goog-api-key`; one WAV per sample (`sample_count` goes in the instance).
                Other models: a `generate_content_stream` with AUDIO and
                TEXT parts; length and lyrics go in the prompt, images go as parts after it, and
                the text parts (lyrics or song structure) come back with the MP3. A server may
                end the stream with a `[DONE]` line the SDK cannot parse: it is ignored once audio
                arrived, and a stream with no audio is tried again.
    diffusers   `local.DiffusersMusicModel`; a WAV file
    openai      a diffusers music model of a model server (`served`): `POST <base_url>/audio/music` with the
                `openai` SDK's `client.post` (the SDK has no music call); a WAV file

An option the model does not take (`TAKES`) is an `AIModelsError` before any request.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Sequence
from dataclasses import dataclass

from plugin_settings import DiffusersRole, GoogleProvider, ProviderKind

from . import config
from .errors import AIModelsError, ConfigError, explained
from .models import http_client, provider, provider_key, uses_cloud_credentials

VERTEX_URL = "https://aiplatform.googleapis.com"
STREAM_ATTEMPTS = 3
MAX_IMAGES = 10
# The options each kind of music model takes.
TAKES = {"diffusers": {"seconds", "lyrics", "seed"}, "server": {"seconds", "lyrics", "seed"},
         "predict": {"seed", "negative", "samples"}, "stream": {"seconds", "lyrics", "images"}}
# The APIs of a diffusers music model: in process, or on a model server.
DIFFUSERS_APIS = ("diffusers", "server")


@dataclass
class Track:
    """One generated track: the audio file, the text the model returned with it and the stream's
    finish reason (stream models)."""

    audio: bytes
    text: str = ""
    finish_reason: str | None = None


def check_options(api: str, model_id: str, **options) -> None:
    """`AIModelsError` for an option `api` (a key of TAKES) does not take, `seed` with `samples`,
    more than MAX_IMAGES images or fewer than 1 sample. Options that are None or empty are unset."""
    given = {k for k, v in options.items() if v not in (None, (), [], "")}
    bad = sorted(given - TAKES[api])
    if bad:
        takers = {k: [a for a, t in TAKES.items() if k in t] for k in bad}
        raise AIModelsError(f"{model_id} does not take {', '.join(bad)} ("
                            + "; ".join(f"{k}: {', '.join(v)}" for k, v in takers.items()) + ")")
    if {"seed", "samples"} <= given:
        raise AIModelsError("seed and samples are mutually exclusive")
    if len(options.get("images") or ()) > MAX_IMAGES:
        raise AIModelsError(f"{model_id} takes at most {MAX_IMAGES} images")
    if options.get("samples") is not None and options["samples"] < 1:
        raise AIModelsError("samples must be at least 1")


def model_api(model_id: str) -> str:
    """The API of the music model `model_id` (`<provider>:<model>`): a key of TAKES. `ConfigError` for a model that
    cannot serve task music (`config.resolve`)."""
    name, _ = config.split_id(config.resolve(model_id, "music"))
    kind = config.provider(name).kind
    if kind == ProviderKind.DIFFUSERS:
        return "diffusers"
    if kind == ProviderKind.OPENAI:
        return "server"
    entry = config.model_entry(model_id)
    return "predict" if entry is not None and entry.predict else "stream"


def min_crest_db(model_id: str) -> float | None:
    """The `min_crest_db` of the music model `model_id`'s entry (`providers.<p>.models.<m>` of a diffusers provider):
    the crest factor (dB) below which its tracks are loud and compressed, also for a model server's diffusers model.
    None when the entry has no such key, or the model is not a diffusers model (remote kinds)."""
    if model_api(model_id) not in DIFFUSERS_APIS:
        return None
    return config.diffusers_model(model_id, DiffusersRole.MUSIC).min_crest_db


def takes(model_id: str) -> frozenset[str]:
    """The options the music model `model_id` takes (`seed`, `seconds`, ...)."""
    return frozenset(TAKES[model_api(model_id)])


def predict_instance(prompt: str, negative: str | None, seed: int | None, samples: int | None) -> dict:
    """The `:predict` instance; `sample_count` goes in it (the endpoint ignores it under `parameters`)."""
    instance: dict = {"prompt": prompt}
    if negative:
        instance["negative_prompt"] = negative
    if seed is not None:
        instance["seed"] = seed
    if samples:
        instance["sample_count"] = samples
    return instance


async def _predict(spec: GoogleProvider, name: str, model: str, prompt: str, negative: str | None, seed: int | None,
                   samples: int | None) -> list[Track]:
    if uses_cloud_credentials(spec):
        raise ConfigError(f"provider {name!r}: predict models ({model}) need `api_key` in {config.path()}; "
                          "Google Cloud credentials serve its stream models only")
    key = provider_key(spec)
    instance = predict_instance(prompt, negative, seed, samples)
    url = f"{(spec.base_url or VERTEX_URL).rstrip('/')}/v1/publishers/google/models/{model}:predict"
    async with http_client(spec) as http:
        response = await http.post(url, json={"instances": [instance]},
                                   headers={"x-goog-api-key": key})
    response.raise_for_status()
    tracks = [Track(base64.b64decode(b64)) for p in response.json().get("predictions") or []
              if (b64 := p.get("bytesBase64Encoded") or p.get("audioContent"))]
    if not tracks:
        raise AIModelsError(f"{model} returned no audio: {response.text[:300]}")
    return tracks


async def _stream(client, model: str, prompt: str, images: Sequence[tuple[bytes, str]]) -> Track:
    from google.genai import types

    generation = types.GenerateContentConfig(response_modalities=["AUDIO", "TEXT"])
    contents = [types.Part.from_text(text=prompt)]
    contents += [types.Part.from_bytes(data=data, mime_type=mime) for data, mime in images]
    for _ in range(STREAM_ATTEMPTS):
        audio, texts, finish = bytearray(), [], None
        try:
            async for chunk in await client.aio.models.generate_content_stream(model=model, contents=contents,
                                                                                config=generation):
                for cand in chunk.candidates or []:
                    if cand.finish_reason is not None:
                        finish = getattr(cand.finish_reason, "name", str(cand.finish_reason))
                    for part in (cand.content.parts if cand.content and cand.content.parts else []):
                        if part.inline_data and part.inline_data.data:
                            audio.extend(part.inline_data.data)
                        elif part.text:
                            texts.append(part.text)
        except Exception as e:
            if "[DONE]" not in str(e):
                raise
        if audio:
            return Track(bytes(audio), "\n".join(texts).strip(), finish)
    raise AIModelsError(f"{model} returned no audio in {STREAM_ATTEMPTS} attempts")


async def _server(model_id: str, bare: str, prompt: str, seconds: float | None, lyrics: str | None,
                  seed: int | None) -> bytes:
    """The WAV file of the music model `bare` of a model server (`POST /audio/music`)."""
    import httpx2

    from . import served

    entry = config.diffusers_model(model_id, DiffusersRole.MUSIC)
    if lyrics and not entry.lyrics_arg:
        raise AIModelsError(f"{model_id} takes no lyrics (its server's entry has no `lyrics_arg`)")
    body = {k: v for k, v in (("model", bare), ("prompt", prompt), ("seconds", seconds), ("lyrics", lyrics or None),
                              ("seed", seed), ("response_format", "wav")) if v is not None}
    with served.answered(model_id):
        response = await served.client(model_id).post("/audio/music", body=body, cast_to=httpx2.Response)
    return response.content


def stream_prompt(prompt: str, seconds: float | None, lyrics: str | None) -> str:
    """The stream prompt: `prompt`, then the length and the lyrics when given."""
    parts = [prompt]
    if seconds:
        parts.append(f"Length: about {round(seconds)} seconds.")
    if lyrics:
        parts.append(f"Lyrics:\n{lyrics}")
    return "\n\n".join(parts)


async def acompose(prompt: str, *, seconds: float | None = None, lyrics: str | None = None,
                   seed: int | None = None, negative: str | None = None,
                   images: Sequence[tuple[bytes, str]] = (), samples: int | None = None,
                   model: str | None = None) -> list[Track]:
    """The tracks for `prompt` by `model` (else `tasks.music`): WAV, or MP3 from a stream model. One
    track, or `samples` tracks from a predict model. `images` are (bytes, MIME type) pairs for stream
    models; `negative` (what to leave out) and `samples` are predict models'."""
    if not prompt.strip():
        raise AIModelsError("the music prompt is empty")
    model_id = config.resolve(model, "music")
    name, bare = config.split_id(model_id)
    spec = config.provider(name)
    api = model_api(model_id)
    check_options(api, model_id, seconds=seconds, lyrics=lyrics, seed=seed, negative=negative, images=images,
                  samples=samples)
    if api == "diffusers":
        from .local import DiffusersMusicModel

        return [Track(await asyncio.to_thread(DiffusersMusicModel(model_id).compose, prompt, seconds=seconds,
                                              lyrics=lyrics, seed=seed))]
    if api == "server":
        return [Track(await _server(model_id, bare, prompt, seconds, lyrics, seed))]
    with explained(model_id):
        if api == "predict":
            return await _predict(spec, name, bare, prompt, negative, seed, samples)
        return [await _stream(provider(name).client, bare, stream_prompt(prompt, seconds, lyrics), images)]


def compose(prompt: str, **kwargs) -> list[Track]:
    """`acompose` from synchronous code."""
    return asyncio.run(acompose(prompt, **kwargs))
