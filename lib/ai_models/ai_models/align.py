"""Forced alignment of speech against its known text (task `align`), in the caller's process on the CPU (extra
`ai-models[align]`).

A model of provider kind `torchaudio` is a forced-alignment pipeline of `torchaudio.pipelines` by name
(`torchaudio:MMS_FA`). The `url` of its entry (`providers.<p>.models.<m>`, `TorchaudioModel`) is that pipeline's
weights file. `weights.ensure_file` downloads it (with
the TLS context of `tls`) to `weights.model_dir` under its own file name, the name torch.hub looks for, and the
pipeline loads it from there (`model_dir`), so torch.hub downloads nothing. torchaudio 2.11, its last release,
keeps `forced_align` and flags it deprecated. A model stays loaded for the life of the process; it needs no GPU
and no local-model lock.
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from pathlib import Path
from plugin_settings import ProviderKind, TorchaudioModel, TorchaudioProvider

from . import config, local, weights
from .errors import AIModelsError, ConfigError

KIND = ProviderKind.TORCHAUDIO
TASK = "align"

_aligners: dict[str, "Aligner"] = {}
local.on_unload(_aligners.clear)


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


def fetch(spec: TorchaudioProvider, entry: TorchaudioModel, model: str):
    """The weights file of the pipeline, downloaded when missing."""
    return weights.ensure_file(entry.url, weights.model_dir(spec, model) / weights.basename(entry.url))


def aligner(model: str | None = None, weights_dir: str | Path | None = None) -> Aligner:
    """The aligner of `model` (else `tasks.align`), loaded once per process, its weights in the provider's `dir`,
    else `weights_dir` (`WeightsDir.with_dir`); `config.resolve` refuses a model that is not of kind torchaudio or
    has no entry."""
    model_id = config.resolve(model, TASK)
    if model_id not in _aligners:
        name, bare = config.split_id(model_id)
        spec = config.provider(name).with_dir(weights_dir)
        fetch(spec, config.local_entry(model_id), bare)
        try:
            _aligners[model_id] = Aligner(bare, str(weights.model_dir(spec, bare)))
        except (OSError, RuntimeError) as e:
            raise AIModelsError(f"{model_id}: cannot load the aligner: {e}") from e
    return _aligners[model_id]
