"""The `routes` command of music (SKILL.md "Model routes")."""

from tests.routes_cli import routed_tasks


def test_routes_prints_the_rows_of_the_skill_tasks(tmp_path):
    """`routes` prints one row of each of the skill's tasks, and `--task` keeps one of them."""
    assert sorted(routed_tasks("music_tool.cli", tmp_path)) == sorted(['music', 'audio'])
    assert routed_tasks("music_tool.cli", tmp_path, "--task", "music") == ["music"]
