"""Unit tests for the Codex review of second_opinion_tool: the setting that selects it, the prompt, the command line,
the answer check and the files it gets. No test runs Codex."""

import json
from pathlib import Path

import pytest

from second_opinion_tool import codex, files, models, review
from second_opinion_tool.codex import CodexReviewer
from second_opinion_tool.files import ReviewFile
from tests.settings_env import use_settings, write_config

GOOD = {"severity": "fail", "location": "a.md line 2", "issue": "b", "evidence": "c", "suggestion": "d"}


@pytest.fixture
def codex_on(tmp_path):
    """A settings file with `second_opinion.codex: true` and a chat model no test calls."""
    cfg = write_config(tmp_path / "config.yaml", providers={"ollama": {"kind": "ollama"}},
                       tasks={"chat": "ollama:c"}, second_opinion={"codex": True})
    with use_settings(cfg):
        yield cfg


def test_codex_setting_selects_codex_without_model(codex_on):
    """With `second_opinion.codex: true`, the review uses Codex when no --model is given and the given model
    otherwise, and `models` says Codex reviews. Guards the selection by the setting."""
    assert models.uses_codex(None) and not models.uses_codex("ollama:c")
    assert "codex   on" in models.describe()


def test_codex_off_by_default(cli_settings):
    """Without `second_opinion`, the review never uses Codex. Guards the default of the setting."""
    assert not models.uses_codex(None)
    assert "codex   off" in models.describe()


def test_instructions_drop_boundary_paragraph():
    """codex.instructions keeps the review instructions except the paragraph on boundary lines, and adds the
    read-only agent instructions. Guards the prompt of a reviewer that reads the files itself."""
    text = codex.instructions()
    assert "BOUNDARY" not in text and "Do not praise" in text and "read-only sandbox" in text


def test_prompt_and_command(tmp_path):
    """CodexReviewer.prompt names the brief and each file by absolute path; command runs `codex exec` read-only in
    the working directory with the output schema, the answer file, `--image` for each image, and the prompt on
    stdin. Guards the call."""
    r = CodexReviewer("/bin/codex", tmp_path)
    fs = [ReviewFile("a.md", "text", "text/plain", b""), ReviewFile("s.png", "image", "image/png", b"")]
    prompt = r.prompt(" Check the sums. ", fs)
    assert "Brief:\nCheck the sums.\n" in prompt
    assert f"- {Path('a.md').resolve()} (text, text/plain)" in prompt
    cmd = r.command(fs, tmp_path / "s.json", tmp_path / "a.json")
    assert cmd[:4] == ["/bin/codex", "exec", "--sandbox", "read-only"]
    assert cmd[cmd.index("--cd") + 1] == str(tmp_path)
    assert cmd[cmd.index("--output-schema") + 1] == str(tmp_path / "s.json")
    assert cmd[cmd.index("--output-last-message") + 1] == str(tmp_path / "a.json")
    assert cmd[cmd.index("--image") + 1] == str(Path("s.png").resolve()) and cmd.count("--image") == 1
    assert cmd[-1] == "-"


def test_find_fails_without_codex(tmp_path):
    """CodexReviewer.find raises ReviewError naming the setting when `codex` is not on the search path. Guards
    the failure when Codex is not installed."""
    with pytest.raises(review.ReviewError, match="second_opinion.codex is true.*codex is not on PATH"):
        CodexReviewer.find(tmp_path, path=str(tmp_path))


def test_parse_answer():
    """codex.parse_answer returns the checked findings of a valid answer and raises ReviewError for text that is
    not JSON or JSON without the findings. Guards the answer check."""
    got = codex.parse_answer(json.dumps({"summary": " One. ", "findings": [GOOD]}))
    assert got == {"summary": "One.", "findings": [GOOD]}
    for bad in ("", "Looks fine.", "[]", json.dumps({"summary": "s"})):
        with pytest.raises(review.ReviewError, match="not the findings JSON"):
            codex.parse_answer(bad)


def test_locate_checks_without_reading(tmp_path):
    """files.locate classifies a file without reading it into the request, records its size on disk, gives a
    non-UTF-8 file of an unknown type kind `other`, and refuses a missing or empty file. Guards the files of a
    Codex review, which has no size limit."""
    (tmp_path / "a.md").write_text("x\n")
    (tmp_path / "b.bin").write_bytes(b"\xff\xfe\x00\x81")
    (tmp_path / "e.md").write_text("")
    a, b = files.locate_all([str(tmp_path / "a.md"), str(tmp_path / "b.bin")])
    assert (a.kind, a.data, a.record()["bytes"]) == ("text", b"", 2)
    assert (b.kind, b.mime) == ("other", "application/octet-stream")
    for name, msg in (("e.md", "empty file"), ("no.md", "no such file")):
        with pytest.raises(files.FileError, match=msg):
            files.locate(str(tmp_path / name))
