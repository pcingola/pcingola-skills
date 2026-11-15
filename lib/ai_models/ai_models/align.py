"""Forced alignment of speech against its known text (task `align`), in the caller's process on the CPU (extra
`ai-models[align]`).

A model of provider kind `torchaudio` is a forced-alignment pipeline of `torchaudio.pipelines` by name
(`torchaudio:MMS_FA`). The provider's `url` is that pipeline's weights file. `weights.ensure_file` downloads it (with
the TLS context of `tls`) to `weights.model_dir` under its own file name, the name torch.hub looks for, and the
pipeline loads it from there (`model_dir`), so torch.hub downloads nothing. torchaudio 2.11, its last release,
keeps `forced_align` and flags it deprecated. A model stays loaded for the life of the process; it needs no GPU
and no local-model lock.
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import config, weights
from .config import required
from .errors import AIModelsError, ConfigError

KIND = "torchaudio"
TASK = "align"

_aligners: dict[str, "Aligner"] = {}


class Aligner:
    """A loaded torchaudio forced-alignment pipeline. `tokens` are what its tokenizer takes (MMS_FA: lowercase
    letters and apostrophes)."""

    def __init__(self, pipeline: str, model_dir: str) -> None:
        import torch
        import torchaudio

        bundle = getattr(torchaudio.pipelines, pipeline, None)
        if bundle is None or not hasattr(bundle, "get_aligner"):
            raise ConfigError(f"torchaudio has no forced-alignment pipeline {pipeline!r}")
        self._torch = torch
        self._resample = torchaudio.functional.resample
        self.model = bundle.get_model(dl_kwargs={"model_dir": model_dir})
        self.model.eval()
        self.tokenizer = bundle.get_tokenizer()
        self.aligner = bundle.get_aligner()
        self.sample_rate = int(bundle.sample_rate)

    def align(self, samples, rate: int, tokens: Sequence[str]) -> list[tuple[float, float]]:
        """One (start, end) in seconds from the start of `samples` (mono float32 at `rate` Hz) per token."""
        import numpy as np

        torch = self._torch
        wav = torch.from_numpy(np.ascontiguousarray(samples, dtype=np.float32)).unsqueeze(0)
        if rate != self.sample_rate:
            wav = self._resample(wav, rate, self.sample_rate)
        with torch.inference_mode():
            emission, _ = self.model(wav)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*forced_align has been deprecated.*")
            spans = self.aligner(emission[0], self.tokenizer(list(tokens)))
        ratio = wav.size(1) / emission.size(1) / self.sample_rate
        return [(sp[0].start * ratio, sp[-1].end * ratio) for sp in spans]


def spec_of(model_id: str) -> tuple[str, dict[str, Any], str]:
    """(provider name, its settings, the pipeline name) of an align model id."""
    name, bare = config.split_id(model_id)
    spec = config.provider(name)
    if spec["kind"] != KIND:
        raise ConfigError(f"provider {name!r} of kind {spec['kind']!r} has no align models; kind: {KIND}")
    return name, spec, bare


def fetch(spec: dict[str, Any], name: str, model: str):
    """The weights file of the pipeline, downloaded when missing."""
    url = str(required(spec, "url", name))
    return weights.ensure_file(url, weights.model_dir(spec, model) / weights.basename(url))


def aligner(model: str | None = None, weights_dir: str | Path | None = None) -> Aligner:
    """The aligner of `model` (else `models.align`), loaded once per process, its weights in the provider's `dir`,
    else `weights_dir` (`weights.with_dir`)."""
    model_id = config.resolve(model, TASK)
    if model_id not in _aligners:
        name, spec, bare = spec_of(model_id)
        spec = weights.with_dir(spec, weights_dir)
        fetch(spec, name, bare)
        try:
            _aligners[model_id] = Aligner(bare, str(weights.model_dir(spec, bare)))
        except (OSError, RuntimeError) as e:
            raise AIModelsError(f"{model_id}: cannot load the aligner: {e}") from e
    return _aligners[model_id]
