"""`classify run` and `eval` through the CLI: the checks before any request, the conversion of
System-1 answers, and one short call per backend to the local Ollama."""
import json

import pytest
from pydantic_ai.models.decision import DecisionResponse, ScoreAnswer, ScoreQuestion

from classify_tool import backends, cli

from .conftest import CHAT_MODEL, SYSTEM1_MODEL, require, run

TEAM = ["--type", "choice", "--instructions", "Which team?", "--option", "billing=invoices", "--option", "technical"]


def main(argv, capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(argv)
    out = capsys.readouterr()
    return e.value.code, out.out, out.err


def lines(text):
    return [json.loads(line) for line in text.splitlines()]


def test_system1_run(models_env):
    """`classify run` without --backend uses the system1 backend with tasks.system1 of config.yaml
    and writes a record with id, backend, model, UTC timestamp, top, p_top and answers whose
    probabilities cover the options. Guards default_backend, System1Backend and runner.record.
    """
    require(SYSTEM1_MODEL)
    p = run(["run", *TEAM, "--item", "My invoice is wrong."], models_env)
    assert p.returncode == 0, p.stderr
    [r] = lines(p.stdout)
    assert (r["id"], r["backend"]) == (1, "system1") and r["timestamp"].endswith("+00:00")
    assert r["top"] in ("billing", "technical") and 0.0 <= r["p_top"] <= 1.0
    assert set(r["answers"]["q"]["probabilities"]) == {"billing", "technical"}


def test_chat_run(models_env):
    """`classify run --backend chat` classifies with tasks.chat and records a label among the
    options with p_top null. Guards ChatBackend's structured output and chat_result.
    """
    require(CHAT_MODEL)
    p = run(["run", "--backend", "chat", "--type", "noul", "--instructions", "Does the customer agree?",
             "--item", "Yes, I agree."], models_env)
    assert p.returncode == 0, p.stderr
    [r] = lines(p.stdout)
    assert (r["backend"], r["p_top"]) == ("chat", None) and r["top"] in ("true", "false")
    assert r["answers"]["q"] == {"type": "noul", "answer": r["top"]}


def test_default_backend_without_system1_model(models_env, tmp_path):
    """Without tasks.system1 in config.yaml the default backend is chat, whose check refuses a score
    question before any request. Guards default_backend.
    """
    cfg = tmp_path / "chat_only.yaml"
    cfg.write_text("providers:\n  ollama: {kind: ollama}\ntasks:\n  chat: ollama:x\n")
    p = run(["run", "--type", "score", "--instructions", "x", "--level", "a", "--level", "b", "--item", "t"],
            {**models_env, "SKILLS_CONFIG": str(cfg)})
    assert p.returncode == 1 and "the chat backend takes choice and noul questions only" in p.stderr


def test_invalid_question_exits(capsys):
    """`classify run` with a choice of one option exits 1 before the backend is made. Guards the
    validation of questions before any request.
    """
    code, _, err = main(["run", "--type", "choice", "--instructions", "x", "--option", "a", "--item", "t"], capsys)
    assert code == 1 and "at least 2 options" in err


def test_chat_backend_refuses_score(models_env, tmp_path):
    """`classify run --backend chat` refuses a score question and creates no --out. Guards
    ChatBackend.check and its order before the output is opened.
    """
    out_file = tmp_path / "out.jsonl"
    argv = ["run", "--backend", "chat", "--type", "score", "--instructions", "x", "--level", "a", "--level", "b",
            "--item", "t", "--out", str(out_file)]
    p = run(argv, models_env)
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


def test_missing_model_stops_before_other_items(models_env, tmp_path):
    """A System-1 model that Ollama does not hold ends the run once with the `ollama pull` message;
    no item line is written."""
    from .conftest import OLLAMA, run

    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"providers:\n  ollama: {{kind: ollama, base_url: {OLLAMA}/v1}}\n"
                   "tasks:\n  system1: ollama:no-such-model:1b\n")
    out = tmp_path / "out.jsonl"
    p = run(["run", "--type", "noul", "--instructions", "Urgent?", *[a for i in range(5) for a in ("--item", f"t{i}")],
             "--out", str(out)], models_env)
    assert p.returncode == 1 and "ollama pull no-such-model:1b" in p.stderr, p.stderr
    assert p.stderr.count("ollama pull") == 1
    assert not out.exists() or not out.read_text().strip()
