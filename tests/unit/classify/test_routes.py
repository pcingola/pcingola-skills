"""The `routes` command of classify (SKILL.md "Model routes")."""

from classify_tool import cli

from tests.routes_cli import main_tasks


def test_routes_prints_the_rows_of_the_skill_tasks(tmp_path):
    """`routes` prints one row of each of the skill's tasks, and `--task` keeps one of them."""
    assert sorted(main_tasks(cli.main, tmp_path)) == sorted(['system1', 'chat'])
    assert main_tasks(cli.main, tmp_path, "--task", "system1") == ["system1"]
