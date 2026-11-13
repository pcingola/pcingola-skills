"""Audio defect check: high-frequency bursts and sample-step clicks.

Each channel is decoded to float32 at 48 kHz and checked on its own (a
defect in one channel is halved by a mono downmix). A burst is a 10 ms window
whose energy above 16.5 kHz is more than BURST_DB above the median of that
band energy over the windows that contain signal. A click is a sample whose
step from the previous sample is more than CLICK_RATIO times the file's
99.99th-percentile step. Flags of the same kind, in any channel, closer than
50 ms are one event.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import media

BURST_DB = 30.0  # speech sibilants in finished films reach +26 dB above the median
CLICK_RATIO = 3.0

RATE = 48000
WINDOW = 480  # 10 ms
BAND_HZ = 16500.0
MERGE_S = 0.05
EPS = 1e-20
# Reference floor for the burst median: band energy in these unnormalised FFT
# units (sum of |X|^2 over a 480-sample window), about -78 dBFS. Keeps silent
# or band-limited files from measuring bursts against EPS.
FLOOR_DB = -30.0
# Windows with RMS above this (-60 dBFS) contain signal; the burst median is
# taken over them only, so digital silence does not pull it down.
SIGNAL_RMS = 1e-3
MIN_STEP = 1e-3  # floor for the 99.99th-percentile step (mostly silent files)


def decode(path: Path) -> np.ndarray:
    """Float32 samples at RATE, one row per channel."""
    streams = [st for st in media.probe(path)["streams"] if st.get("codec_type") == "audio"]
    if not streams:
        raise media.ToolError(f"{path} has no audio stream")
    channels = int(streams[0].get("channels") or 1)
    out = media.run([media.which("ffmpeg"), "-v", "error", "-i", str(path), "-vn", "-map", "0:a:0",
                     "-ar", str(RATE), "-f", "f32le", "-"], text=False).stdout
    x = np.frombuffer(out, dtype=np.float32)
    return x[:len(x) // channels * channels].reshape(-1, channels).T


def _merge(flags: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """(time, value) flags sorted by time -> (first time, max value) per event."""
    events: list[list[float]] = []
    last = -1.0
    for t, v in flags:
        if events and t - last < MERGE_S:
            events[-1][1] = max(events[-1][1], v)
        else:
            events.append([t, v])
        last = t
    return [(t, v) for t, v in events]


def _stamp(t: float) -> str:
    cs = round(t * 100)
    return f"{cs // 6000:02d}:{cs % 6000 / 100:05.2f}"


def _flags(x: np.ndarray) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """(burst, click) flags as (time, value) in one channel `x` at RATE."""
    bursts: list[tuple[float, float]] = []
    clicks: list[tuple[float, float]] = []
    n = len(x) // WINDOW
    frames = x[:n * WINDOW].reshape(n, WINDOW).astype(np.float64)
    active = np.sqrt((frames ** 2).mean(axis=1)) > SIGNAL_RMS
    if active.any():
        spec = np.fft.rfft(frames, axis=1)
        band = np.fft.rfftfreq(WINDOW, 1.0 / RATE) >= BAND_HZ
        db = 10.0 * np.log10((np.abs(spec[:, band]) ** 2).sum(axis=1) + EPS)
        above = db - max(float(np.median(db[active])), FLOOR_DB)
        bursts = [(i * WINDOW / RATE, float(above[i])) for i in np.flatnonzero(above > BURST_DB)]
    if len(x) > 1:
        step = np.abs(np.diff(x.astype(np.float64)))
        limit = CLICK_RATIO * max(float(np.percentile(step, 99.99)), MIN_STEP)
        clicks = [(i / RATE, float(step[i - 1])) for i in np.flatnonzero(step > limit) + 1]
    return bursts, clicks


def find(x: np.ndarray) -> list[tuple[float, str]]:
    """(time, line) per event in samples `x` at RATE (one row per channel, or
    one channel), sorted by time."""
    bursts: list[tuple[float, float]] = []
    clicks: list[tuple[float, float]] = []
    for ch in np.atleast_2d(x):
        b, c = _flags(ch)
        bursts += b
        clicks += c
    found = [(t, f"{_stamp(t)} burst +{round(v)} dB") for t, v in _merge(sorted(bursts))]
    found += [(t, f"{_stamp(t)} click step {v:.2f}") for t, v in _merge(sorted(clicks))]
    return sorted(found)


def check(path: Path | str) -> list[str]:
    """One line per audio defect in the file, sorted by time; [] when clean."""
    return [line for _, line in find(decode(Path(path)))]
