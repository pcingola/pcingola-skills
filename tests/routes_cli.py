"""Run a skill CLI's `routes` command in a child process against a config with one Ollama provider and a user
`routes.md` holding one row of every task, so the output shows which tasks the skill routes."""
from __future__ import annotations

from pathlib import Path

from tests.settings_env import write_config
from tests.subproc import child_env, run_python

TASKS = ("chat", "vision", "system1", "image", "image_edit", "image_best", "image_multi_ref", "speech", "music",
         "audio", "video", "presenter", "film_critic")


def routed_tasks(module: str, tmp_path: Path, *argv: str) -> list[str]:
    """The tasks of the rows that `<module>.main` prints for `routes *argv`, in order."""
    cfg = write_config(tmp_path / "config.yaml", providers={"o": {"kind": "ollama"}})
    rows = "".join(f"| {t} | any request | o:{t}-model | test |\n" for t in TASKS)
    (tmp_path / "routes.md").write_text("| task | when | model | why |\n|---|---|---|---|\n" + rows, encoding="utf-8")
    code = f"import sys\nsys.argv = ['cli', 'routes', *{list(argv)!r}]\nfrom {module} import main\nmain()"
    done = run_python(code, child_env(SKILLS_CONFIG=str(cfg)))
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert lines[0] == "| task | when | model | why |", done.stdout
    return [line.split("|")[1].strip() for line in lines[2:]]
