"""`speech.resample`: the narrator brings a model's own rate (Fish Audio Drama 3: 44.1 kHz) to its 24 kHz
(voiceover_tool/speech.py docstring)."""

import numpy as np

from voiceover_tool.speech import SAMPLE_RATE, resample


def test_resample_keeps_length_in_seconds():
    """`speech.resample` passes the source and target rates to torchaudio in that order and returns a NumPy array:
    one second at 44.1 kHz becomes 24000 float32 samples."""
    t = np.arange(44_100) / 44_100
    out = resample(np.sin(2 * np.pi * 440 * t).astype(np.float32), 44_100, SAMPLE_RATE)
    assert isinstance(out, np.ndarray) and out.dtype == np.float32 and out.shape == (SAMPLE_RATE,)
