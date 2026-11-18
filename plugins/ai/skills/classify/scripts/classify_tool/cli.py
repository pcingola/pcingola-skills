"""Argparse dispatcher for `classify <command>`.

Commands:
    run    Classify items; one JSONL record per item to --out or stdout.
           --out is appended per finished item and resumed by a rerun.
    eval   Classify labelled items with one question, or read the scores of
           an earlier run (--scores), and print accuracy, Brier score,
           calibration and accuracy/coverage per threshold.
    routes Print the model routes of the system1 and chat tasks (`ai_models.routes`).
"""

from __future__ import annotations

import argparse
import json
import sys

from ai_models import routes
from ai_models.errors import AIModelsError
from plugin_settings import exit_code
from pydantic_ai.models.decision import DecisionQuestion, NoulQuestion, ScoreQuestion

from . import backends, config, metrics, output, questions, runner
from .items import Item, ItemError, items_from_texts, read_items
from .questions import QuestionError

# The tasks of the two backends; `routes` prints their rows.
ROUTE_TASKS = ("system1", "chat")


def _add_question_flags(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("question (flags, or --questions FILE)")
    g.add_argument("--type", choices=["choice", "noul", "score"], help="question type (noul = yes/no)")
    g.add_argument("--instructions", help="the question")
    g.add_argument("--option", action="append", metavar="NAME[=DESCRIPTION]", help="choice option (repeat, at least 2)")
    g.add_argument("--level", action="append", metavar="TEXT", help="score level (repeat, 2 to 10, lowest first)")
    g.add_argument("--true", metavar="TEXT", help="noul: what a yes means (with --false)")
    g.add_argument("--false", metavar="TEXT", help="noul: what a no means (with --true)")
    g.add_argument("--id", help=f"question id (default {questions.DEFAULT_ID})")
    g.add_argument("--questions", metavar="FILE", help="JSON object in the request's `questions` format")


def _add_backend_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--backend", choices=backends.BACKENDS,
                   help="system1 (a System-1 model, probabilities) or chat (a chat model, label only; "
                        "choice and noul); default system1 when config.yaml names a System-1 model, else chat")
    p.add_argument("--model", help="model id <provider>:<model> (default: tasks.system1 or tasks.chat "
                                   "of config.yaml)")
    p.add_argument("--concurrency", type=int, default=config.DEFAULT_CONCURRENCY,
                   help=f"concurrent requests (default {config.DEFAULT_CONCURRENCY})")
    p.add_argument("--timeout", type=float, default=None,
                   help="seconds per request (default: the provider's timeout in config.yaml)")
    p.add_argument("--retry-failed", type=int, default=config.DEFAULT_RETRY_FAILED, metavar="N",
                   help="extra sequential passes retrying rate-limit (429) and connection failures "
                        f"after the concurrent pass (default {config.DEFAULT_RETRY_FAILED})")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="classify", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="classify items")
    _add_question_flags(p)
    p.add_argument("--item", action="append", metavar="TEXT", help="item text (repeat)")
    p.add_argument("--items", metavar="FILE", help=".jsonl (id, text), .csv (id, text) or .txt (one per line)")
    _add_backend_flags(p)
    p.add_argument("--out", metavar="FILE", help="JSONL output (default stdout); an existing file is resumed: "
                                                 "ids with a line without error are not scored again")

    p = sub.add_parser("eval", help="evaluate one question on labelled items")
    _add_question_flags(p)
    p.add_argument("--labeled", metavar="FILE", required=True, help=".jsonl or .csv with id, text, label")
    _add_backend_flags(p)
    p.add_argument("--out", metavar="FILE", help="per-item predictions as JSONL; an existing file is resumed")
    p.add_argument("--scores", metavar="FILE", help="compute the metrics from this run or eval output "
                                                     "instead of scoring (backend flags unused)")
    p.add_argument("--json", action="store_true", help="print the metrics as JSON")

    routes.command(sub, ROUTE_TASKS)
    return parser


def _load_items(args) -> list[Item]:
    if bool(args.item) == bool(args.items):
        config.error("give --item TEXT (repeatable) or --items FILE")
    return items_from_texts(args.item) if args.item else read_items(args.items)


def _score(args, items: list[Item], qs: questions.Questions, extra=lambda rec: rec) -> runner.Scored:
    """`runner.score` with the backend flags and `--out` of `args`."""
    return runner.score(items, qs, backend_name=args.backend, model=args.model, timeout=args.timeout,
                        concurrency=args.concurrency, retry_failed=args.retry_failed, out_path=args.out,
                        extra=extra)


def _summary(items: list[Item], failed: int, resumed: int, path: str | None) -> str:
    tail = f", {resumed} already in {path}" if resumed else ""
    return f"{len(items)} items, {failed} failed{tail}"


def _cmd_run(args) -> int:
    qs = questions.load(args)
    items = _load_items(args)
    scored = _score(args, items, qs)
    records, resumed = scored.records, scored.resumed
    if not args.out:
        for it in items:
            sys.stdout.write(json.dumps(records[it.id], ensure_ascii=False) + "\n")
    failed = sum(not output.done(records[it.id]) for it in items)
    print(_summary(items, failed, resumed, args.out), file=sys.stderr)
    return 1 if failed else 0


def label_class(q: DecisionQuestion, label: str, classes: list[str]) -> str:
    """The class a label names. A yes/no label is `true` or `false` in any case.
    A score label is a level description or, when no description equals it,
    the level index (0 = lowest)."""
    if isinstance(q, NoulQuestion) and label.lower() in classes:
        return label.lower()
    if label in classes:
        return label
    if isinstance(q, ScoreQuestion) and label.isdigit() and int(label) < len(classes):
        return classes[int(label)]
    raise QuestionError(f"label {label!r} is not one of {classes}")


def _cmd_eval(args) -> int:
    qs = questions.load(args)
    if len(qs) != 1:
        config.error(f"eval takes one question, got {len(qs)}")
    [(qid, q)] = qs.items()
    classes = questions.classes(q)
    items = read_items(args.labeled, labeled=True)
    labels = {}
    bad = []
    for it in items:
        try:
            labels[it.id] = label_class(q, it.label, classes)
        except QuestionError:
            bad.append(f"{it.id}: {it.label!r}")
    if bad:
        config.error(f"labels not among {classes}: {'; '.join(bad[:10])}")

    def prediction(rec) -> metrics.Prediction:
        label = labels[rec["id"]]
        if not output.done(rec):
            return metrics.Prediction(label, None)
        try:
            return metrics.Prediction(label, *backends.answer_parts(q, rec["answers"][qid]))
        except (KeyError, TypeError, ValueError) as e:
            config.error(f"id {rec['id']!r}: no answer to question {qid!r} in its line: {e}")

    def with_label(rec):
        p = prediction(rec)
        return {**rec, "label": p.label, "correct": None if p.failed else p.correct}

    if args.scores:
        if args.out:
            config.error("eval --scores computes the metrics from an existing output and writes no --out")
        records = output.read_records(args.scores)
        ignored = sum(i not in labels for i in records)
        if ignored:
            print(f"{ignored} lines of {args.scores} have ids not in {args.labeled}; ignored", file=sys.stderr)
        scored = [r for i, r in records.items() if i in labels and output.done(r)]
        backend_name = ", ".join(sorted({str(r.get("backend")) for r in scored})) or "-"
        model = ", ".join(sorted({str(r.get("model")) for r in scored})) or "-"
        missing = f"no line in {args.scores}"
    else:
        scored = _score(args, items, qs, with_label)
        records, resumed = scored.records, scored.resumed
        backend_name, model, missing = scored.backend.name, scored.backend.model, "not scored"
        print(_summary(items, sum(not output.done(records[it.id]) for it in items), resumed, args.out),
              file=sys.stderr)
    preds = []
    for it in items:
        rec = records.get(it.id)
        if rec is None:
            print(f"item {it.id}: {missing}", file=sys.stderr)
            preds.append(metrics.Prediction(labels[it.id], None))
            continue
        if not output.done(rec):
            print(f"item {it.id}: {rec['error']}", file=sys.stderr)
        preds.append(prediction(rec))
    m = metrics.evaluate(preds, classes, binary=q.type == "noul")
    m.update(backend=backend_name, model=model, question=qid)
    print(json.dumps(m, indent=2) if args.json else f"backend: {backend_name}  model: {model}\n"
          + metrics.report(m))
    return 1 if m["errors"] else 0


def main(argv: list[str] | None = None) -> int:
    """Run the command in `argv` (default: `sys.argv[1:]`) and return its exit code; `--help`, argument errors and
    command errors (`config.error`: `Error: <msg>` on stderr, exit 1) return their code, an interrupt 130. Checks the
    settings (`config.check_settings`) and leaves `os.environ` unchanged: the wrapper path (`__main__`) exports the
    settings to the environment before it calls `main`."""
    args = None
    try:
        config.check_settings()
        args = build_parser().parse_args(argv)
        if args.command == "routes":
            return args.func(args)
        try:
            return _cmd_run(args) if args.command == "run" else _cmd_eval(args)
        except (AIModelsError, ItemError, QuestionError) as e:
            config.error(str(e))
    except KeyboardInterrupt:
        resume = "; rerun with the same --out to resume" if getattr(args, "out", None) else ""
        print(f"interrupted{resume}", file=sys.stderr)
        return 130
    except SystemExit as e:
        return exit_code(e)
