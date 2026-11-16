"""The `routes` command of voiceover (SKILL.md "Model routes")."""

from tests.routes_cli import routed_rows, routed_tasks


def test_routes_prints_the_rows_of_the_skill_tasks(tmp_path):
    """`routes` prints the rows of the speech task: the default row (`tasks.speech`), then the escalation row;
    `--task` keeps them."""
    rows = routed_rows("voiceover_tool.cli", tmp_path)
    assert [r[:3] for r in rows] == [["speech", "o:tts", "default"], ["speech", "o:speech-model", "only when tested"]]
    assert routed_tasks("voiceover_tool.cli", tmp_path, "--task", "speech") == ["speech", "speech"]
