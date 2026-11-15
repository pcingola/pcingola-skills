"""`speech.resample`: the narrator brings a model's own rate (Fish Audio Drama 3: 44.1 kHz) to its 24 kHz
(voiceover_tool/speech.py docstring)."""

import numpy as np

from voiceover_tool.speech import SAMPLE_RATE, resample


def test_resample_keeps_length_in_seconds_and_pitch():
    """One second of a 440 Hz tone at 44.1 kHz becomes 24000 float32 samples whose spectrum peaks at 440 Hz."""
    t = np.arange(44_100) / 44_100
    out = resample(np.sin(2 * np.pi * 440 * t).astype(np.float32), 44_100, SAMPLE_RATE)
    assert out.dtype == np.float32 and out.shape == (SAMPLE_RATE,)
    peak = np.argmax(np.abs(np.fft.rfft(out))) * SAMPLE_RATE / out.size
    assert abs(peak - 440) <= 1
