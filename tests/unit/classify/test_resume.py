"""`--out` read back and resumed, and `eval --scores`, without model calls: the output files are
written by the tests."""
import json

import pytest

from classify_tool import output
from classify_tool.items import ItemError

from .test_run import TEAM, classify, lines

CHOICE = {"type": "choice", "choice": "billing", "probabilities": {"billing": 0.9, "technical": 0.1},
          "confidence": 0.9}


def write_lines(path, recs):
    path.write_text("".join(json.dumps(r) + "\n" for r in recs))
    return path


def test_unreadable_out_line_is_refused(tmp_path):
    """A complete line of --out that is not JSON is an error naming the file and line, not a torn
    write. Guards output.read_records.
    """
    out = tmp_path / "scored.jsonl"
    out.write_text('{"id": 1}\nnot json\n')
    with pytest.raises(ItemError, match=r"scored.jsonl:2: not JSON"):
        output.read_records(out)


def test_torn_last_line_is_dropped(tmp_path):
    """A last line without a newline, left by a process killed while writing it, is ignored and, with
    drop_torn, cut from the file; the last line of an id wins. Guards output.read_records.
    """
    out = tmp_path / "scored.jsonl"
    out.write_text('{"id": 1, "error": "x"}\n{"id": 1}\n{"id": 2, "an')
    assert output.read_records(out, drop_torn=True) == {1: {"id": 1}}
    assert out.read_text() == '{"id": 1, "error": "x"}\n{"id": 1}\n'


def test_finish_rewrites_in_input_order(tmp_path):
    """Output.finish replaces the file with one line per id in the given order, each passed through
    the update. Guards the rewrite at the end of a run.
    """
    out = output.Output(tmp_path / "scored.jsonl")
    out.open()
    for rec in ({"id": 2}, {"id": 1, "error": "x"}, {"id": 1}):
        out.write(rec)
    out.finish([1, 2, 3], lambda r: {**r, "seen": True})
    assert lines(out.path.read_text()) == [{"id": 1, "seen": True}, {"id": 2, "seen": True}]


@pytest.mark.parametrize("argv, message", [
    (["run", "--backend", "system1", *TEAM, "--item", "billing"], "holds ids that are not among the items"),
    (["run", "--backend", "chat", *TEAM, "--item", "billing", "--item", "x"], "scored with backend 'system1'"),
    (["run", "--backend", "system1", "--type", "noul", "--instructions", "Yes?", "--id", "u", "--item", "billing",
      "--item", "x"], "answers questions ['q'], this run asks ['u']"),
])
def test_resume_refuses_other_runs(tmp_path, argv, message):
    """A rerun refuses an --out that holds other ids, another backend or other questions before
    the backend is made. Guards runner.resume.
    """
    out = write_lines(tmp_path / "scored.jsonl", [{"id": n, "backend": "system1", "answers": {"q": CHOICE}}
                                                  for n in (1, 2)])
    p = classify(*argv, "--out", str(out))
    assert p.returncode == 1 and message in p.stderr


def labeled_csv(tmp_path):
    p = tmp_path / "l.csv"
    p.write_text("id,text,label\n1,billing issue,billing\n2,technical bug,technical\n")
    return p


def test_eval_scores_metrics(tmp_path):
    """`classify eval --scores` computes the metrics from existing lines: a labelled item without a
    line is an error, lines of other ids are ignored, and --out is refused. Guards the --scores
    branch of cli._cmd_eval and backends.answer_parts.
    """
    labeled = labeled_csv(tmp_path)
    scores = write_lines(tmp_path / "s.jsonl", [{"id": "1", "backend": "system1", "model": "m", "answers": {"q": CHOICE}},
                                                {"id": "9", "backend": "system1", "model": "m", "answers": {}}])
    p = classify("eval", *TEAM, "--labeled", str(labeled), "--scores", str(scores), "--json")
    m = json.loads(p.stdout)
    assert p.returncode == 1 and (m["n"], m["errors"], m["accuracy"]) == (2, 1, 1.0)
    assert m["brier"] == pytest.approx(0.02)
    assert (m["backend"], m["model"]) == ("system1", "m")
    assert "1 lines of" in p.stderr and f"item 2: no line in {scores}" in p.stderr
    p = classify("eval", *TEAM, "--labeled", str(labeled), "--scores", str(scores), "--out", str(tmp_path / "p.jsonl"))
    assert p.returncode == 1 and "writes no --out" in p.stderr


@pytest.mark.parametrize("flags, answer, top", [
    (["--type", "noul", "--instructions", "Agree?"], {"type": "noul", "p_yes": 0.3}, "false"),
    (["--type", "score", "--instructions", "Sev?", "--level", "billing", "--level", "technical"],
     {"type": "score", "score": 0.8, "level": 1, "probabilities": {"0": 0.2, "1": 0.8}}, "technical"),
    (TEAM, {"type": "choice", "answer": "technical"}, "technical"),
])
def test_eval_scores_answer_types(tmp_path, flags, answer, top):
    """`classify eval --scores` reads noul, score and chat answers of output lines. Guards
    backends.answer_parts per answer form.
    """
    labeled = tmp_path / "l.jsonl"
    labeled.write_text(json.dumps({"id": 1, "text": "x", "label": top}) + "\n")
    scores = write_lines(tmp_path / "s.jsonl", [{"id": 1, "backend": "system1", "answers": {"q": answer}}])
    p = classify("eval", *flags, "--labeled", str(labeled), "--scores", str(scores), "--json")
    assert p.returncode == 0 and json.loads(p.stdout)["accuracy"] == 1.0


def test_eval_scores_refuses_answers_of_another_question(tmp_path):
    """`classify eval --scores` stops on a line whose answer does not fit the question's classes.
    Guards the class check of backends.answer_parts.
    """
    labeled = labeled_csv(tmp_path)
    scores = write_lines(tmp_path / "s.jsonl", [{"id": "1", "backend": "system1", "answers": {"q": {
        "type": "choice", "choice": "sales", "probabilities": {"sales": 1.0}}}}])
    p = classify("eval", *TEAM, "--labeled", str(labeled), "--scores", str(scores))
    assert p.returncode == 1 and "does not fit the classes" in p.stderr
