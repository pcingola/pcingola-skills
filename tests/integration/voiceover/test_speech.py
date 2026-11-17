"""The `speech` model of tests/config.yaml through voiceover's `Narrator` (a real model call)."""

import numpy as np
import pytest
from plugin_settings import use

from tests.settings_env import TEST_CONFIG, task_model
from voiceover_tool.speech import Narrator


@pytest.fixture(autouse=True)
def _config():
    """TEST_CONFIG in use for the test."""
    use(TEST_CONFIG)
    yield
    use(None)


def test_speech_model():
    """One sentence of the `speech` model of TEST_CONFIG, with a style when the model takes one, comes back as float32
    mono speech of plausible length."""
    narrator = Narrator()
    assert narrator.model == task_model("speech")
    if narrator.instructions:
        narrator = Narrator(style="calm narrator")
    lines = narrator.lines(["The heart pumps blood."])
    narrator.prepare(lines, narrator.default_voice)
    samples = narrator.synthesize(lines[0])
    assert samples.dtype == np.float32 and samples.ndim == 1
    assert 0.5 < samples.size / narrator.sample_rate < 10
    assert float(np.abs(samples).max()) > 0.01
