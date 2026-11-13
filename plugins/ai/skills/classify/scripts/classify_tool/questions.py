"""Questions from the command line or a `--questions` JSON file, and the class
names each question type answers with. Questions are Pydantic-AI's decision
questions (`pydantic_ai.models.decision`) keyed by id, in the order given."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

from pydantic import Field, TypeAdapter, ValidationError
from pydantic_ai.models.decision import ChoiceQuestion, DecisionQuestion, NoulCriteria, NoulQuestion, ScoreQuestion

CHOICE, NOUL, SCORE = "choice", "noul", "score"
# Keys of a question in the request format; others are refused, since a model ignores them.
QUESTION_KEYS = ("type", "instructions", "criteria")
MIN_CLASSES, MAX_LEVELS = 2, 10
DEFAULT_ID = "q"
NOUL_CLASSES = ["true", "false"]

Questions = dict[str, DecisionQuestion]
_QUESTIONS = TypeAdapter(dict[str, Annotated[DecisionQuestion, Field(discriminator="type")]])


class QuestionError(ValueError):
    """An invalid question or question flag."""


def parse_option(text: str) -> tuple[str, str | None]:
    """`NAME=DESCRIPTION` or `NAME`."""
    name, sep, desc = text.partition("=")
    return name.strip(), (desc.strip() if sep else None)


def from_flags(qtype: str | None, instructions: str | None, options=(), levels=(), true=None, false=None,
               qid: str = DEFAULT_ID) -> Questions:
    """One question from the `--type`, `--instructions`, `--option`, `--level`,
    `--true`, `--false` and `--id` flags; flags of another type are refused."""
    if qtype is None:
        raise QuestionError("give --type and --instructions, or --questions FILE")
    if options and qtype != CHOICE:
        raise QuestionError("--option is for --type choice")
    if levels and qtype != SCORE:
        raise QuestionError("--level is for --type score")
    if (true is not None or false is not None) and qtype != NOUL:
        raise QuestionError("--true and --false are for --type noul")
    instructions = instructions or ""
    if qtype == CHOICE:
        opts = dict(parse_option(o) for o in options)
        if len(opts) != len(options):
            raise QuestionError("duplicate --option name")
        return {qid: ChoiceQuestion(instructions=instructions, criteria=opts)}
    if qtype == NOUL:
        criteria = None if true is None and false is None else NoulCriteria(true=true, false=false)
        return {qid: NoulQuestion(instructions=instructions, criteria=criteria)}
    return {qid: ScoreQuestion(instructions=instructions, criteria=list(levels))}


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    """A JSON object whose keys must be unique (json.loads keeps the last of
    duplicate keys, which would drop a question or option silently)."""
    keys = [k for k, _ in pairs]
    dups = sorted({k for k in keys if keys.count(k) > 1})
    if dups:
        raise QuestionError(f"duplicate keys {dups}")
    return dict(pairs)


def from_file(path: str | Path) -> Questions:
    """Questions from a JSON object in the request's `questions` format."""
    try:
        data = json.loads(Path(path).expanduser().read_text(encoding="utf-8"), object_pairs_hook=_unique_keys)
    except OSError as e:
        raise QuestionError(f"--questions: {e}") from None
    except QuestionError as e:
        raise QuestionError(f"--questions {path}: {e}") from None
    except ValueError as e:
        raise QuestionError(f"--questions {path}: not JSON: {e}") from None
    if isinstance(data, dict):
        for qid, q in data.items():
            unknown = sorted(set(q) - set(QUESTION_KEYS)) if isinstance(q, dict) else []
            if unknown:
                raise QuestionError(f"--questions {path}: question {qid!r}: unknown keys {', '.join(unknown)} "
                                    f"(allowed: {', '.join(QUESTION_KEYS)})")
    try:
        return _QUESTIONS.validate_python(data)
    except ValidationError as e:
        raise QuestionError(f"--questions {path}: {e}") from None


def check(qs: Questions) -> None:
    """Raise `QuestionError` listing every problem: no questions, empty instructions, fewer than 2
    options or levels, more than 10 levels, an empty option name or description, a yes/no with one
    description, duplicate option names or level descriptions (compared after stripping whitespace)."""
    errors = [] if qs else ["no questions"]
    for qid, q in qs.items():
        name = f"question {qid!r}"
        if not q.instructions.strip():
            errors.append(f"{name}: empty instructions")
        if len(classes(q)) < MIN_CLASSES:
            errors.append(f"{name}: at least {MIN_CLASSES} {'options' if q.type == CHOICE else 'levels'}")
        if isinstance(q, ScoreQuestion) and len(q.criteria) > MAX_LEVELS:
            errors.append(f"{name}: at most {MAX_LEVELS} levels, got {len(q.criteria)}")
        texts = []
        if isinstance(q, ChoiceQuestion):
            texts = [t for opt, desc in q.criteria.items() for t in (opt, desc) if t is not None]
        elif isinstance(q, ScoreQuestion):
            texts = list(q.criteria)
        elif q.criteria is not None:
            if q.criteria.true is None or q.criteria.false is None:
                errors.append(f"{name}: give both true and false descriptions, or neither")
            texts = [t for t in (q.criteria.true, q.criteria.false) if t is not None]
        if any(not t.strip() for t in texts):
            errors.append(f"{name}: empty option name, description or level")
        stripped = [c.strip() for c in classes(q)]
        dups = sorted({c for c in stripped if stripped.count(c) > 1})
        if dups:
            errors.append(f"{name}: duplicate {'option names' if q.type == CHOICE else 'levels'} {dups}")
    if errors:
        raise QuestionError("; ".join(errors))


def load(args) -> Questions:
    """Validated questions from parsed arguments."""
    flags = args.type or args.instructions or args.option or args.level or args.true or args.false
    if args.questions:
        if flags or args.id:
            raise QuestionError("give --questions FILE or the question flags (--id included), not both")
        qs = from_file(args.questions)
    else:
        qs = from_flags(args.type, args.instructions, args.option or [], args.level or [], args.true, args.false,
                        args.id or DEFAULT_ID)
    check(qs)
    return qs


def classes(q: DecisionQuestion) -> list[str]:
    """The answers a question can have: option names, "true"/"false", or level descriptions."""
    if isinstance(q, ChoiceQuestion):
        return list(q.criteria)
    if isinstance(q, NoulQuestion):
        return list(NOUL_CLASSES)
    if isinstance(q, ScoreQuestion):
        return list(q.criteria)
    raise QuestionError(f"unknown question class {type(q).__name__}")
