"""`classify run` and `eval`: the checks before any request, through `runner.score` and the CLI in process, and the
conversion of System-1 answers. No test calls a model."""
import json
from pathlib import Path

import pytest
from pydantic_ai.models.decision import DecisionResponse, ScoreAnswer, ScoreQuestion

from classify_tool import backends, cli, questions, runner
from classify_tool.items import items_from_texts
from classify_tool.questions import QuestionError
from tests.inproc import CliResult, run_main
from tests.settings_env import use_settings

TEAM = ["--type", "choice", "--instructions", "Which team?", "--option", "billing=invoices", "--option", "technical"]
SCORE = questions.from_flags("score", "x", levels=["a", "b"])


def classify(*argv: str, settings: Path | None = None) -> CliResult:
    """`classify <argv>` in process (`cli.main`), with the settings file `settings` when given."""
    return run_main(cli.main, *argv, settings=settings)


def lines(text):
    return [json.loads(line) for line in text.splitlines()]


def test_default_backend_without_system1_model(chat_config):
    """Without tasks.system1 in config.yaml the default backend of `runner.score` is chat, whose check refuses a
    score question before any request. Guards default_backend.
    """
    with use_settings(chat_config), pytest.raises(QuestionError,
                                                  match="the chat backend takes choice and noul questions only"):
        runner.score(items_from_texts(["t"]), SCORE)


def test_invalid_question_exits():
    """`classify run` with a choice of one option exits 1 before the backend is made. Guards the
    validation of questions before any request.
    """
    p = classify("run", "--type", "choice", "--instructions", "x", "--option", "a", "--item", "t")
    assert p.returncode == 1 and "at least 2 options" in p.stderr


def test_chat_backend_refuses_score(chat_config, tmp_path):
    """`runner.score` with the chat backend refuses a score question and creates no output file. Guards
    ChatBackend.check and its order before the output is opened.
    """
    out_file = tmp_path / "out.jsonl"
    with use_settings(chat_config), pytest.raises(QuestionError, match="choice and noul questions only"):
        runner.score(items_from_texts(["t"]), SCORE, backend_name="chat", out_path=out_file)
    assert not out_file.exists()


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


def test_eval_refuses_unknown_labels(tmp_path):
    """`classify eval` refuses labels that are not classes of the question before any request.
    Guards the label check of eval.
    """
    labeled = tmp_path / "l.jsonl"
    labeled.write_text('{"id": 1, "text": "x", "label": "sales"}\n')
    p = classify("eval", *TEAM, "--labeled", str(labeled))
    assert p.returncode == 1 and "labels not among" in p.stderr


def test_eval_needs_one_question(tmp_path):
    """`classify eval` refuses a questions file with more than one question. Guards the one-question
    rule of eval.
    """
    q = tmp_path / "q.json"
    q.write_text(json.dumps({"a": {"type": "noul", "instructions": "A?"}, "b": {"type": "noul", "instructions": "B?"}}))
    labeled = tmp_path / "l.jsonl"
    labeled.write_text('{"id": 1, "text": "x", "label": true}\n')
    p = classify("eval", "--questions", str(q), "--labeled", str(labeled))
    assert p.returncode == 1 and "one question" in p.stderr
