"""`music generate` checks, run as a subprocess with a config file in a temp dir; no model is called."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from music_tool import cli

SCRIPTS = Path(__file__).resolve().parents[3] / "plugins/media/skills/music/scripts"


@pytest.fixture
def music(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("providers:\n  oai: {kind: openai, base_url: http://127.0.0.1:1/v1}\nmodels: {}\n")
    env = {**os.environ, "SKILLS_CONFIG": str(config),
           "PYTHONPATH": os.pathsep.join([str(SCRIPTS), os.environ.get("PYTHONPATH", "")])}

    def run(*argv: str) -> tuple[int, str]:
        p = subprocess.run([sys.executable, "-m", "music_tool", "generate", *argv], env=env, capture_output=True,
                           text=True, timeout=60)
        return p.returncode, p.stderr

    return run


def test_refusals_before_any_model_call(music, tmp_path):
    lyrics = tmp_path / "l.txt"
    lyrics.write_text("la")
    existing = tmp_path / "e.mp3"
    existing.write_bytes(b"x")
    cases = [
        (["-o", str(tmp_path / "a.mp3")], "no prompt"),
        (["piano", "-o", str(tmp_path / "a.ogg")], "--out must end in .mp3 or .wav"),
        (["piano", "-o", str(existing)], "pass --force"),
        (["piano", "--lyrics", str(lyrics), "--instrumental", "-o", str(tmp_path / "a.mp3")], "mutually exclusive"),
        (["piano", "--bpm", "0", "-o", str(tmp_path / "a.mp3")], "--bpm must be positive"),
        (["piano", "-o", str(tmp_path / "a.mp3")], "no model for task 'music'"),
    ]
    for argv, message in cases:
        code, err = music(*argv)
        assert code == 1 and message in err, (argv, err)
    assert existing.read_bytes() == b"x"


def test_sidecar_and_audio_ext():
    """The sidecar appends to the full name (`a.mp3.json`), which analyze and short-video read."""
    assert cli.sidecar(Path("/x/a.mp3"), ".json") == Path("/x/a.mp3.json")
    assert cli.audio_ext(b"RIFF....WAVE") == ".wav"
    assert cli.audio_ext(b"ID3\x04") == ".mp3"


def test_sample_paths():
    """One sample keeps `--out`; several get `<stem>_1` ... `<stem>_N`, which `--force` and analyze see."""
    assert cli.sample_paths(Path("/x/a.wav"), 1) == [Path("/x/a.wav")]
    assert cli.sample_paths(Path("/x/a.wav"), 3) == [Path("/x/a_1.wav"), Path("/x/a_2.wav"), Path("/x/a_3.wav")]


def test_options_the_model_does_not_take(music, tmp_path):
    """Options are refused before any request: by the CLI (`--seed` with `--samples`, an image that is not
    PNG, JPEG or WebP) and by `ai_models.music` for the model's kind (images for lyria-002, a negative
    prompt for Lyria 3, samples for a local model)."""
    (tmp_path / "config.yaml").write_text("providers:\n  g: {kind: google}\n  local: {kind: diffusers}\n"
                                          "models: {}\n")
    gif = tmp_path / "a.gif"
    gif.write_bytes(b"GIF8")
    png = tmp_path / "a.png"
    png.write_bytes(b"\x89PNG")
    out = str(tmp_path / "o.wav")
    cases = [
        (["piano", "--seed", "1", "--samples", "2", "-o", out], "--seed and --samples are mutually exclusive"),
        (["piano", "--image", str(gif), "-o", out], "use PNG, JPEG or WebP"),
        (["piano", "--model", "g:lyria-002", "--image", str(png), "-o", out], "does not take images"),
        (["piano", "--model", "g:lyria-3-pro-preview", "--negative", "drums", "-o", out], "does not take negative"),
        (["piano", "--model", "local:ace-step", "--samples", "2", "-o", out], "does not take samples"),
    ]
    for argv, message in cases:
        code, err = music(*argv)
        assert code == 1 and message in err, (argv, err)


@pytest.mark.parametrize("text, extra", [
    ("providers:\n  local: {kind: diffusers}\n", "--extra local"),
    ("providers:\n  # local: {kind: diffusers}\n  o: {kind: ollama}\n", ""),
    (None, ""),
])
def test_wrapper_local_extra(tmp_path, text, extra):
    """The wrapper adds `--extra local` to `uv run` exactly when the config of SKILLS_CONFIG has a
    provider of kind diffusers; a commented line or a missing file adds nothing. Runs the wrapper's own
    lines in bash."""
    config = tmp_path / "config.yaml"
    if text is not None:
        config.write_text(text)
    wrapper = (SCRIPTS / "music.sh").read_text().splitlines()
    start = next(i for i, line in enumerate(wrapper) if line.startswith("CONFIG="))
    end = next(i for i, line in enumerate(wrapper) if line.startswith("exec "))
    script = "\n".join([f"source {SCRIPTS.parents[2] / 'lib/uv_env.sh'}", *wrapper[start:end], 'printf %s "$EXTRA"'])
    p = subprocess.run(["bash", "-euc", script], env={"PATH": os.environ["PATH"], "HOME": str(tmp_path),
                                                     "SKILLS_CONFIG": str(config)},
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 0 and p.stdout == extra, p.stderr
