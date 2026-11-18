"""The `routes` command of music (SKILL.md "Model routes"), through `music_tool.cli.main` in process."""

from music_tool.cli import main
from tests.routes_cli import main_tasks


def test_routes_prints_the_rows_of_the_skill_tasks(tmp_path):
    """`routes` prints one row of each of the skill's tasks, and `--task` keeps one of them."""
    assert sorted(main_tasks(main, tmp_path)) == sorted(['music', 'audio'])
    assert main_tasks(main, tmp_path, "--task", "music") == ["music"]
