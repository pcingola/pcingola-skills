#!/usr/bin/env python3
"""
run_batch — the batch loop: iterate pending journal items, render the prompt
template per item, run one fresh `claude -p` invocation, classify the result,
and write done/error back to the journal (with ETA + a timestamped main log).
"""

import sys
import time
from datetime import datetime
from pathlib import Path

from .journal import BatchJournal, JournalEntry
from .runner import ClaudeRunner, now, safe_name
from .status import Status


def eta_str(i: int, n_total: int, durations: list[float]) -> str:
    if len(durations) < 2:
        return ""
    avg = sum(durations) / len(durations)
    remaining_secs = int(avg * (n_total - i + 1))
    hours, remainder = divmod(remaining_secs, 3600)
    mins, secs = divmod(remainder, 60)
    if hours:
        return f" ETA ~{hours}h{mins:02d}m"
    if mins:
        return f" ETA ~{mins}m{secs:02d}s"
    return f" ETA ~{secs}s"


def render_prompt(template_text: str, entry: JournalEntry, variables: dict) -> str:
    """
    Render the prompt template for one entry.

    Reserved placeholders auto-injected every invocation:
        {item_path}       — the primary file (files[0])
        {item_paths}      — all files, newline-joined (for cluster items)
        {signal_done}     {signal_transient}     {signal_fatal}

    Every other {placeholder} must be supplied via `variables` (--var k=v).
    A missing var raises KeyError, caught by the caller as a fail-fast.
    """
    reserved = dict(
        item_path=str(entry.files[0]),
        item_paths="\n".join(str(f) for f in entry.files),
        signal_done=Status.DONE,
        signal_transient=Status.ERROR_TRANSIENT,
        signal_fatal=Status.ERROR_FATAL,
    )
    return template_text.format(**reserved, **variables)


def run_batch(
    journal: BatchJournal,
    template_text: str,
    variables: dict,
    runner: ClaudeRunner,
    main_log: Path,
) -> int:
    """
    Run every pending journal item through the template + runner.

    Returns the number of errors. Resume is automatic: a rerun picks up at the
    first still-PENDING item.
    """
    def log(msg: str) -> None:
        main_log.parent.mkdir(parents=True, exist_ok=True)
        with open(main_log, "a") as f:
            f.write(msg)

    if not journal.has_pending():
        print("Nothing to run — no pending items.")
        return 0

    settings_label = runner.settings or "(none)"
    print(f"""
================================================================
  batch-run
  Journal : {journal.path}
  Settings: {settings_label}
  Started : {now()}
  Main log: {main_log}
================================================================""")
    log(f"=== batch-run started at {now()} | journal={journal.path} ===\n")

    n_err = 0
    n_ok = 0
    durations: list[float] = []
    n_total = len(journal)

    for i, entry in enumerate(journal, 1):
        sep = "-" * 64
        eta = eta_str(i, n_total, durations)
        print(f"{sep}\n  [{i}/{n_total}]{eta} {datetime.now().strftime('%H:%M:%S')}")
        print(f"  Item : {entry.files[0]}")
        print(sep)
        log(f"--- [{i}/{n_total}] {now()} | {entry.files[0]}\n")

        try:
            prompt = render_prompt(template_text, entry, variables)
        except KeyError as e:
            missing = str(e).strip("'")
            sys.exit(
                f"error: template needs {{{missing}}}; pass --var {missing}=..."
            )

        t0 = time.time()
        result_text, exit_code = runner.run(prompt, safe_name(str(entry.files[0])))
        durations.append(time.time() - t0)
        log(result_text + "\n")
        status, reason = runner.classify(result_text, exit_code)

        if status != Status.DONE:
            journal.error(entry, status, reason)
            print(f"  ERROR [{status}]: {reason}")
            log(f"--- ERROR [{status}]: {entry.files[0]} — {reason}\n")
            n_err += 1
        else:
            journal.done(entry)
            print("  OK.")
            log(f"--- OK: {entry.files[0]}\n")
            n_ok += 1

        print()

    summary = f"{n_ok} ok, {n_err} errors."
    print(f"""
================================================================
  batch-run complete. {summary}
  Done at {now()}
================================================================""")
    log(f"=== batch-run finished at {now()} — {summary} ===\n")
    return n_err
