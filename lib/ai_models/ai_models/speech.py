"""Text to speech (Pydantic-AI has no speech call).

    ollama, openrouter, openai, azure   OpenAI SDK `audio.speech` of the provider's client;
                                        a `speed` other than 1 is sent (the server may refuse it)
    google                              `generate_content` with an AUDIO response
                                        and a prebuilt voice; raw PCM comes back as a WAV file;
                                        no speed
    vllm-omni                           a vLLM-Omni server in its own environment, started once per
                                        process (`omni`); WAV at the model's rate; instructions through the
                                        provider's `style` format; no speed
    kokoro                              Kokoro in process on the CPU (`kokoro`); 24 kHz WAV; speed 0.5 to 2;
                                        no instructions
    chatterbox                          Chatterbox Turbo in a worker of its own environment (`chatterbox`);
                                        24 kHz WAV; voice cloning; no speed, no instructions

`TRAITS` gives what each kind takes (`Traits`): its default voice, speed range, instructions, whether a voice
may be a reference recording, whether the text may carry inline tags, and whether more request fields (`params`)
pass through to the server (the OpenAI kinds as `extra_body`, vllm-omni in the request body). A provider's `voice` replaces the kind's default voice and its `voices` (a list)
are what `voices` lists; without it `voices` lists the Kokoro voices of a `kokoro` model, else the default voice.
`check` refuses a speed, instructions or `params` the model does not take, before any request or model load.
"""

from __future__ import annotations

import asyncio
import io
import re
import wave
from dataclasses import dataclass
from typing import Any

from . import chatterbox, config, kokoro, omni
from .errors import AIModelsError, ConfigError, explained
from .models import provider

DEFAULT_PCM_RATE = 24_000
OPENAI_KINDS = ("ollama", "openrouter", "openai", "azure")


@dataclass(frozen=True)
class Traits:
    """What a provider kind's speech models take: the default `voice` when the provider sets none, the `speed`
    range (None: only 1), whether they take `instructions` (vllm-omni: when the provider has `style`), whether a
    voice may be a reference recording (`clones`), whether the text may carry inline tags (`tags`) and whether more
    request fields pass through (`params`)."""

    voice: str
    speed: tuple[float, float] | None
    instructions: bool
    clones: bool = False
    tags: bool = False  # inline tags in the text (point tags such as [laughs], speaker tags)
    params: bool = False  # more request fields pass through (`params`)


OPENAI_TRAITS = Traits("marin", (0.25, 4.0), True, params=True)
TRAITS: dict[str, Traits] = {
    **{k: OPENAI_TRAITS for k in ("openrouter", "openai", "azure")},
    "ollama": Traits("default", (0.25, 4.0), True, params=True),
    "google": Traits("Kore", None, True),
    omni.KIND: Traits(omni.DEFAULT_VOICE, None, False, clones=True, tags=True, params=True),
    kokoro.KIND: Traits("af_heart", (0.5, 2.0), False),
    chatterbox.KIND: Traits(chatterbox.DEFAULT_VOICE, None, False, clones=True),
}


@dataclass(frozen=True)
class SpeechModel:
    """A speech model of the config: its id, provider name, provider settings and bare model name."""

    id: str
    provider: str
    spec: dict[str, Any]
    bare: str

    @property
    def kind(self) -> str:
        return self.spec["kind"]

    @property
    def traits(self) -> Traits:
        try:
            return TRAITS[self.kind]
        except KeyError:
            raise ConfigError(f"provider {self.provider!r} of kind {self.kind!r} has no speech models") from None

    @property
    def default_voice(self) -> str:
        return str(self.spec.get("voice") or self.traits.voice)

    @property
    def instructions(self) -> bool:
        return bool(self.spec.get("style")) if self.kind == omni.KIND else self.traits.instructions


def model_of(model: str | None = None) -> SpeechModel:
    """`model` (else `models.speech`) as a `SpeechModel`; `ConfigError` for a kind without speech models."""
    model_id = config.resolve(model, "speech")
    name, bare = config.split_id(model_id)
    spec = (config.template_provider(name, name) if name in (kokoro.KIND, chatterbox.KIND)
            else config.provider(name))
    m = SpeechModel(model_id, name, spec, bare)
    m.traits  # noqa: B018 - refuses a kind without speech models
    return m


def check(model: str | None = None, *, speed: float = 1.0, instructions: str | None = None,
          params: dict[str, Any] | None = None) -> SpeechModel:
    """The `SpeechModel`; `AIModelsError` for a speed, instructions or request parameters it does not take."""
    m = model_of(model)
    rng = m.traits.speed
    if rng is None and speed != 1.0:
        raise AIModelsError(f"{m.id} has no speed setting; ask for the pace in the instructions instead"
                            if m.instructions else f"{m.id} has no speed setting")
    if rng is not None and not rng[0] <= speed <= rng[1]:
        raise AIModelsError(f"{m.id}: speed must be between {rng[0]:g} and {rng[1]:g}")
    if instructions and not m.instructions:
        raise AIModelsError(f"{m.id} takes no instructions (style)")
    if params and not m.traits.params:
        raise AIModelsError(f"{m.id} takes no request parameters")
    return m


def voices(model: str | None = None) -> list[str]:
    """The voices of `model` (else `models.speech`): the provider's `voices`, else a Kokoro model's voices, else
    the default voice. A model whose kind `clones` also takes a reference recording, which is not listed."""
    m = model_of(model)
    if m.spec.get("voices"):
        return [str(v) for v in m.spec["voices"]]
    if m.kind == kokoro.KIND:
        return kokoro.voices(m.spec, m.provider, m.bare)
    return [m.default_voice]


def fetch(model: str | None = None) -> None:
    """Download the weights of a local speech model (kinds kokoro, chatterbox) when missing; other kinds have
    none."""
    m = model_of(model)
    if m.kind == kokoro.KIND:
        kokoro.files(m.spec, m.provider, m.bare)
    elif m.kind == chatterbox.KIND:
        chatterbox.fetch(m.spec, m.provider, m.bare)


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
                  speed: float, params: dict[str, Any] | None = None) -> bytes:
    from openai import omit

    response = await client.audio.speech.create(model=model, input=text, voice=voice, response_format=fmt,
                                                instructions=instructions or omit,
                                                speed=speed if speed != 1.0 else omit, extra_body=params or None)
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


async def aspeak(text: str, *, voice: str | None = None, model: str | None = None,
                 instructions: str | None = None, response_format: str = "wav", speed: float = 1.0,
                 speaker: str | None = None, params: dict[str, Any] | None = None) -> bytes:
    """The audio of `text` by `model` (else `models.speech`) in `voice` (else the model's default voice).
    `instructions` set the style, `speed` the pace, `params` more request fields sent as they are (kinds with
    `Traits.params`), as far as `check` allows. `speaker` names who speaks, for a vllm-omni model with the voice
    `default` (`omni.speak`). Google, vLLM-Omni, Kokoro and Chatterbox return WAV whatever `response_format` says."""
    m = check(model, speed=speed, instructions=instructions, params=params)
    model_id, name, bare, kind, spec = m.id, m.provider, m.bare, m.kind, m.spec
    voice = voice or m.default_voice
    if kind == omni.KIND:
        return omni.speak(name, spec, bare, text, voice, instructions, speed, speaker, params)
    if kind == kokoro.KIND:
        return kokoro.speak(spec, name, bare, text, voice, speed)
    if kind == chatterbox.KIND:
        return chatterbox.speak(spec, name, bare, text, voice)
    p = provider(name)
    with explained(model_id):
        if kind in OPENAI_KINDS:
            audio = await _openai(p.client, bare, text, voice, instructions, response_format, speed, params)
        else:
            audio = await _google(p.client, bare, text, voice, instructions)
    if not audio:
        raise AIModelsError(f"{model_id} returned no audio")
    return audio


def speak(text: str, **kwargs) -> bytes:
    """`aspeak` from synchronous code."""
    return asyncio.run(aspeak(text, **kwargs))
