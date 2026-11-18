"""The `routes` command of voiceover (SKILL.md "Model routes"), through `voiceover_tool.cli.main` in process."""

from tests.routes_cli import main_rows, main_tasks
from voiceover_tool.cli import main


def test_routes_prints_the_rows_of_the_skill_tasks(tmp_path):
    """`routes` prints the rows of the speech task: the default row (`tasks.speech`), then the escalation row;
    `--task` keeps them."""
    rows = main_rows(main, tmp_path)
    assert [r[:3] for r in rows] == [["speech", "o:tts", "default"], ["speech", "o:speech-model", "only when tested"]]
    assert main_tasks(main, tmp_path, "--task", "speech") == ["speech", "speech"]
