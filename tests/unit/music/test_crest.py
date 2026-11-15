"""The crest factor (`measure.crest_db`) and the regeneration check of `generate` (`crest.CrestCheck`)."""

import io
import wave

import numpy as np

from music_tool import measure
from music_tool.crest import DEFAULT_ATTEMPTS, DEFAULT_MIN_CREST_DB, CrestCheck
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
    assert measure.crest_db(sine()) == 3.01
    assert measure.crest_db(np.sign(sine()) * 0.5) == 0.0
    assert measure.crest_db(np.zeros(100)) == 0.0
    assert measure.crest_db(spiky()) > 30


def test_decode_bytes_keeps_every_channel():
    """A stereo WAV with a sine in one channel and silence in the other: all samples count, so the RMS halves
    and the crest factor rises by 3 dB."""
    y = sine(amp=0.5)
    stereo = np.stack([y, np.zeros_like(y)], axis=1).ravel()
    assert abs(measure.crest_db(measure.decode_bytes(wav(y))) - 3.01) < 0.05
    assert abs(measure.crest_db(measure.decode_bytes(wav(stereo, channels=2))) - 6.02) < 0.05


def test_run_stops_at_first_request_above_threshold():
    """Seeds 5, 6, 7 give a sine (3 dB), a spiky track, a sine; the check stops at seed 6 and keeps it
    (music SKILL.md, Output)."""
    tracks = {5: wav(sine()), 6: wav(spiky()), 7: wav(sine())}
    calls = []

    def generate(seed: int | None) -> list[bytes]:
        calls.append(seed)
        return [tracks[seed]]

    checked = CrestCheck(13.0, 3).run(generate, lambda t: t, 5)
    assert calls == [5, 6]
    assert checked.kept.seed == 6 and checked.tracks == [tracks[6]] and not checked.below
    record = checked.record(0)
    assert [a["seed"] for a in record["attempts"]] == [5, 6]
    assert record["attempts"][0]["crest_db"][0] < 13 < record["crest_db"] == record["attempts"][1]["crest_db"][0]
    assert record["below_threshold"] is False and record["min_crest_db"] == 13.0 and record["seed"] == 6


def test_run_keeps_best_when_all_below():
    """Every request below the threshold: all requests run and the highest crest factor is kept."""
    tracks = {1: wav(np.sign(sine()) * 0.5), 2: wav(sine()), 3: wav(np.sign(sine()) * 0.9)}
    checked = CrestCheck(13.0, 3).run(lambda s: [tracks[s]], lambda t: t, 1)
    assert [a.seed for a in checked.attempts] == [1, 2, 3]
    assert checked.kept.seed == 2 and checked.below and checked.record(0)["below_threshold"] is True


def test_run_without_seed_and_with_several_tracks():
    """A model without a seed gets the same request again (seed None); a request with several tracks counts its
    lowest crest factor, and each track's sidecar entry has its own."""
    replies = [[wav(spiky()), wav(sine())], [wav(spiky()), wav(spiky())]]
    calls = []

    def generate(seed: int | None) -> list[bytes]:
        calls.append(seed)
        return replies[len(calls) - 1]

    checked = CrestCheck(13.0, 3).run(generate, lambda t: t, None)
    assert calls == [None, None] and checked.tracks == replies[1] and not checked.below
    assert "seed" not in checked.record(0) and checked.record(1)["crest_db"] > 13
    assert checked.attempts[0].lowest == 3.01


def test_one_attempt_or_zero_threshold_turns_regeneration_off():
    """`MUSIC_CREST_ATTEMPTS: 1` or `MUSIC_MIN_CREST_DB: 0` sends one request; the crest factor is still recorded."""
    for check in (CrestCheck(13.0, 1), CrestCheck(0.0, 3)):
        calls = []
        checked = check.run(lambda s: calls.append(s) or [wav(sine())], lambda t: t, 1)
        assert calls == [1] and checked.record(0)["crest_db"] == 3.01


def test_from_settings(tmp_path):
    """Defaults without the settings; the settings file's values; an invalid value exits naming the key."""
    code = "from music_tool import config, crest\nconfig.load_settings()"
    expr = "[crest.CrestCheck.from_settings().min_crest_db, crest.CrestCheck.from_settings().attempts]"
    plain = write_config(tmp_path / "a.yaml", providers={})
    assert py_value(code, expr, child_env(SKILLS_CONFIG=str(plain))) == [DEFAULT_MIN_CREST_DB, DEFAULT_ATTEMPTS]
    set_ = write_config(tmp_path / "b.yaml", {"MUSIC_MIN_CREST_DB": "14.5", "MUSIC_CREST_ATTEMPTS": "5"}, providers={})
    assert py_value(code, expr, child_env(SKILLS_CONFIG=str(set_))) == [14.5, 5]
    for key, value in (("MUSIC_MIN_CREST_DB", "loud"), ("MUSIC_CREST_ATTEMPTS", "0")):
        bad = write_config(tmp_path / f"{key}.yaml", {key: value}, providers={})
        done = run_python(f"{code}\ncrest.CrestCheck.from_settings()", child_env(SKILLS_CONFIG=str(bad)))
        assert done.returncode != 0 and key in done.stderr, done.stderr
