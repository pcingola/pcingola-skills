#!/usr/bin/env python3
"""
batch-run — portable journal-driven batch inference.

Iterate a list of items, run one fresh `claude -p` invocation per item from a
prompt template, track progress in a resumable on-disk journal, classify
success/transient/fatal, and retry failures.

Subcommands:
    scan   <journal.json> <glob> [<glob> ...]                 add matching files as PENDING
    add    <journal.json> <path> [<path> ...]                 add specific items (1 entry each)
    list   <journal.json> [-v]                                show items + status
    done   <journal.json> <n>                                 mark item n done (1-based)
    error  <journal.json> <n> --reason TEXT [--fatal]         mark item n failed
    retry  <journal.json> [--all]                             transient→pending; --all incl. fatal
    run    <journal.json> <template.md> [--var k=v ...] [--cwd DIR] [--settings S] [--runs-dir DIR]
"""

import argparse
import sys
from pathlib import Path

from .journal import BatchJournal, JournalEntry
from .loop import run_batch
from .runner import ClaudeRunner
from .status import Status


def _entry_at(journal: BatchJournal, index: int):
    """Return the 1-based entry at `index`, or exit with a clear message if out of range."""
    items = journal._load().items
    if not 1 <= index <= len(items):
        sys.exit(f"error: index {index} out of range (journal has {len(items)} item(s))")
    return items[index - 1]


def _parse_vars(pairs: list[str]) -> dict:
    out: dict = {}
    for pair in pairs or []:
        if "=" not in pair:
            sys.exit(f"error: --var expects k=v, got: {pair}")
        k, v = pair.split("=", 1)
        out[k] = v
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="batch-run",
        description="Journal-driven batch inference: one fresh `claude -p` per item, resumable, with retry.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="add files matching glob(s) as pending items")
    p_scan.add_argument("journal")
    p_scan.add_argument("globs", nargs="+", help="glob pattern(s), resolved relative to --cwd")
    p_scan.add_argument("--cwd", default=None, help="base dir for globs and stored paths (default: current dir)")

    p_add = sub.add_parser("add", help="add specific paths (one entry each)")
    p_add.add_argument("journal")
    p_add.add_argument("paths", nargs="+")

    p_list = sub.add_parser("list", help="show items + status")
    p_list.add_argument("journal")
    p_list.add_argument("-v", "--verbose", action="store_true", help="show full error history")

    p_done = sub.add_parser("done", help="mark item n (1-based) done")
    p_done.add_argument("journal")
    p_done.add_argument("index", type=int)

    p_error = sub.add_parser("error", help="mark item n (1-based) failed")
    p_error.add_argument("journal")
    p_error.add_argument("index", type=int)
    p_error.add_argument("--reason", required=True)
    p_error.add_argument("--fatal", action="store_true", help="mark ERROR_FATAL (not retried by default)")

    p_retry = sub.add_parser("retry", help="reset failed items to pending")
    p_retry.add_argument("journal")
    p_retry.add_argument("--all", dest="force", action="store_true", help="also reset ERROR_FATAL")

    p_run = sub.add_parser("run", help="run pending items through a prompt template")
    p_run.add_argument("journal")
    p_run.add_argument("template", help="path to the prompt template (.md)")
    p_run.add_argument("--var", dest="vars", action="append", metavar="k=v",
                       help="template variable (repeatable)")
    p_run.add_argument("--cwd", default=None, help="working dir for the claude subprocess (default: current dir)")
    p_run.add_argument("--settings", default="", help="path passed as `claude --settings`")
    p_run.add_argument("--runs-dir", default="batch-runs", help="dir for per-item logs (default: ./batch-runs)")

    return parser


def main() -> None:
    args = build_parser().parse_args()
    j = BatchJournal(args.journal)

    if args.cmd == "scan":
        cwd = Path(args.cwd) if args.cwd else None
        n = j.scan(args.globs, cwd)
        print(f"Scan complete: {n} new item(s) added.", file=sys.stderr)

    elif args.cmd == "add":
        j.add([JournalEntry(files=[Path(p)]) for p in args.paths])
        print(f"Added {len(args.paths)} item(s).", file=sys.stderr)

    elif args.cmd == "list":
        j.show(verbose=args.verbose)

    elif args.cmd == "done":
        j.done(_entry_at(j, args.index))

    elif args.cmd == "error":
        entry = _entry_at(j, args.index)
        j.error(entry, Status.ERROR_FATAL if args.fatal else Status.ERROR_TRANSIENT, args.reason)

    elif args.cmd == "retry":
        j.retry(force=args.force)

    elif args.cmd == "run":
        template_path = Path(args.template)
        if not template_path.exists():
            sys.exit(f"error: template not found: {template_path}")
        template_text = template_path.read_text()
        variables = _parse_vars(args.vars)
        cwd = Path(args.cwd).resolve() if args.cwd else Path.cwd()
        runs_dir = Path(args.runs_dir)
        runner = ClaudeRunner(cwd=cwd, runs_dir=runs_dir, settings=args.settings)
        main_log = runs_dir / "batch-run.log"
        n_err = run_batch(j, template_text, variables, runner, main_log)
        sys.exit(1 if n_err else 0)


if __name__ == "__main__":
    main()
