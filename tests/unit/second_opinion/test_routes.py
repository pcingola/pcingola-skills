"""The `routes` command of second-opinion (SKILL.md "Model routes")."""

from second_opinion_tool import cli
from tests.routes_cli import main_tasks


def test_routes_prints_the_rows_of_the_skill_tasks(tmp_path):
    """`routes` prints one row of each of the skill's tasks, and `--task` keeps one of them."""
    assert sorted(main_tasks(cli.main, tmp_path)) == sorted(['chat', 'vision'])
    assert main_tasks(cli.main, tmp_path, "--task", "chat") == ["chat"]
