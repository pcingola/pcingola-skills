"""`second-opinion review` through the CLI with one short review by the local Ollama, on the chat model of
tests/config.yaml."""

import json

from second_opinion_tool import review
from tests.prereq import require_ollama
from tests.settings_env import TEST_CONFIG, task_model
from tests.subproc import child_env, run_module


def test_review_with_ollama(tmp_path):
    """`second-opinion review` sends a text file to tasks.chat and writes findings JSON whose
    findings pass check_answer. Guards the agent request, its native output and the --out record.
    """
    require_ollama("chat")
    md = tmp_path / "sum.md"
    md.write_text("2 + 2 = 5\n")
    out = tmp_path / "findings.json"
    p = run_module("second_opinion_tool", ["review", "--brief", "Check the arithmetic.", "--file", str(md),
                                           "--out", str(out)], child_env(SKILLS_CONFIG=str(TEST_CONFIG)))
    assert p.returncode == 0, p.stderr
    r = json.loads(out.read_text())
    assert r["model"] == task_model("chat") and r["files"][0]["path"] == str(md)
    assert review.check_answer(r) == {"summary": r["summary"], "findings": r["findings"]}
    assert p.stdout.startswith(f"# Second opinion ({task_model('chat')})")
