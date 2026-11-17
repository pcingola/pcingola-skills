"""`classify run` and `eval` through the CLI: the checks before any request and the conversion of
System-1 answers. No test calls a model."""
import json

import pytest
from pydantic_ai.models.decision import DecisionResponse, ScoreAnswer, ScoreQuestion

from classify_tool import backends, cli

from .conftest import run

TEAM = ["--type", "choice", "--instructions", "Which team?", "--option", "billing=invoices", "--option", "technical"]


def main(argv, capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(argv)
    out = capsys.readouterr()
    return e.value.code, out.out, out.err


def lines(text):
    return [json.loads(line) for line in text.splitlines()]


def test_default_backend_without_system1_model(cli_env, tmp_path):
    """Without tasks.system1 in config.yaml the default backend is chat, whose check refuses a score
    question before any request. Guards default_backend.
    """
    cfg = tmp_path / "chat_only.yaml"
    cfg.write_text("providers:\n  ollama: {kind: ollama}\ntasks:\n  chat: ollama:x\n")
    p = run(["run", "--type", "score", "--instructions", "x", "--level", "a", "--level", "b", "--item", "t"],
            {**cli_env, "SKILLS_CONFIG": str(cfg)})
    assert p.returncode == 1 and "the chat backend takes choice and noul questions only" in p.stderr


def test_invalid_question_exits(capsys):
    """`classify run` with a choice of one option exits 1 before the backend is made. Guards the
    validation of questions before any request.
    """
    code, _, err = main(["run", "--type", "choice", "--instructions", "x", "--option", "a", "--item", "t"], capsys)
    assert code == 1 and "at least 2 options" in err


def test_chat_backend_refuses_score(cli_env, tmp_path):
    """`classify run --backend chat` refuses a score question and creates no --out. Guards
    ChatBackend.check and its order before the output is opened.
    """
    out_file = tmp_path / "out.jsonl"
    argv = ["run", "--backend", "chat", "--type", "score", "--instructions", "x", "--level", "a", "--level", "b",
            "--item", "t", "--out", str(out_file)]
    p = run(argv, cli_env)
    assert p.returncode == 1 and "choice and noul questions only" in p.stderr and not out_file.exists()


def test_system1_result_score_top_is_level_text():
    """backends.system1_result names a score answer's top by the question's level description, not
    the response's legend, and maps level probabilities to descriptions. Guards the score class
    mapping.
    """
    qs = {"s": ScoreQuestion(instructions="How bad?", criteria=["low", "high"])}
    # A legend that differs from the question: the class is the question's level description.
    a = ScoreAnswer(score=0.9, confidence=0.8, probabilities={0: 0.1, 1: 0.9}, legend={0: "L", 1: "H"})
    r = backends.system1_result(qs, DecisionResponse(answers={"s": a}, model_name="m", provider_response_id="r1"))
    assert (r.top["s"], r.p_top["s"], r.probabilities["s"]) == ("high", 0.9, {"low": 0.1, "high": 0.9})
    assert (r.model, r.request_id) == ("m", "r1")
    assert r.answers["s"] == {"type": "score", "score": 0.9, "level": 1, "probabilities": {"0": 0.1, "1": 0.9},
                              "confidence": 0.8}


def test_eval_refuses_unknown_labels(capsys, tmp_path):
    """`classify eval` refuses labels that are not classes of the question before any request.
    Guards the label check of eval.
    """
    labeled = tmp_path / "l.jsonl"
    labeled.write_text('{"id": 1, "text": "x", "label": "sales"}\n')
    code, _, err = main(["eval", *TEAM, "--labeled", str(labeled)], capsys)
    assert code == 1 and "labels not among" in err


def test_eval_needs_one_question(capsys, tmp_path):
    """`classify eval` refuses a questions file with more than one question. Guards the one-question
    rule of eval.
    """
    q = tmp_path / "q.json"
    q.write_text(json.dumps({"a": {"type": "noul", "instructions": "A?"}, "b": {"type": "noul", "instructions": "B?"}}))
    labeled = tmp_path / "l.jsonl"
    labeled.write_text('{"id": 1, "text": "x", "label": true}\n')
    code, _, err = main(["eval", "--questions", str(q), "--labeled", str(labeled)], capsys)
    assert code == 1 and "one question" in err
