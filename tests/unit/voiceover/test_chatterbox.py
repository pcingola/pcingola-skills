"""Chatterbox voice handling through the CLI (no model is loaded)."""

import wave
from pathlib import Path

import numpy as np
import pytest

from tests.unit.voiceover.cli_run import voiceover
from voiceover_tool.chatterbox import ChatterboxBackend, reference_path


def write_wav(path: Path, seconds: float, sr: int = 16_000) -> Path:
    samples = (0.1 * np.sin(np.arange(int(seconds * sr)) / 10) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(samples.tobytes())
    return path


def test_add_voice_rules_and_listing(tmp_path):
    """add-voice copies a recording longer than 5 s to <voices dir>/<name>.wav, refuses bad names, `default`
    and an existing name without --force; `voices` then lists `default` and the new voice."""
    voices = tmp_path / "voices"
    env = {"VOICEOVER_VOICES_DIR": str(voices)}
    short, ok = write_wav(tmp_path / "short.wav", 3.0), write_wav(tmp_path / "ok.wav", 6.0)

    assert voiceover("voices", "--backend", "chatterbox", **env).stdout.split() == ["default", "(default)"]
    assert voiceover("add-voice", "alice", str(short), **env).returncode == 1
    for bad in ("Alice", "a b", "default", "-x"):
        assert voiceover("add-voice", "--", bad, str(ok), **env).returncode == 1, bad
    p = voiceover("add-voice", "alice", str(ok), **env)
    assert p.returncode == 0 and p.stdout.strip() == str(voices / "alice.wav")
    p = voiceover("add-voice", "alice", str(ok), **env)
    assert p.returncode == 1 and "--force" in p.stderr
    assert voiceover("add-voice", "alice", str(ok), "--force", **env).returncode == 0
    assert voiceover("voices", "--backend", "chatterbox", **env).stdout.split() == ["default", "(default)", "alice"]


def test_reference_path(tmp_path):
    """A path to a recording is a voice; `default` is the built-in voice; an unknown name is refused."""
    src = write_wav(tmp_path / "rec.wav", 6.0)
    assert reference_path(str(src)) == src
    assert reference_path("default") is None
    with pytest.raises(ValueError):
        reference_path("bob-not-a-voice")


def test_rejects_style_and_speed():
    with pytest.raises(ValueError):
        ChatterboxBackend(style="calm")
    with pytest.raises(ValueError):
        ChatterboxBackend().synthesize("Hi.", "default", 1.2)
