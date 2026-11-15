"""The `speech` model of the user's `ai_models` config through voiceover's `Narrator` (a real model call)."""

import numpy as np

from voiceover_tool.speech import Narrator


def test_speech_model():
    """One sentence, with a style when the model takes one, comes back as float32 mono speech of plausible length."""
    narrator = Narrator()
    if narrator.instructions:
        narrator = Narrator(style="calm narrator")
    lines = narrator.lines(["The heart pumps blood."])
    narrator.prepare(lines, narrator.default_voice)
    samples = narrator.synthesize(lines[0])
    assert samples.dtype == np.float32 and samples.ndim == 1
    assert 0.5 < samples.size / narrator.sample_rate < 10
    assert float(np.abs(samples).max()) > 0.01
