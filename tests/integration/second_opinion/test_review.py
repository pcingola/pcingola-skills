"""`second-opinion review` through the CLI entry `main(argv)` in process, with one short review by the local Ollama,
on the chat model of tests/config.yaml."""

import json

from second_opinion_tool import cli, review
from tests.inproc import run_main
from tests.prereq import require_ollama
from tests.settings_env import TEST_CONFIG, task_model


def test_review_with_ollama(tmp_path):
    """`second-opinion review` sends a text file to tasks.chat, writes findings JSON whose findings pass
    check_answer and prints the Markdown report. Guards cli.run_review (the agent request, its native output and
    the --out record) and the printed report.
    """
    require_ollama("chat")
    md = tmp_path / "sum.md"
    md.write_text("2 + 2 = 5\n")
    out = tmp_path / "findings.json"
    p = run_main(cli.main, "review", "--brief", "Check the arithmetic.", "--file", str(md), "--out", str(out),
                 settings=TEST_CONFIG)
    assert p.returncode == 0, p.stderr
    r = json.loads(out.read_text())
    assert r["model"] == task_model("chat") and r["files"][0]["path"] == str(md)
    assert review.check_answer(r) == {"summary": r["summary"], "findings": r["findings"]}
    assert p.stdout.startswith(f"# Second opinion ({task_model('chat')})")
