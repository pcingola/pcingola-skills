"""Signal measurements of a clip with librosa, numpy and FFmpeg.

The clip is decoded by FFmpeg to mono float32 at `SR` Hz. Measurements:

- tempo (librosa beat tracker) and beat confidence: the autocorrelation of
  the mean-removed onset envelope at the beat period, divided by its value at
  lag 0 (0 = no periodicity, 1 = perfectly periodic), also at the requested
  tempo when one is given; the coefficient of variation of the inter-beat
  intervals;
- percussive ratio: percussive energy / (harmonic + percussive) after HPSS;
- onset rate per second (onsets of strength at least ONSET_MIN) and mean
  spectral centroid;
- RMS in non-overlapping `WINDOW_SECONDS` windows (dBFS) with a label from
  `level_label`;
- key and mode (none for silence): the time-averaged CQT chroma of the harmonic part correlated
  with the 24 rotations of the Krumhansl-Kessler profiles;
- integrated loudness (LUFS), loudness range (LU) and true peak (dBTP) from
  FFmpeg's `ebur128` filter at the file's own sample rate.

Clips shorter than MIN_TEMPO_KEY_SECONDS get every measurement except tempo
and key.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import warnings
from pathlib import Path

import numpy as np

SR = 22050
HOP = 512
WINDOW_SECONDS = 2.0
# level_label thresholds (dB)
SPARSE_BELOW_MAX_DB = 20.0  # a window this far below the loudest one is "quiet"
SPARSE_FRACTION = 0.25  # more quiet windows than this: sparse
TREND_DB = 3.0  # last third minus first third, inner windows
SILENT_DBFS = -60.0  # loudest window below this: silent
# shorter clips get no tempo or key (too few beats and chroma frames)
MIN_TEMPO_KEY_SECONDS = 2.0
# onset strength is librosa's log-mel spectral flux (dB). librosa normalises
# the envelope before peak picking, so a steady tone yields many tiny "onsets";
# peaks below ONSET_MIN are dropped, and a clip whose 95th percentile is below
# it has no tempo.
ONSET_MIN = 1.0
# pulse_label thresholds on beat confidence
PULSE_REGULAR = 0.3
PULSE_WEAK = 0.15
# tempo_relation: relative tolerance around 1, 1/2 and 2 times the request
TEMPO_TOLERANCE = 0.04
TRUE_PEAK_LIMIT_DBTP = -1.0

NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
# Krumhansl-Kessler key profiles, tonic first
MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


class MeasureError(Exception):
    """Decoding or measuring a clip failed."""


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if path is None:
        raise MeasureError("ffmpeg not found on PATH")
    return path


def decode(path: Path, sr: int = SR) -> np.ndarray:
    """Mono float32 samples at `sr` Hz."""
    proc = subprocess.run(
        [_ffmpeg(), "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise MeasureError(f"ffmpeg could not decode {path.name}: {proc.stderr.decode(errors='replace').strip()[-500:]}")
    y = np.frombuffer(proc.stdout, dtype=np.float32)
    if y.size == 0:
        raise MeasureError(f"{path.name}: no audio samples")
    return y.copy()


def db(x: float) -> float:
    return float(20 * np.log10(max(x, 1e-10)))


def window_rms_db(y: np.ndarray, sr: int, seconds: float = WINDOW_SECONDS) -> list[float]:
    """RMS in dBFS of each full `seconds` window; a last partial window of at
    least half a window is kept, and a clip shorter than that is one window."""
    n = int(sr * seconds)
    out = []
    for start in range(0, y.size, n):
        w = y[start:start + n]
        if w.size < n / 2:
            break
        out.append(round(db(float(np.sqrt(np.mean(w.astype(np.float64) ** 2)))), 1))
    if not out and y.size:
        out.append(round(db(float(np.sqrt(np.mean(y.astype(np.float64) ** 2)))), 1))
    return out


def level_label(windows: list[float]) -> tuple[str, float]:
    """`silent`, `sparse`, `building`, `decaying` or `flat`, and the trend in dB.

    Silent: the loudest window is below SILENT_DBFS.
    Sparse: more than SPARSE_FRACTION of the windows are SPARSE_BELOW_MAX_DB
    or more below the loudest. Otherwise the first and last windows (fades)
    are dropped and the mean level of the last third minus that of the first
    third is the trend: at least +TREND_DB building, at most -TREND_DB
    decaying, else flat."""
    if not windows:
        return "sparse", 0.0
    top = max(windows)
    if top < SILENT_DBFS:
        return "silent", 0.0
    quiet = sum(1 for w in windows if w <= top - SPARSE_BELOW_MAX_DB)
    inner = windows[1:-1] if len(windows) >= 5 else windows
    k = max(1, len(inner) // 3)
    trend = round(float(np.mean(inner[-k:]) - np.mean(inner[:k])), 1)
    if quiet / len(windows) > SPARSE_FRACTION:
        return "sparse", trend
    if trend >= TREND_DB:
        return "building", trend
    if trend <= -TREND_DB:
        return "decaying", trend
    return "flat", trend


def beat_confidence(onset_env: np.ndarray, tempo: float, sr: int = SR, hop: int = HOP) -> float:
    """Normalised autocorrelation of the onset envelope at the beat period."""
    if tempo <= 0:
        return 0.0
    x = onset_env - onset_env.mean()
    ac = np.correlate(x, x, mode="full")[x.size - 1:]
    if ac[0] <= 0:
        return 0.0
    ac = ac / ac[0]
    lag = 60.0 * sr / (hop * tempo)
    i = int(round(lag))
    if i >= ac.size - 1:
        return 0.0
    return round(float(np.clip(ac[max(1, i - 1):i + 2].max(), 0.0, 1.0)), 3)


def pulse_label(confidence: float) -> str:
    """`regular`, `weak` or `none`. Beat confidence measures how periodic the
    onsets are, so repeated piano chords score like a drum beat; the
    percussive ratio tells the two apart."""
    if confidence >= PULSE_REGULAR:
        return "regular"
    if confidence >= PULSE_WEAK:
        return "weak"
    return "none"


NO_KEY = {"key": None, "mode": None, "correlation": None, "runner_up": None, "runner_up_correlation": None}


def estimate_key(chroma_mean: np.ndarray) -> dict:
    """Best of the 24 major/minor keys by Pearson correlation with the
    profiles; no key when the chroma is flat (silence)."""
    if not np.all(np.isfinite(chroma_mean)) or np.ptp(chroma_mean) < 1e-9:
        return dict(NO_KEY)
    scores = []
    for tonic in range(12):
        for mode, profile in (("major", MAJOR), ("minor", MINOR)):
            r = float(np.corrcoef(chroma_mean, np.roll(profile, tonic))[0, 1])
            scores.append((r, NOTES[tonic], mode))
    scores.sort(reverse=True)
    (r1, tonic, mode), (r2, tonic2, mode2) = scores[0], scores[1]
    return {"key": tonic, "mode": mode, "correlation": round(r1, 3),
            "runner_up": f"{tonic2} {mode2}", "runner_up_correlation": round(r2, 3)}


def tempo_relation(measured: float | None, requested: float | None, tol: float = TEMPO_TOLERANCE) -> str | None:
    """`match`, `half` (measured is half the request), `double`, or `differs`;
    None without both values. Beat trackers often lock to half or double time."""
    if not measured or not requested:
        return None
    ratio = measured / requested
    for name, target in (("match", 1.0), ("half", 0.5), ("double", 2.0)):
        if abs(ratio / target - 1) <= tol:
            return name
    return "differs"


_EBU = {
    "integrated_lufs": re.compile(r"Integrated loudness:\s*\n\s*I:\s*(-?[\d.]+|-inf)\s*LUFS"),
    "loudness_range_lu": re.compile(r"Loudness range:\s*\n\s*LRA:\s*(-?[\d.]+)\s*LU"),
    "true_peak_dbtp": re.compile(r"True peak:\s*\n\s*Peak:\s*(-?[\d.]+|-inf)\s*dBFS"),
}


def parse_ebur128(stderr: str) -> dict:
    """Integrated loudness, loudness range and true peak from the ebur128 summary."""
    text = stderr[stderr.rfind("Summary:"):] if "Summary:" in stderr else stderr
    out: dict = {}
    for key, rx in _EBU.items():
        m = rx.search(text)
        out[key] = None if m is None or m.group(1) == "-inf" else float(m.group(1))
    return out


def loudness(path: Path) -> dict:
    proc = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-nostats", "-i", str(path), "-vn", "-filter_complex", "ebur128=peak=true",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise MeasureError(f"ffmpeg ebur128 failed on {path.name}: {proc.stderr.strip()[-500:]}")
    return parse_ebur128(proc.stderr)


def measure_samples(y: np.ndarray, sr: int = SR, requested_bpm: float | None = None) -> dict:
    """Every measurement that works on the decoded samples. With
    `requested_bpm`, also the beat confidence at that tempo."""
    import librosa

    # numba repeats a harmless warning when clips are measured in threads
    warnings.filterwarnings("ignore", message="Compilation requested for previously compiled")

    duration = y.size / sr
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    long_enough = duration >= MIN_TEMPO_KEY_SECONDS
    tempo, conf, ibi_cv, beats = None, 0.0, None, np.array([], dtype=int)
    if long_enough and np.percentile(onset_env, 95) >= ONSET_MIN:
        bpm, beats = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, hop_length=HOP)
        tempo = float(np.atleast_1d(bpm)[0]) or None
        ibi = np.diff(librosa.frames_to_time(beats, sr=sr, hop_length=HOP))
        ibi_cv = round(float(ibi.std() / np.median(ibi)), 3) if ibi.size >= 3 else None
        conf = beat_confidence(onset_env, tempo or 0.0, sr, HOP)

    harmonic, percussive = librosa.effects.hpss(y)
    e_h, e_p = float(np.sum(harmonic.astype(np.float64) ** 2)), float(np.sum(percussive.astype(np.float64) ** 2))
    perc_ratio = round(e_p / (e_h + e_p), 3) if e_h + e_p > 0 else 0.0

    onsets = [o for o in librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, hop_length=HOP)
              if onset_env[o] >= ONSET_MIN]
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=HOP)[0]
    windows = window_rms_db(y, sr)
    label, trend = level_label(windows)
    key = (estimate_key(librosa.feature.chroma_cqt(y=harmonic, sr=sr, hop_length=HOP).mean(axis=1))
           if long_enough and label != "silent" else dict(NO_KEY))
    extra = {}
    if requested_bpm and tempo:
        extra["requested_bpm_confidence"] = beat_confidence(onset_env, requested_bpm, sr, HOP)
    return {
        "duration_s": round(duration, 2),
        "tempo_bpm": round(tempo, 1) if tempo else None,
        "beat_count": int(len(beats)),
        "beat_confidence": conf,
        "pulse": pulse_label(conf),
        "ibi_cv": ibi_cv,
        "percussive_ratio": perc_ratio,
        "onset_rate_per_s": round(len(onsets) / duration, 2),
        "spectral_centroid_hz": round(float(np.mean(centroid)), 0),
        "rms_window_s": WINDOW_SECONDS,
        "rms_dbfs": windows,
        "level": label,
        "level_trend_db": trend,
        **key,
        **extra,
    }


def measure(path: Path, requested_bpm: float | None = None) -> dict:
    m = measure_samples(decode(path), requested_bpm=requested_bpm)
    m.update(loudness(path))
    return m


def summary_line(m: dict) -> str:
    """One plain line from a `measure` result."""
    tempo = f"{m['tempo_bpm']:.0f} BPM" if m.get("tempo_bpm") else "no tempo"
    parts = [f"{tempo}, pulse {m['pulse']} (beat confidence {m['beat_confidence']:.2f})",
             f"percussive {m['percussive_ratio']:.2f}",
             f"{m['onset_rate_per_s']:.1f} onsets/s",
             f"centroid {m['spectral_centroid_hz']:.0f} Hz",
             f"level {m['level']} ({m['level_trend_db']:+.1f} dB)",
             f"{m['key']} {m['mode']} (r {m['correlation']:.2f})" if m.get("key") else "no key"]
    if m.get("integrated_lufs") is not None:
        parts.append(f"{m['integrated_lufs']:.1f} LUFS")
    if m.get("true_peak_dbtp") is not None:
        parts.append(f"true peak {m['true_peak_dbtp']:.1f} dBTP")
    return "; ".join(parts)
