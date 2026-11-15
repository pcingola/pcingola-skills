"""The crest factor check of `music generate` through the CLI, in a child process with its own config and the small
local test model `ace-step` (ACE-Step 1.5 XL turbo, 8 steps; a real model call on the GPU)."""

import json
import subprocess
import sys
from pathlib import Path

from tests.settings_env import write_config
from tests.subproc import child_env

TEST_MODEL = {"repo": "ACE-Step/acestep-v15-xl-turbo-diffusers", "steps": 8, "guidance": 1.0,
              "duration_arg": "audio_duration", "lyrics_arg": "lyrics"}


def generate(tmp_path: Path, name: str, *argv: str) -> tuple[dict, str]:
    """Run `music generate` with a config whose `ace-step` entry has `min_crest_db: 30` (no track reaches it); return
    the sidecar and stderr."""
    cfg = write_config(tmp_path / "config.yaml", providers={"local": {"kind": "diffusers"}},
                       models={"music": "local:ace-step"}, diffusers={"ace-step": {**TEST_MODEL, "min_crest_db": 30}})
    out = tmp_path / f"{name}.wav"
    p = subprocess.run([sys.executable, "-m", "music_tool", "generate", "calm piano", "--instrumental", "--seconds", "4",
                        "-o", str(out), *argv], env=child_env(SKILLS_CONFIG=str(cfg), HOME=str(Path.home())),
                       capture_output=True, text=True, timeout=900)
    assert p.returncode == 0, p.stderr
    return json.loads(out.with_name(out.name + ".json").read_text(encoding="utf-8")), p.stderr


def test_threshold_from_the_model_entry(tmp_path):
    """The entry's min_crest_db applies: with --crest-attempts 2 both requests are below 30 dB, so two attempts with
    consecutive random seeds, exactly one kept, a warning, and the kept seed as the sidecar's `seed` (music SKILL.md,
    Output)."""
    meta, err = generate(tmp_path, "a", "--crest-attempts", "2")
    crest = meta["crest"]
    attempts = crest["attempts"]
    assert crest["min_crest_db"] == 30 and crest["below_threshold"] is True and "below 30 dB" in err
    assert len(attempts) == 2 and sum(a["kept"] for a in attempts) == 1
    assert attempts[1]["seed"] == attempts[0]["seed"] + 1 and 0 <= attempts[0]["seed"] < 2**31
    kept = next(a for a in attempts if a["kept"])
    assert meta["seed"] == kept["seed"] and crest["crest_db"] == kept["crest_db"][0] < 30
    assert "seed" not in meta["options"]


def test_min_crest_db_zero_turns_the_check_off(tmp_path):
    """--min-crest-db 0 overrides the entry: one request, no `crest` entry, and the random seed drawn for the model
    still recorded as `seed`."""
    meta, err = generate(tmp_path, "b", "--min-crest-db", "0")
    assert "crest" not in meta and "crest factor" not in err
    assert isinstance(meta["seed"], int) and 0 <= meta["seed"] < 2**31
