"""The `speech` backend with the `speech` model of the user's `ai_models` config (a real model call)."""

import numpy as np

from voiceover_tool.backends import get_backend


def test_speech_backend():
    """One sentence, with a style unless the model is an Ollama one (Ollama answers instructions with HTTP 400),
    comes back as float32 mono speech of plausible length."""
    backend = get_backend("speech")
    if backend.kind != "ollama":
        backend = get_backend("speech", style="calm narrator")
    samples = backend.synthesize("The heart pumps blood.", backend.default_voice, 1.0)
    assert samples.dtype == np.float32 and samples.ndim == 1
    assert 0.5 < samples.size / backend.sample_rate < 10
    assert float(np.abs(samples).max()) > 0.01
