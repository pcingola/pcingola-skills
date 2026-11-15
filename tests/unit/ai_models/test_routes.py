"""Model routes (`ai_models.routes`, docs/ai_models.md "Model routes"): the user's `routes.md` beside the config
file, then the shipped defaults, unconfigured models left out."""

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
# A config with a diffusers provider holding two of the default models, and an Ollama provider.
LOCAL = {"providers": {"local": {"kind": "diffusers"}, "ollama": {"kind": "ollama"}},
         "diffusers": {"qwen-image": {"repo": "r/q"}, "ltx-2.5": {"repo": "r/l"}}}


def user_table(tmp_path: Path, rows: str) -> Path:
    path = tmp_path / routes.FILE_NAME
    path.write_text("# My routes\n\n" + HEADER + rows, encoding="utf-8")
    return path


def test_defaults_parse_and_name_models_of_the_config_template():
    """The shipped defaults are a valid table, and each default model is a `local` model the config template
    (`config.example.yaml`) names, commented or not."""
    rows = routes.parse(routes.DEFAULTS)
    assert rows
    template = EXAMPLE.read_text(encoding="utf-8")
    for r in rows:
        provider, name = config.split_id(r.model)
        assert provider == "local"
        assert re.search(rf"^\s*#?{re.escape(name)}:", template, re.M), r.model


def test_user_rows_come_first_and_unconfigured_rows_are_dropped(write_config, tmp_path):
    """`table` lists the user's rows before the defaults, so a user row for the same request wins; a row whose
    provider is missing, or whose diffusers model is missing, is left out."""
    write_config(LOCAL)
    user_table(tmp_path, "| image | text in the picture | ollama:x-image | mine |\n"
                         "| image | anything | cloud:gpt | no such provider |\n"
                         "| image | anything | local:not-there | no such diffusers model |\n")
    got = routes.table()
    assert [r.model for r in got] == ["ollama:x-image", "local:qwen-image", "local:qwen-image", "local:ltx-2.5"]
    assert got[0] == routes.Route("image", "text in the picture", "ollama:x-image", "mine")


def test_task_filter(write_config, tmp_path):
    """`table(tasks)` keeps only the rows of those tasks."""
    write_config(LOCAL)
    user_table(tmp_path, "| speech | narration | ollama:tts | mine |\n")
    assert [r.task for r in routes.table(["video"])] == ["video"]
    assert [r.model for r in routes.table(["speech", "image"])] == ["ollama:tts", "local:qwen-image", "local:qwen-image"]


def test_missing_user_file_gives_the_defaults(write_config, tmp_path):
    """Without a user `routes.md` the table is the configured default rows."""
    write_config(LOCAL)
    assert not (tmp_path / routes.FILE_NAME).exists()
    assert [r.model for r in routes.table()] == ["local:qwen-image", "local:qwen-image", "local:ltx-2.5"]


@pytest.mark.parametrize("table, line, message", [
    ("| task | model |\n", 1, "header"),
    (HEADER + "| image | x | local:a |\n", 3, "4 cells"),
    (HEADER + "| image |  | local:a | y |\n", 3, "must not be empty"),
    (HEADER + "| image | x | qwen | y |\n", 3, "<provider>:<model>"),
])
def test_malformed_table_names_file_and_line(write_config, tmp_path, table, line, message):
    """A wrong header, a row of another width, an empty task/when/model cell or a model without a provider is a
    `ConfigError` naming the user's file and the line."""
    write_config(LOCAL)
    (tmp_path / routes.FILE_NAME).write_text(table, encoding="utf-8")
    with pytest.raises(ConfigError, match=re.escape(message)) as e:
        routes.table()
    assert f"{tmp_path / routes.FILE_NAME}:{line}:" in str(e.value)


def test_user_file_beside_skills_config(tmp_path):
    """The user's file is `routes.md` in the directory of the config file that SKILLS_CONFIG names."""
    cfg = write_settings(tmp_path / "elsewhere" / "config.yaml", **LOCAL)
    user_table(cfg.parent, "| video | any clip | ollama:v | mine |\n")
    env = child_env(SKILLS_CONFIG=str(cfg))
    assert py_value("from ai_models import routes", "str(routes.user_path())", env) == str(cfg.parent / "routes.md")
    assert py_value("from ai_models import routes", "[r.model for r in routes.table(['video'])]", env) == [
        "ollama:v", "local:ltx-2.5"]


def test_command_prints_the_table_or_the_error(write_config, tmp_path, capsys):
    """The `routes` command prints the Markdown table of the skill's tasks (or of `--task`) and returns 0; a
    malformed user file prints the error and returns 1."""
    write_config(LOCAL)
    parser = argparse.ArgumentParser()
    routes.command(parser.add_subparsers(dest="command"), ("image", "video"))
    args = parser.parse_args(["routes", "--task", "video"])
    assert args.func(args) == 0
    out = capsys.readouterr().out
    assert out.startswith(HEADER) and "local:ltx-2.5" in out and "local:qwen-image" not in out
    (tmp_path / routes.FILE_NAME).write_text("| a | b |\n", encoding="utf-8")
    args = parser.parse_args(["routes"])
    assert args.func(args) == 1
    assert "header" in capsys.readouterr().err
