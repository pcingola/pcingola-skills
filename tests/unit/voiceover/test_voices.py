"""Reference recordings (`add-voice`), the voices of a model that clones one, through the CLI, and the names of
saved Fish voices (no model is loaded)."""

import wave
from pathlib import Path

import numpy as np
import plugin_settings
import pytest

from tests.settings_env import write_config
from tests.unit.voiceover.cli_run import voiceover
from voiceover_tool.voices import fish_folder, fish_names, reference_path

CHATTERBOX = {"kind": "chatterbox",
              "models": {"chatterbox-turbo": {"url": "http://127.0.0.1:1", "files": ["a"]}}}


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
    and an existing name without --force; `voices` of a model that clones a voice then lists `default` and the new
    voice, and that of a model that does not lists only its own."""
    voices = tmp_path / "voices"
    config = write_config(tmp_path / "config.yaml", voiceover={"voices_dir": str(voices)},
                          providers={"cb": CHATTERBOX, "g": {"kind": "google", "api_key": "k"}},
                          tasks={"speech": "cb:chatterbox-turbo"})
    env = {"SKILLS_CONFIG": str(config)}
    short, ok = write_wav(tmp_path / "short.wav", 3.0), write_wav(tmp_path / "ok.wav", 6.0)

    assert voiceover("voices", **env).stdout.split() == ["default", "(default)"]
    assert voiceover("add-voice", "alice", str(short), **env).returncode == 1
    for bad in ("Alice", "a b", "default", "-x"):
        assert voiceover("add-voice", "--", bad, str(ok), **env).returncode == 1, bad
    p = voiceover("add-voice", "alice", str(ok), **env)
    assert p.returncode == 0 and p.stdout.strip() == str(voices / "alice.wav")
    p = voiceover("add-voice", "alice", str(ok), **env)
    assert p.returncode == 1 and "--force" in p.stderr
    assert voiceover("add-voice", "alice", str(ok), "--force", **env).returncode == 0
    assert voiceover("voices", **env).stdout.split() == ["default", "(default)", "alice"]
    assert voiceover("voices", "--model", "g:tts", **env).stdout.split() == ["Kore", "(default)"]


def test_reference_path(tmp_path):
    """A path to a recording is a voice; `default` is the model's own voice; an unknown name is refused."""
    src = write_wav(tmp_path / "rec.wav", 6.0)
    assert reference_path(str(src)) == src
    assert reference_path("default") is None
    with pytest.raises(ValueError):
        reference_path("bob-not-a-voice")


def test_fish_voice_names(tmp_path):
    """A Fish voice name resolves to `<voices dir>/<name>.fish`, whether saved or new; `default` is the model's own
    voice; a recording (a path, or a name with a recording and no saved Fish voice) and a name with other characters
    are refused, since Fish takes no user recording; `fish_names` lists the saved Fish voices only.
    Guards the voice names of voiceover_tool/voices.py for fish models."""
    voices = tmp_path / "voices"
    (voices / "anna.fish").mkdir(parents=True)
    write_wav(voices / "rec.wav", 6.0)
    plugin_settings.use(write_config(tmp_path / "config.yaml", voiceover={"voices_dir": str(voices)}))
    assert fish_folder("default") is None
    assert fish_folder("anna") == voices / "anna.fish"
    assert fish_folder("nara") == voices / "nara.fish" and not (voices / "nara.fish").exists()
    for recording in ("rec", str(voices / "rec.wav")):
        with pytest.raises(ValueError, match="Fish takes no user recording"):
            fish_folder(recording)
    with pytest.raises(ValueError, match="lowercase letters"):
        fish_folder("Nara")
    assert fish_names() == ["anna"]
