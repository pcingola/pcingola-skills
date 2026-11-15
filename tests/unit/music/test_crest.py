"""The crest factor (`measure.crest_db`) and the regeneration of `generate` (`crest.regenerate`)."""

import io
import wave

import numpy as np

from ai_models.music import Track

from music_tool import measure
from music_tool.crest import regenerate

SR = 8000


def sine(seconds: float = 4.0, amp: float = 1.0) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    return amp * np.sin(2 * np.pi * 440 * t)


def wav(y: np.ndarray, channels: int = 1) -> bytes:
    """A 16-bit WAV file of `y` (interleaved when `channels` > 1)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def spiky() -> np.ndarray:
    """A quiet sine with one full-scale click: a crest factor far above 13 dB."""
    y = sine(amp=0.01)
    y[100] = 1.0
    return y


def test_crest_db():
    """crest_db is sample peak minus RMS in dB: 3.01 for a sine, 0 for a square wave and silence."""
    assert measure.crest_db(sine(), SR) == 3.01
    assert measure.crest_db(np.sign(sine()) * 0.5, SR) == 0.0
    assert measure.crest_db(np.zeros(100), SR) == 0.0
    assert measure.crest_db(spiky(), SR) > 30


def test_crest_db_counts_only_loud_windows():
    """Quiet intros and silence do not count (music SKILL.md, Output): a sine after 4 s of a sine 30 dB lower and 4 s
    of silence has the crest factor of the sine alone, where the whole file would give a higher one."""
    y = np.concatenate([np.zeros(SR * 4), sine(amp=0.03), sine()])
    assert measure.crest_db(y, SR) == 3.01
    assert measure.crest_db(y, SR * 100) > 5


def test_track_crest_db_decodes_every_channel():
    """track_crest_db decodes the file in stereo at 48 kHz: a mono WAV keeps a sine's 3.01 dB, a stereo WAV with the
    sine in one channel and silence in the other has half the RMS, so 6.02 dB (resampling adds a few hundredths)."""
    y = sine(amp=0.5)
    stereo = np.stack([y, np.zeros_like(y)], axis=1).ravel()
    assert abs(measure.track_crest_db(wav(y)) - 3.01) < 0.05
    assert abs(measure.track_crest_db(wav(stereo, channels=2)) - 6.02) < 0.05


def test_regenerate_stops_at_first_request_above_threshold():
    """Seeds 5, 6, 7 give a sine (3 dB), a spiky track, a sine; regenerate stops at seed 6 and keeps it
    (music SKILL.md, Output)."""
    tracks = {5: Track(wav(sine())), 6: Track(wav(spiky())), 7: Track(wav(sine()))}
    calls = []

    def compose(seed: int | None) -> list[Track]:
        calls.append(seed)
        return [tracks[seed]]

    kept, records, failure = regenerate(compose, 13.0, 3, 5)
    assert calls == [5, 6] and kept == [tracks[6]] and failure is None
    assert [(r["seed"], r["kept"]) for r in records] == [(5, False), (6, True)]
    assert records[0]["crest_db"][0] < 3.1 and records[1]["crest_db"][0] > 13


def test_regenerate_keeps_best_when_all_below():
    """Every request below the threshold: all requests run and the one with the highest crest factor is kept."""
    tracks = {1: Track(wav(np.sign(sine()) * 0.5)), 2: Track(wav(sine())), 3: Track(wav(np.sign(sine()) * 0.9))}
    kept, records, _ = regenerate(lambda s: [tracks[s]], 13.0, 3, 1)
    assert kept == [tracks[2]] and [r["kept"] for r in records] == [False, True, False]


def test_regenerate_without_seed_and_with_several_tracks():
    """Without a seed the same request is sent again (compose(None)) and records have no seed; a request with several
    tracks counts its lowest crest factor."""
    replies = [[Track(wav(spiky())), Track(wav(sine()))], [Track(wav(spiky())), Track(wav(spiky()))]]
    calls = []

    def compose(seed: int | None) -> list[Track]:
        calls.append(seed)
        return replies[len(calls) - 1]

    kept, records, _ = regenerate(compose, 13.0, 3, None)
    assert calls == [None, None] and kept == replies[1]
    assert all("seed" not in r for r in records) and records[0]["crest_db"][1] < 3.1


def test_one_attempt_sends_one_request():
    """One attempt sends one request even below the threshold; its crest factor is recorded."""
    calls = []
    kept, records, _ = regenerate(lambda s: calls.append(s) or [Track(wav(sine()))], 13.0, 1, 1)
    assert calls == [1] and len(records) == 1 and records[0]["seed"] == 1 and records[0]["kept"]
    assert records[0]["crest_db"][0] < 3.1


def test_measurement_failure_keeps_the_tracks():
    """A track ffmpeg cannot decode: regenerate returns that request's tracks, kept with no crest factor, and the
    error, instead of discarding the output."""
    bad = [Track(b"not audio")]
    kept, records, failure = regenerate(lambda s: bad, 13.0, 3, 4)
    assert kept == bad and records == [{"seed": 4, "crest_db": None, "kept": True}] and "decode" in failure
