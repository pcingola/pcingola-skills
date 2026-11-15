"""The `routes` command of image-gen (SKILL.md "Model routes")."""

from tests.routes_cli import routed_tasks


def test_routes_prints_the_rows_of_the_skill_tasks(tmp_path):
    """`routes` prints one row of each of the skill's tasks, and `--task` keeps one of them."""
    assert sorted(routed_tasks("image_gen_tool.cli", tmp_path)) == sorted(['image', 'image_edit', 'image_best', 'image_multi_ref'])
    assert routed_tasks("image_gen_tool.cli", tmp_path, "--task", "image") == ["image"]
