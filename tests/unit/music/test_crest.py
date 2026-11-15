"""The crest factor (`measure.crest_db`) and the regeneration of `generate` (`crest.regenerate`)."""

import io
import wave

import numpy as np

from ai_models.music import Track

from music_tool import measure
from music_tool.crest import DEFAULT_ATTEMPTS, regenerate
from tests.settings_env import write_config
from tests.subproc import child_env, py_value, run_python

SR = 8000


def sine(seconds: float = 1.0, amp: float = 1.0) -> np.ndarray:
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
    assert measure.crest_db(sine()) == 3.01
    assert measure.crest_db(np.sign(sine()) * 0.5) == 0.0
    assert measure.crest_db(np.zeros(100)) == 0.0
    assert measure.crest_db(spiky()) > 30


def test_decode_bytes_keeps_every_channel():
    """measure.decode of bytes with sr=None keeps every channel: a stereo WAV with a sine in one channel and silence
    in the other has half the RMS, so the crest factor rises by 3 dB."""
    y = sine(amp=0.5)
    stereo = np.stack([y, np.zeros_like(y)], axis=1).ravel()
    assert abs(measure.crest_db(measure.decode(wav(y), sr=None)) - 3.01) < 0.05
    assert abs(measure.crest_db(measure.decode(wav(stereo, channels=2), sr=None)) - 6.02) < 0.05


def test_regenerate_stops_at_first_request_above_threshold():
    """Seeds 5, 6, 7 give a sine (3 dB), a spiky track, a sine; regenerate stops at seed 6 and keeps it
    (music SKILL.md, Output)."""
    tracks = {5: Track(wav(sine())), 6: Track(wav(spiky())), 7: Track(wav(sine()))}
    calls = []

    def compose(seed: int | None) -> list[Track]:
        calls.append(seed)
        return [tracks[seed]]

    kept, records = regenerate(compose, 13.0, 3, 5)
    assert calls == [5, 6] and kept == [tracks[6]]
    assert [(r["seed"], r["kept"]) for r in records] == [(5, False), (6, True)]
    assert records[0]["crest_db"][0] == 3.01 and records[1]["crest_db"][0] > 13


def test_regenerate_keeps_best_when_all_below():
    """Every request below the threshold: all requests run and the one with the highest crest factor is kept."""
    tracks = {1: Track(wav(np.sign(sine()) * 0.5)), 2: Track(wav(sine())), 3: Track(wav(np.sign(sine()) * 0.9))}
    kept, records = regenerate(lambda s: [tracks[s]], 13.0, 3, 1)
    assert kept == [tracks[2]] and [r["kept"] for r in records] == [False, True, False]


def test_regenerate_without_seed_and_with_several_tracks():
    """Without a seed the same request is sent again (compose(None)) and records have no seed; a request with several
    tracks counts its lowest crest factor."""
    replies = [[Track(wav(spiky())), Track(wav(sine()))], [Track(wav(spiky())), Track(wav(spiky()))]]
    calls = []

    def compose(seed: int | None) -> list[Track]:
        calls.append(seed)
        return replies[len(calls) - 1]

    kept, records = regenerate(compose, 13.0, 3, None)
    assert calls == [None, None] and kept == replies[1]
    assert all("seed" not in r for r in records) and records[0]["crest_db"][1] == 3.01


def test_one_attempt_sends_one_request():
    """MUSIC_CREST_ATTEMPTS 1 sends one request even below the threshold; its crest factor is recorded."""
    calls = []
    kept, records = regenerate(lambda s: calls.append(s) or [Track(wav(sine()))], 13.0, 1, 1)
    assert calls == [1] and records == [{"seed": 1, "crest_db": [3.01], "kept": True}]


def test_attempts_setting(tmp_path):
    """MUSIC_CREST_ATTEMPTS: the default without the setting, the settings file's value, and an exit naming the key
    for a value below 1 or not an integer."""
    code = "from music_tool import config, crest\nconfig.load_settings()"
    plain = write_config(tmp_path / "a.yaml", providers={})
    assert py_value(code, "crest.attempts_setting()", child_env(SKILLS_CONFIG=str(plain))) == DEFAULT_ATTEMPTS
    five = write_config(tmp_path / "b.yaml", {"MUSIC_CREST_ATTEMPTS": "5"}, providers={})
    assert py_value(code, "crest.attempts_setting()", child_env(SKILLS_CONFIG=str(five))) == 5
    for i, value in enumerate(("0", "many")):
        bad = write_config(tmp_path / f"c{i}.yaml", {"MUSIC_CREST_ATTEMPTS": value}, providers={})
        done = run_python(f"{code}\ncrest.attempts_setting()", child_env(SKILLS_CONFIG=str(bad)))
        assert done.returncode != 0 and "MUSIC_CREST_ATTEMPTS" in done.stderr, done.stderr
