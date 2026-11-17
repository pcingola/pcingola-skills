"""Integration: one Fish voice across two `voiceover synth` commands, on the tiny random-weight Drama 3 checkpoint of
the `fish` provider of tests/config.yaml (`tests/tiny_fish.py`), on the GPU.

Each command runs in its own child process of the root `dev` environment with a settings file that is TEST_CONFIG
plus a temporary `voiceover.voices_dir`. One command takes about 11-15 s (imports, load of the tiny model, CUDA
graph capture), so the first command runs once in a module fixture and each test runs at most one command.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.settings_env import config_sections, kind_model, write_config
from tests.subproc import child_env, run_module

MODEL = kind_model("fish")
VOICE = "tiny-narrator"
SAVED = ("voice.wav", "voice.txt", "codes.pt")


@dataclass(frozen=True)
class FirstCommand:
    """The first command: its environment `env`, temporary directory `tmp`, the voice folder `folder`, its result
    and the bytes of each saved file (`saved`, empty when the command saved nothing)."""

    env: dict[str, str]
    tmp: Path
    folder: Path
    result: subprocess.CompletedProcess
    saved: dict[str, bytes]


def synth(env: dict[str, str], text: str, out: Path) -> subprocess.CompletedProcess:
    """`voiceover synth` of the one-line script `text` with the fish model and `--voice VOICE` into `out`, without
    word alignment, for at most 25 s."""
    script = out.with_suffix(".txt")
    script.write_text(text + "\n", encoding="utf-8")
    return run_module("voiceover_tool", ["synth", "--script", str(script), "--out-dir", str(out), "--model", MODEL,
                                         "--voice", VOICE, "--no-align"], env)


@pytest.fixture(scope="module")
def first(tmp_path_factory, tiny_fish_folder) -> FirstCommand:
    """The first command with the new Fish voice name VOICE and an empty voices directory."""
    tmp = tmp_path_factory.mktemp("fish-voice")
    voices = tmp / "voices"
    config = write_config(tmp / "config.yaml", **{**config_sections(), "voiceover": {"voices_dir": str(voices)}})
    env = child_env(SKILLS_CONFIG=str(config))
    folder = voices / f"{VOICE}.fish"
    result = synth(env, "The heart pumps blood.", tmp / "one")
    saved = {n: (folder / n).read_bytes() for n in SAVED if (folder / n).is_file()}
    return FirstCommand(env, tmp, folder, result, saved)


def test_first_command_saves_fish_voice(first):
    """The first command with a new Fish voice name saves its first take in `<voices dir>/<name>.fish/`: the WAV,
    the text the model got and the codes; the narrator's first take in the output directory (`voice.wav`) is the
    same WAV. Guards the save of a Fish voice (docs/voiceover.md, Fish voices across commands)."""
    assert first.result.returncode == 0, first.result.stderr
    assert f"saved Fish voice {VOICE!r}" in first.result.stderr, first.result.stderr
    assert sorted(first.saved) == sorted(SAVED)
    assert first.saved["voice.txt"].decode() == "The heart pumps blood."
    assert (first.tmp / "one" / "voice.wav").read_bytes() == first.saved["voice.wav"]


def test_second_command_reuses_saved_fish_voice(first):
    """A second command with the same Fish voice name loads the saved take as the reference and saves nothing: the
    saved files stay as they were, and the narrator's first take of the second command (`voice.wav` in its output
    directory) is the saved take. Guards one Fish voice across the scenes of a film (docs/voiceover.md)."""
    assert first.result.returncode == 0, first.result.stderr
    second = synth(first.env, "The lungs fill with air.", first.tmp / "two")
    assert second.returncode == 0, second.stderr
    assert "saved Fish voice" not in second.stderr, second.stderr
    assert {n: (first.folder / n).read_bytes() for n in SAVED} == first.saved
    assert (first.tmp / "two" / "voice.wav").read_bytes() == first.saved["voice.wav"]
