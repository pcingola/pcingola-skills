"""The request payload and prompts of the model analysis (no model call)."""

import subprocess
import wave

import pytest

from music_tool import describe


def silent_wav(path):
    """Write 0.5 s of mono 16 kHz silence to `path` as WAV."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0\0" * 8000)


def test_prompt_marks_missing_briefs():
    """`verdict_prompt` writes `(none)` for a missing clip brief and the stripped style brief, so the model is told
    which brief is absent instead of guessing one."""
    p = describe.verdict_prompt({"genre": "x"}, None, "  calm  ")
    assert "Clip brief (the prompt this clip was generated from):\n(none)" in p
    assert "Style brief (the style every clip should have):\ncalm" in p


def test_small_file_sent_as_is(tmp_path):
    """`audio_payload` sends a small WAV unchanged with its MIME type, without transcoding."""
    f = tmp_path / "a.wav"
    silent_wav(f)
    assert describe.audio_payload(f) == (f.read_bytes(), "audio/wav")


@pytest.mark.parametrize("name, formats", [("a.m4a", None), ("a.flac", describe.OPENAI_AUDIO)])
def test_transcoded_to_mp3(tmp_path, name, formats):
    """M4A always, and FLAC for a provider that takes WAV and MP3 only, go as MP3."""
    f = tmp_path / name
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=1", str(f)], check=True, timeout=25)
    data, mime = describe.audio_payload(f, formats)
    assert mime == "audio/mpeg" and data != f.read_bytes()
