"""Text to speech (Pydantic-AI has no speech call).

    ollama, openrouter, openai, azure   OpenAI SDK `audio.speech` of the provider's client;
                                        a `speed` other than 1 is sent (the server may refuse it)
    google                              `generate_content` with an AUDIO response
                                        and a prebuilt voice; raw PCM comes back as a WAV file;
                                        no speed
    vllm-omni                           a vLLM-Omni server in its own environment, started once per
                                        process (`omni`); WAV at the model's rate; instructions through the
                                        provider's `style` format; no speed
"""

from __future__ import annotations

import asyncio
import io
import re
import wave

from . import config, omni
from .errors import AIModelsError, ConfigError, explained
from .models import provider

DEFAULT_PCM_RATE = 24_000
OPENAI_KINDS = ("ollama", "openrouter", "openai", "azure")


def wav(pcm: bytes, rate: int) -> bytes:
    """A 16-bit mono WAV file of little-endian PCM."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm[: len(pcm) - len(pcm) % 2])
    return buf.getvalue()


async def _openai(client, model: str, text: str, voice: str, instructions: str | None, fmt: str,
                  speed: float) -> bytes:
    from openai import omit

    response = await client.audio.speech.create(model=model, input=text, voice=voice, response_format=fmt,
                                                instructions=instructions or omit,
                                                speed=speed if speed != 1.0 else omit)
    return response.content


async def _google(client, model: str, text: str, voice: str, instructions: str | None) -> bytes:
    from google.genai import types

    response = await client.aio.models.generate_content(
        model=model, contents=f"{instructions.strip().rstrip(':')}: {text}" if instructions else text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)))))
    for cand in response.candidates or []:
        for part in (cand.content.parts if cand.content and cand.content.parts else []):
            if part.inline_data and part.inline_data.data:
                data, mime = part.inline_data.data, part.inline_data.mime_type or ""
                if data[:4] == b"RIFF":
                    return data
                rate = re.search(r"rate=(\d+)", mime)
                return wav(data, int(rate.group(1)) if rate else DEFAULT_PCM_RATE)
    raise AIModelsError(f"{model} returned no audio")


async def aspeak(text: str, *, voice: str, model: str | None = None, instructions: str | None = None,
                 response_format: str = "wav", speed: float = 1.0) -> bytes:
    """The audio of `text` by `model` (else `models.speech`) in `voice`. `instructions`
    set the style, `speed` the pace (OpenAI-style kinds only). Google returns WAV whatever
    `response_format` says."""
    model_id = config.resolve(model, "speech")
    name, bare = config.split_id(model_id)
    kind = config.provider(name)["kind"]
    if kind == omni.KIND:
        return omni.speak(name, config.provider(name), bare, text, voice, instructions, speed)
    if kind == "google" and speed != 1.0:
        raise AIModelsError(f"{model_id} has no speed setting; ask for the pace in the instructions instead")
    p = provider(name) if kind in (*OPENAI_KINDS, "google") else None
    with explained(model_id):
        if kind in OPENAI_KINDS:
            audio = await _openai(p.client, bare, text, voice, instructions, response_format, speed)
        elif kind == "google":
            audio = await _google(p.client, bare, text, voice, instructions)
        else:
            raise ConfigError(f"provider {name!r} of kind {kind!r} has no speech models")
    if not audio:
        raise AIModelsError(f"{model_id} returned no audio")
    return audio


def speak(text: str, **kwargs) -> bytes:
    """`aspeak` from synchronous code."""
    return asyncio.run(aspeak(text, **kwargs))
