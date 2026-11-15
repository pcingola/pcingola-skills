"""Run a skill CLI's `routes` command in a child process against a config with one Ollama provider and a user
`routes.md` holding one escalation row of every task and the `kokoro` default row of `speech`, so the output shows
which tasks the skill routes."""
from __future__ import annotations

from pathlib import Path

from tests.settings_env import write_config
from tests.subproc import child_env, run_python

HEADER = "| task | model | when | why |"
TASKS = ("chat", "vision", "system1", "image", "image_edit", "image_best", "image_multi_ref", "speech", "music",
         "audio", "video", "presenter", "film_critic")


def routed_rows(module: str, tmp_path: Path, *argv: str) -> list[list[str]]:
    """The rows, as cells `[task, model, when, why]`, that `<module>.main` prints for `routes *argv`, in order."""
    cfg = write_config(tmp_path / "config.yaml", providers={"o": {"kind": "ollama"}})
    rows = "| speech | kokoro | default | test |\n"
    rows += "".join(f"| {t} | o:{t}-model | only when tested | test |\n" for t in TASKS)
    (tmp_path / "routes.md").write_text(HEADER + "\n|---|---|---|---|\n" + rows, encoding="utf-8")
    code = f"import sys\nsys.argv = ['cli', 'routes', *{list(argv)!r}]\nfrom {module} import main\nmain()"
    done = run_python(code, child_env(SKILLS_CONFIG=str(cfg)))
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert lines[0] == HEADER, done.stdout
    return [[c.strip() for c in line.strip().strip("|").split("|")] for line in lines[2:]]


def routed_tasks(module: str, tmp_path: Path, *argv: str) -> list[str]:
    """The tasks of the rows that `<module>.main` prints for `routes *argv`, in order."""
    return [row[0] for row in routed_rows(module, tmp_path, *argv)]
