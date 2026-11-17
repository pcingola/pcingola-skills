"""The crest factor check of `music generate` through the CLI, in a child process with the `music` model of
tests/config.yaml (the tiny ACE-Step pipeline, random weights; a real model call on the GPU). Its tracks are noise."""

import json
from pathlib import Path

import pytest

from tests.settings_env import config_sections, model_entry, task_model, write_config
from tests.subproc import child_env, run_module

pytestmark = pytest.mark.usefixtures("tiny_ace_step_folder")

# The `min_crest_db` of the model entry: above the crest factor of the tiny model's noise tracks (measured: 4.7 dB
# for every seed), so each request is sent again.
THRESHOLD_DB = 10


def generate(tmp_path: Path, name: str, *argv: str) -> tuple[dict, str]:
    """Run `music generate` with TEST_CONFIG whose `music` entry has `min_crest_db: THRESHOLD_DB`; return the
    sidecar and stderr."""
    provider, model = task_model("music").split(":", 1)
    sections = config_sections()
    sections["providers"][provider]["models"][model] = {**model_entry("music"), "min_crest_db": THRESHOLD_DB}
    cfg = write_config(tmp_path / "config.yaml", **sections)
    out = tmp_path / f"{name}.wav"
    p = run_module("music_tool", ["generate", "calm piano", "--instrumental", "--seconds", "4", "-o", str(out),
                                  *argv], child_env(SKILLS_CONFIG=str(cfg)))
    assert p.returncode == 0, p.stderr
    return json.loads(out.with_name(out.name + ".json").read_text(encoding="utf-8")), p.stderr


def test_threshold_from_the_model_entry(tmp_path):
    """The entry's min_crest_db applies: with --crest-attempts 2 both requests are below it, so two attempts with
    consecutive random seeds, exactly one kept, a warning, and the kept seed as the sidecar's `seed` (music SKILL.md,
    Output)."""
    meta, err = generate(tmp_path, "a", "--crest-attempts", "2")
    crest = meta["crest"]
    attempts = crest["attempts"]
    assert crest["min_crest_db"] == THRESHOLD_DB and crest["below_threshold"] is True
    assert f"below {THRESHOLD_DB} dB" in err
    assert len(attempts) == 2 and sum(a["kept"] for a in attempts) == 1
    assert attempts[1]["seed"] == attempts[0]["seed"] + 1 and 0 <= attempts[0]["seed"] < 2**31
    kept = next(a for a in attempts if a["kept"])
    assert meta["seed"] == kept["seed"] and crest["crest_db"] == kept["crest_db"][0] < THRESHOLD_DB
    assert "seed" not in meta["options"]


def test_min_crest_db_zero_turns_the_check_off(tmp_path):
    """--min-crest-db 0 overrides the entry: one request, no `crest` entry, and the random seed drawn for the model
    still recorded as `seed`."""
    meta, err = generate(tmp_path, "b", "--min-crest-db", "0")
    assert "crest" not in meta and "crest factor" not in err
    assert isinstance(meta["seed"], int) and 0 <= meta["seed"] < 2**31
