"""Fish Audio speech models (provider kind `fish`, Drama 3) through fish-speech on an NVIDIA GPU, in the caller's
process (media:voiceover's `cuda` extra, Linux only).

A model entry (`providers.<p>.models.<m>`, `FishModel`) names the checkpoint (`repo`: a Hugging Face repository,
downloaded to the Hugging Face cache, or a local folder), the GB it takes at its peak (`memory`) and its `style`.
The first `speak` of a model loads it (`fish_speech` `init_model` in bfloat16 and the codec of the checkpoint,
`load_codec_model`); it stays loaded until the process exits or calls `local.unload`. The load takes the local-model
lock (`local.hold_lock`) and is refused with `local.memory_error` when `memory` exceeds the free memory, after
waiting for the previous holder's memory and for local Ollama models that unload soon. One synthesis runs at a time
(`_lock`).

`speak` cuts the text at its style tags (`fish_span.split_spans`) and sends each span as one `generate_long`
request, with fish-speech's sampling defaults (temperature 0.7, top-p 0.7, top-k 30). The voice is always
`default`: the first span of a speaker in the process is kept as its `Take` (`fish_takes.Takes`), and its text and
codes are the reference of every later span of that speaker. The answer is one WAV file at the codec's rate
(44.1 kHz), the spans joined in order. `style` (optional) is a format string with `{instructions}` and `{text}`
that puts the caller's instructions into each span without a style tag of its own.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plugin_settings import FishModel, FishProvider, ProviderKind

from . import local
from .errors import AIModelsError
from .fish_span import Span, split_spans
from .fish_take import Take
from .fish_takes import Takes

KIND = ProviderKind.FISH
DEFAULT_VOICE = "default"
DEVICE = "cuda"


@dataclass
class Loaded:
    """A loaded model: the fish-speech `model`, its `decode_one_token` (None for Drama 3) and its `codec`."""

    model: Any
    decode_one_token: Any
    codec: Any

    @property
    def rate(self) -> int:
        """The sample rate of the codec's audio."""
        return int(self.codec.sample_rate)


_models: dict[str, Loaded] = {}  # by model id
takes = Takes()  # the first take of each speaker
_lock = threading.RLock()  # one load or synthesis at a time when callers run in several threads


def _clear() -> None:
    _models.clear()
    takes.clear()


local.on_unload(_clear)


def checkpoint(repo: str) -> Path:
    """The checkpoint folder of `repo`: the folder it names (`local.local_folder`), else the repository's snapshot
    in the Hugging Face cache, downloaded when missing."""
    if (folder := local.local_folder(repo)) is not None:
        return folder
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError

    try:
        return Path(snapshot_download(repo, local_files_only=True))
    except LocalEntryNotFoundError:
        return Path(snapshot_download(repo))


def check_free(entry: FishModel, where: str, waited: bool) -> int:
    """The device's free memory once it holds the model's `memory`, after waiting for the previous holder of the
    lock (`waited`) and for Ollama models that unload soon; `local.memory_error` when it stays below. `where` is
    the model's YAML path."""
    need = int(entry.memory * local.GB)
    free = local.free_memory(DEVICE)
    if waited and need > free:
        free = local.wait_for_memory(DEVICE, need)
    if need > free:
        free = local.wait_for_ollama(DEVICE, need)
    if need > free:
        raise local.memory_error(entry.repo, f"it takes {entry.memory:g} GB at its peak (`memory` of {where}) and "
                                 f"the device has {free / local.GB:.1f} GB free")
    return free


def _load(entry: FishModel, name: str, model: str) -> Loaded:
    """The loaded model `name:model`, loaded on the first call; the caller holds `_lock`."""
    model_id = f"{name}:{model}"
    if model_id in _models:
        return _models[model_id]
    try:
        import torch
        from fish_speech.models.text2semantic.inference import init_model, load_codec_model, resolve_codec_path
    except ImportError as e:
        raise AIModelsError(f"{model_id}: fish-speech is not installed ({e}); media:voiceover installs it on Linux "
                            "when config.yaml has a provider of kind fish") from None
    waited = local.hold_lock()
    try:
        if local.device() != DEVICE:
            raise AIModelsError(f"{model_id}: fish-speech runs only on an NVIDIA GPU (CUDA)")
        free = check_free(entry, f"providers.{name}.models.{model}", waited)
        local.cap_memory(DEVICE, free)
        folder = checkpoint(entry.repo)
        with local.out_of_memory(entry.repo):
            tts, decode_one_token = init_model(str(folder), DEVICE, torch.bfloat16, compile=False,
                                               reference_sampling=None)
            codec = load_codec_model(resolve_codec_path(folder, None), str(tts.device), tts.dtype)
        _models[model_id] = Loaded(tts, decode_one_token, codec)
    except BaseException:
        if not _models:
            local.release_lock()
        raise
    return _models[model_id]


def _codes(m: Loaded, text: str, reference: Take | None):
    """The codec codes [codebooks, frames] of `text`, with `reference` as the voice when given; `AIModelsError`
    when the model answers no audio frame."""
    import torch
    from fish_speech.models.text2semantic.inference import generate_long

    ref = {} if reference is None else {"prompt_text": [reference.text], "prompt_tokens": [reference.codes]}
    codes = [r.codes for r in generate_long(model=m.model, device=DEVICE, decode_one_token=m.decode_one_token,
                                            text=text, compile=False, **ref) if r.action == "sample"]
    if not codes:
        raise AIModelsError(f"the model answered no audio for {text[:80]!r}")
    return torch.cat(codes, 1)


def joined(parts: list, rate: int) -> bytes:
    """One 16-bit mono WAV file at `rate` of the float sample arrays `parts`, in order."""
    import numpy as np

    from .speech import float_wav

    return float_wav(np.concatenate([np.asarray(p, dtype=np.float32).reshape(-1) for p in parts]), rate)


def _span_audio(m: Loaded, model_id: str, span: Span, entry: FishModel, instructions: str | None,
                speaker: str | None):
    """The float samples of one span; the span becomes `speaker`'s first take when it has none."""
    from fish_speech.models.text2semantic.inference import decode_to_audio

    reference = takes.get(model_id, speaker)
    codes = _codes(m, span.said(entry.style, instructions), reference)
    audio = decode_to_audio(codes.to(m.model.device), m.codec).float().cpu().numpy()
    if reference is None:
        takes.keep(model_id, speaker, Take(joined([audio], m.rate), span.styled(entry.style, instructions),
                                            codes.cpu()))
    return audio


def speak(spec: FishProvider, entry: FishModel, name: str, model: str, text: str, voice: str,
          instructions: str | None, speaker: str | None = None) -> bytes:
    """A WAV file at the codec's rate of `text` (module docstring); `speaker` names who speaks (None: the
    narrator)."""
    model_id = f"{name}:{model}"
    if voice != DEFAULT_VOICE:
        raise AIModelsError(f"{model_id} has only the voice {DEFAULT_VOICE!r}; a model of kind chatterbox clones a "
                            "recorded voice")
    spans = split_spans(text)
    if not spans:
        raise AIModelsError(f"{model_id}: no text to speak")
    import torch

    with _lock, torch.inference_mode():
        m = _load(entry, name, model)
        parts = [_span_audio(m, model_id, s, entry, instructions, speaker) for s in spans]
        return joined(parts, m.rate)
