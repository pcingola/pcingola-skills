"""Model routes (`ai_models.routes`, docs/ai_models.md "Model routes"): per task the default of `models.<task>`,
then the escalation rows of the user's `routes.md` beside the config file, then the shipped ones, unconfigured
models left out."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pytest

from ai_models import ConfigError, config, routes
from tests.settings_env import write_config as write_settings
from tests.subproc import child_env, py_value

EXAMPLE = Path(__file__).resolve().parents[3] / "plugins/setup/skills/settings/assets/config.example.yaml"
HEADER = "| task | when | model | why |\n|---|---|---|---|\n"
# Defaults for image and video, a diffusers provider holding the shipped image model but not the shipped video
# model, and an Ollama provider.
LOCAL = {"providers": {"local": {"kind": "diffusers"}, "ollama": {"kind": "ollama"}},
         "models": {"image": "local:flux2-klein-4b", "video": "local:ltx-2.5"},
         "diffusers": {"flux2-klein-4b": {"repo": "r/f"}, "qwen-image": {"repo": "r/q"}, "ltx-2.5": {"repo": "r/l"}}}


def user_table(tmp_path: Path, rows: str) -> Path:
    path = tmp_path / routes.FILE_NAME
    path.write_text("# My routes\n\n" + HEADER + rows, encoding="utf-8")
    return path


def models(rows: list[routes.Route]) -> list[str]:
    return [r.model for r in rows]


def test_shipped_rows_are_escalations_to_models_of_the_config_template():
    """The shipped table is valid (every `when` begins with `only when`), and each model is a `local` model the
    config template (`config.example.yaml`) names, commented or not."""
    rows = routes.parse(routes.SHIPPED)
    assert rows
    template = EXAMPLE.read_text(encoding="utf-8")
    for r in rows:
        provider, name = config.split_id(r.model)
        assert provider == "local"
        assert re.search(rf"^\s*#?{re.escape(name)}:", template, re.M), r.model


def test_default_row_then_user_rows_then_shipped_rows(write_config, tmp_path):
    """Per task, `table` lists the generated default row of `models.<task>`, then the user's rows, then the shipped
    ones; a row whose provider or diffusers model is missing is left out (here the shipped kandinsky-6 row)."""
    write_config(LOCAL)
    user_table(tmp_path, "| image | only when it is a diagram | ollama:x-image | mine |\n"
                         "| image | only when tested | cloud:gpt | no such provider |\n"
                         "| image | only when tested | local:not-there | no such diffusers model |\n")
    got = routes.table(["image", "video"])
    assert got[0] == routes.Route("image", routes.DEFAULT, "local:flux2-klein-4b", routes.DEFAULT_WHY)
    assert got[1] == routes.Route("image", "only when it is a diagram", "ollama:x-image", "mine")
    assert models(got) == ["local:flux2-klein-4b", "ollama:x-image", "local:qwen-image", "local:qwen-image",
                           "local:ltx-2.5"]


def test_task_filter_and_task_without_default(write_config, tmp_path):
    """`table(tasks)` keeps only those tasks, in the order given; a task without `models.<task>` has no default
    row but keeps its escalation rows."""
    write_config(LOCAL)
    user_table(tmp_path, "| speech | only when tested | ollama:tts | mine |\n")
    assert models(routes.table(["video"])) == ["local:ltx-2.5"]
    assert models(routes.table(["speech", "image"])) == ["ollama:tts", "local:flux2-klein-4b", "local:qwen-image",
                                                         "local:qwen-image"]


def test_missing_user_file_gives_default_and_shipped_rows(write_config, tmp_path):
    """Without a user `routes.md` the table is the default row and the configured shipped rows."""
    write_config(LOCAL)
    assert not (tmp_path / routes.FILE_NAME).exists()
    assert models(routes.table(["image"])) == ["local:flux2-klein-4b", "local:qwen-image", "local:qwen-image"]


@pytest.mark.parametrize("table, line, message", [
    ("| task | model |\n", 1, "header"),
    (HEADER + "| image | only when x | local:a |\n", 3, "4 cells"),
    (HEADER + "| image |  | local:a | y |\n", 3, "must not be empty"),
    (HEADER + "| image | any other image | local:a | y |\n", 3, "must begin with 'only when'"),
    (HEADER + "| image | only when x | qwen | y |\n", 3, "<provider>:<model>"),
])
def test_malformed_table_names_file_and_line(write_config, tmp_path, table, line, message):
    """A wrong header, a row of another width, an empty task/when/model cell, a catch-all `when` (one that does not
    begin with `only when`) or a model without a provider is a `ConfigError` naming the user's file and the line."""
    write_config(LOCAL)
    (tmp_path / routes.FILE_NAME).write_text(table, encoding="utf-8")
    with pytest.raises(ConfigError, match=re.escape(message)) as e:
        routes.table(["image"])
    assert f"{tmp_path / routes.FILE_NAME}:{line}:" in str(e.value)


def test_user_file_beside_skills_config(tmp_path):
    """The user's file is `routes.md` in the directory of the config file that SKILLS_CONFIG names."""
    cfg = write_settings(tmp_path / "elsewhere" / "config.yaml", **LOCAL)
    user_table(cfg.parent, "| video | only when tested | ollama:v | mine |\n")
    env = child_env(SKILLS_CONFIG=str(cfg))
    assert py_value("from ai_models import routes", "str(routes.user_path())", env) == str(cfg.parent / "routes.md")
    assert py_value("from ai_models import routes", "[r.model for r in routes.table(['video'])]", env) == [
        "local:ltx-2.5", "ollama:v"]


def test_command_prints_the_table_or_the_error(write_config, tmp_path, capsys):
    """The `routes` command prints the Markdown table of the skill's tasks (or of `--task`) and returns 0; a
    malformed user file prints the error and returns 1."""
    write_config(LOCAL)
    parser = argparse.ArgumentParser()
    routes.command(parser.add_subparsers(dest="command"), ("image", "video"))
    args = parser.parse_args(["routes", "--task", "video"])
    assert args.func(args) == 0
    out = capsys.readouterr().out
    assert out == HEADER + f"| video | default | local:ltx-2.5 | {routes.DEFAULT_WHY} |\n"
    (tmp_path / routes.FILE_NAME).write_text("| a | b |\n", encoding="utf-8")
    args = parser.parse_args(["routes"])
    assert args.func(args) == 1
    assert "header" in capsys.readouterr().err
