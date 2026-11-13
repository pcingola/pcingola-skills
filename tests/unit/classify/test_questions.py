"""Questions from flags and files; class names; eval label mapping."""
import json
from types import SimpleNamespace

import pytest

from pydantic_ai.models.decision import ChoiceQuestion, NoulCriteria, NoulQuestion, ScoreQuestion

from classify_tool import questions
from classify_tool.questions import QuestionError
from classify_tool.cli import label_class


def args(**kw):
    base = dict(type=None, instructions=None, option=None, level=None, true=None, false=None, id=None, questions=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_choice_options_with_and_without_description():
    """questions.load builds a choice question from --option NAME=DESCRIPTION and NAME, splitting at
    the first '='. Guards parse_option, so a description may contain '='.
    """
    qs = questions.load(args(type="choice", instructions="Which?", option=["a=first = one", "b"]))
    assert qs == {"q": ChoiceQuestion(instructions="Which?", criteria={"a": "first = one", "b": None})}


def test_noul_and_score():
    """questions.load builds a yes/no question with and without --true/--false and a score question
    whose classes are its levels, with the --id given or the default q. Guards from_flags for the
    noul and score types.
    """
    qs = questions.load(args(type="noul", instructions="Yes?", true="y", false="n", id="yn"))
    assert qs == {"yn": NoulQuestion(instructions="Yes?", criteria=NoulCriteria(true="y", false="n"))}
    assert questions.load(args(type="noul", instructions="Yes?")) == {"q": NoulQuestion(instructions="Yes?")}
    [q] = questions.load(args(type="score", instructions="How bad?", level=["low", "high"])).values()
    assert questions.classes(q) == ["low", "high"]


@pytest.mark.parametrize("kw, match", [
    (dict(type="noul", instructions="x", option=["a"]), "--option is for --type choice"),
    (dict(type="choice", instructions="x", level=["a"]), "--level is for --type score"),
    (dict(type="score", instructions="x", true="a"), "--true and --false are for --type noul"),
    (dict(type="choice", instructions="x", option=["a", "a=again"]), "duplicate --option"),
    (dict(type="choice", instructions="x", option=["a"]), "at least 2 options"),
    (dict(instructions="x"), "give --type"),
    (dict(type="noul"), "empty instructions"),
    (dict(type="score", instructions="x", level=[str(i) for i in range(11)]), "at most 10 levels"),
    (dict(type="score", instructions="x", level=["low", " low"]), "duplicate levels"),
    (dict(type="noul", instructions="x", true="y"), "both true and false"),
    (dict(type="choice", instructions="x", option=["a= ", "b"]), "empty option name"),
])
def test_flag_errors(kw, match):
    """questions.load refuses flags of another question type, a duplicate --option, a missing --type
    and questions that fail questions.check. Guards from_flags' checks and that load
    validates before any request.
    """
    with pytest.raises(QuestionError, match=match):
        questions.load(args(**kw))


def test_questions_file(tmp_path):
    """questions.load reads a --questions file in order and refuses it together with question flags.
    Guards the file format and the exclusive choice of file or flags.
    """
    p = tmp_path / "q.json"
    p.write_text(json.dumps({"t": {"type": "choice", "instructions": "Team?", "criteria": {"a": None, "b": None}},
                             "u": {"type": "noul", "instructions": "Urgent?"}}))
    qs = questions.load(args(questions=str(p)))
    assert list(qs) == ["t", "u"]
    assert qs["u"] == NoulQuestion(instructions="Urgent?")
    with pytest.raises(QuestionError, match="not both"):
        questions.load(args(questions=str(p), type="noul"))


def test_label_class_score_index_or_text():
    """cli.label_class maps a score label given as a level description or index and refuses an index
    out of range and a yes/no label other than true/false. Guards the label mapping of eval.
    """
    q = ScoreQuestion(instructions="How bad?", criteria=["low", "mid", "high"])
    classes = questions.classes(q)
    assert label_class(q, "2", classes) == "high"
    assert label_class(q, "mid", classes) == "mid"
    with pytest.raises(QuestionError):
        label_class(q, "3", classes)
    with pytest.raises(QuestionError):
        label_class(NoulQuestion(instructions="x"), "yes", ["true", "false"])


def test_unknown_key_in_questions_file(tmp_path):
    """A --questions file with a key other than type, instructions and criteria is refused, since the model
    would ignore it."""
    p = tmp_path / "q.json"
    p.write_text(json.dumps({"t": {"type": "noul", "instructions": "Urgent?", "labels": ["y", "n"]}}))
    with pytest.raises(QuestionError, match="unknown keys labels"):
        questions.load(args(questions=str(p)))


def test_id_with_questions_file_refused(tmp_path):
    """questions.load refuses --id together with --questions. Guards that question ids come from the
    file only.
    """
    p = tmp_path / "q.json"
    p.write_text(json.dumps({"u": {"type": "noul", "instructions": "Urgent?"}}))
    with pytest.raises(QuestionError, match="--id included"):
        questions.load(args(questions=str(p), id="x"))


def test_duplicate_keys_in_questions_file(tmp_path):
    """questions.from_file refuses duplicate keys in the JSON object. Guards _unique_keys, since
    json.loads would keep the last and drop an option silently.
    """
    p = tmp_path / "q.json"
    p.write_text('{"t": {"type": "choice", "instructions": "T?", "criteria": {"a": null, "a": "again", "b": null}}}')
    with pytest.raises(QuestionError, match=r"duplicate keys \['a'\]"):
        questions.load(args(questions=str(p)))


def test_noul_labels_any_case():
    """cli.label_class accepts yes/no labels in any case. Guards the case-insensitive yes/no labels
    of eval files.
    """
    q = NoulQuestion(instructions="x")
    assert [label_class(q, v, ["true", "false"]) for v in ("TRUE", "False", "true")] == ["true", "false", "true"]


def test_score_label_text_match_wins_over_index():
    """cli.label_class takes a level whose description equals the label before reading the label as
    an index. Guards the order of the two mappings for numeric level names.
    """
    q = ScoreQuestion(instructions="Stars?", criteria=["1", "2", "3"])
    classes = questions.classes(q)
    assert label_class(q, "2", classes) == "2"   # the level described "2" (index 1), not index 2
    assert label_class(q, "0", classes) == "1"   # no level described "0": index 0
