"""Model routes (`ai_models.routes`, docs/ai_models.md "Model routes"): one table, the user's `routes.md` beside
the config file; per task a default row with the model of `tasks.<task>`, then the escalation rows, unconfigured
models left out."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

import pytest
import yaml

from ai_models import ConfigError, config, routes
from tests.settings_env import write_config as write_settings
from tests.subproc import child_env, py_value

ASSETS = Path(__file__).resolve().parents[3] / "plugins/setup/skills/settings/assets"
EXAMPLE = ASSETS / "config.example.yaml"
TEMPLATE = ASSETS / routes.FILE_NAME
HEADER = "| task | model | when | why |\n|---|---|---|---|\n"
# Defaults for image and video, a diffusers provider holding the template's image models but not its video
# escalation models, and an Ollama provider.
LTX = {"repo": "r/l", "pipeline": "P", "fps": 24, "size_multiple": 32, "frame_step": 8, "width": 64, "height": 64,
       "max_frames": 9}
LOCAL = {"providers": {"diffusers": {"kind": "diffusers", "models": {"flux2-klein-4b": {"repo": "r/f"},
                                                                      "qwen-image": {"repo": "r/q"}, "ltx-2.5": LTX}},
                       "ollama": {"kind": "ollama"}},
         "tasks": {"image": "diffusers:flux2-klein-4b", "video": "diffusers:ltx-2.5"}}


def user_table(tmp_path: Path, rows: str) -> Path:
    path = tmp_path / routes.FILE_NAME
    path.write_text("# My routes\n\n" + HEADER + rows, encoding="utf-8")
    return path


def models(rows: list[routes.Route]) -> list[str]:
    return [r.model for r in rows]


def template_default(task: str) -> routes.Route:
    return next(r for r in routes.parse(TEMPLATE) if r.task == task and r.is_default)


def test_template_rows_name_models_of_the_config_template():
    """The setup:settings template `routes.md` is valid; each model is a `diffusers` model that `config.example.yaml`
    names in `providers.diffusers.models`, or a model of a provider it names in `providers`, commented or not; each
    default row names the config template's `tasks.<task>`."""
    rows = routes.parse(TEMPLATE)
    assert rows
    text = EXAMPLE.read_text(encoding="utf-8")
    template = yaml.safe_load(text)
    for r in rows:
        provider, name = config.split_id(r.model)
        key = name if provider == "diffusers" else provider
        assert re.search(rf"^\s*#?{re.escape(key)}:", text, re.M), r.model
        if r.is_default:
            assert template["tasks"][r.task] == r.model, r


def test_default_row_from_config_then_escalations(write_config, tmp_path):
    """With the template as the user's table, `table` lists per task the default row with the model of
    `tasks.<task>` and the table's `why`, then the escalation rows; a row whose provider or diffusers model is
    missing is left out (here z-image-turbo, kandinsky-6 and ltx-video)."""
    write_config(LOCAL)
    shutil.copy(TEMPLATE, tmp_path / routes.FILE_NAME)
    got = routes.table(["image", "video"])
    assert got[0] == routes.Route("image", "diffusers:flux2-klein-4b", routes.DEFAULT, template_default("image").why)
    assert models(got) == ["diffusers:flux2-klein-4b", "diffusers:qwen-image", "diffusers:qwen-image",
                           "diffusers:ltx-2.5"]


def test_user_rows_in_file_order_and_unconfigured_dropped(write_config, tmp_path):
    """Escalation rows keep the file's order; a row of a missing provider or diffusers model, or of a model that
    cannot serve the task (`Config.task_error`: a diffusers model of another role), is left out."""
    write_config(LOCAL)
    user_table(tmp_path, "| image | ollama:x-image | only when it is a diagram | mine |\n"
                         "| image | cloud:gpt | only when tested | no such provider |\n"
                         "| image | diffusers:not-there | only when tested | no such diffusers model |\n"
                         "| image | diffusers:ltx-2.5 | only when tested | a video model |\n"
                         "| image | diffusers:qwen-image | only when text | spelled |\n")
    assert routes.table(["image"])[1:] == [
        routes.Route("image", "ollama:x-image", "only when it is a diagram", "mine"),
        routes.Route("image", "diffusers:qwen-image", "only when text", "spelled")]


def test_config_model_other_than_the_table_default_is_used_with_a_note(write_config, tmp_path):
    """When `tasks.<task>` differs from the table's default model, the default row has the config model and a
    `why` naming the table's recommendation."""
    write_config({**LOCAL, "tasks": {"image": "diffusers:qwen-image"}})
    user_table(tmp_path, "| image | diffusers:flux2-klein-4b | default | fast |\n")
    assert routes.table(["image"]) == [routes.Route(
        "image", "diffusers:qwen-image", routes.DEFAULT,
        "set in config.yaml; the table recommends diffusers:flux2-klein-4b: fast")]


def test_task_without_table_default_or_without_config_model(write_config, tmp_path):
    """A task without a default row in the table gets the config model with `why` `set in config.yaml`; a task
    without `tasks.<task>` has no default row but keeps its escalation rows."""
    write_config({**LOCAL, "tasks": {"chat": "ollama:c"}})
    user_table(tmp_path, "| image | diffusers:flux2-klein-4b | default | fast |\n"
                         "| image | ollama:x | only when tested | mine |\n")
    assert routes.table(["chat"]) == [routes.Route("chat", "ollama:c", routes.DEFAULT, routes.DEFAULT_WHY)]
    assert models(routes.table(["image"])) == ["ollama:x"]


def test_missing_file_gives_config_defaults_and_a_note(write_config, tmp_path, capsys):
    """Without the user's `routes.md`, `table` has only the default rows of `tasks.<task>`, and the `routes`
    command prints them and, on stderr, that the table is missing and that setup:settings creates it."""
    write_config(LOCAL)
    assert not (tmp_path / routes.FILE_NAME).exists()
    assert routes.table(["image", "speech", "video"]) == [
        routes.Route("image", "diffusers:flux2-klein-4b", routes.DEFAULT, routes.DEFAULT_WHY),
        routes.Route("video", "diffusers:ltx-2.5", routes.DEFAULT, routes.DEFAULT_WHY)]
    parser = argparse.ArgumentParser()
    routes.command(parser.add_subparsers(dest="command"), ("image",))
    args = parser.parse_args(["routes"])
    assert args.func(args) == 0
    out, err = capsys.readouterr()
    assert out == HEADER + f"| image | diffusers:flux2-klein-4b | default | {routes.DEFAULT_WHY} |\n"
    assert str(tmp_path / routes.FILE_NAME) in err and "setup:settings" in err


@pytest.mark.parametrize("table, line, message", [
    ("| task | when | model | why |\n", 1, "header"),
    (HEADER + "| image | diffusers:a | only when x |\n", 3, "4 cells"),
    (HEADER + "| image | diffusers:a |  | y |\n", 3, "must not be empty"),
    (HEADER + "| image | diffusers:a | any other image | y |\n", 3, "must be 'default' or begin with 'only when'"),
    (HEADER + "| image | diffusers:a | default | y |\n| image | diffusers:b | default | z |\n", 4,
     "a second 'default' row"),
    (HEADER + "| image | qwen | only when x | y |\n", 3, "<provider>:<model>"),
    (HEADER + "| speech | kokoro | default | y |\n", 3, "<provider>:<model>"),
])
def test_malformed_table_names_file_and_line(write_config, tmp_path, table, line, message):
    """A wrong header (including the old column order), a row of another width, an empty task/model/when cell, a
    `when` that is neither `default` nor an `only when` condition, a second default row of a task, or a model
    without a provider (also a bare `kokoro` of an earlier voiceover) is a `ConfigError` naming the user's file and
    the line."""
    write_config(LOCAL)
    (tmp_path / routes.FILE_NAME).write_text(table, encoding="utf-8")
    with pytest.raises(ConfigError, match=re.escape(message)) as e:
        routes.table(["image"])
    assert f"{tmp_path / routes.FILE_NAME}:{line}:" in str(e.value)


def test_user_file_beside_skills_config(tmp_path):
    """The table is `routes.md` in the directory of the config file that SKILLS_CONFIG names."""
    cfg = write_settings(tmp_path / "elsewhere" / "config.yaml", **LOCAL)
    user_table(cfg.parent, "| image | diffusers:flux2-klein-4b | default | drafts |\n"
                           "| image | ollama:v | only when tested | mine |\n")
    env = child_env(SKILLS_CONFIG=str(cfg))
    assert py_value("from ai_models import routes", "str(routes.user_path())", env) == str(cfg.parent / "routes.md")
    assert py_value("from ai_models import routes", "[[r.model, r.why] for r in routes.table(['image'])]", env) == [
        ["diffusers:flux2-klein-4b", "drafts"], ["ollama:v", "mine"]]


def test_command_prints_the_table_or_the_error(write_config, tmp_path, capsys):
    """The `routes` command prints the Markdown table of the skill's tasks (or of `--task`) and returns 0; a
    malformed user file prints the error and returns 1."""
    write_config(LOCAL)
    shutil.copy(TEMPLATE, tmp_path / routes.FILE_NAME)
    parser = argparse.ArgumentParser()
    routes.command(parser.add_subparsers(dest="command"), ("image", "video"))
    args = parser.parse_args(["routes", "--task", "video"])
    assert args.func(args) == 0
    out, err = capsys.readouterr()
    assert out == HEADER + f"| video | diffusers:ltx-2.5 | default | {template_default('video').why} |\n"
    assert err == ""
    (tmp_path / routes.FILE_NAME).write_text("| a | b |\n", encoding="utf-8")
    args = parser.parse_args(["routes"])
    assert args.func(args) == 1
    assert "header" in capsys.readouterr().err
