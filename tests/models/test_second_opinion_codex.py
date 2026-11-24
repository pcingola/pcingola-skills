"""A real review by the Codex CLI through second_opinion_tool, selected by `second_opinion.codex` of the settings
file. Codex uses its own login and model; the test fails when `codex` is not on PATH."""

import shutil

import pytest

from second_opinion_tool import cli
from tests.prereq import require
from tests.settings_env import use_settings, write_config


@pytest.mark.timeout(600)
def test_codex_review_finds_planted_error(tmp_path):
    """With `second_opinion.codex: true` and no --model, run_review sends the brief and a file with a wrong sum to
    Codex and returns findings that match the schema, at least one locating the wrong line, with `model` codex and
    the file recorded by its size on disk."""
    require(shutil.which("codex"), "the Codex CLI (`codex`) on PATH")
    doc = tmp_path / "sums.md"
    doc.write_text("# Sums\n\n- 2 + 2 = 4\n- 3 + 5 = 9\n- 10 + 1 = 11\n", encoding="utf-8")
    cfg = write_config(tmp_path / "config.yaml", second_opinion={"codex": True})
    with use_settings(cfg):
        result = cli.run_review("Every sum in the file must be arithmetically correct.", [str(doc)])
    assert result["model"] == "codex"
    assert result["files"] == [{"path": str(doc), "kind": "text", "mime_type": "text/plain",
                                "bytes": doc.stat().st_size}]
    assert any("9" in f["evidence"] or "3 + 5" in f["evidence"] for f in result["findings"]), result
