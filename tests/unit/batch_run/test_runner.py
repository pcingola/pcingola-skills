"""ClaudeRunner.classify signal parsing, prompt rendering, the missing-variable fail-fast and the ETA."""
from pathlib import Path

import pytest

from batch_run_tool.journal import BatchJournal, JournalEntry
from batch_run_tool.loop import eta_str, render_prompt, run_batch
from batch_run_tool.runner import ClaudeRunner
from batch_run_tool.status import Status


@pytest.fixture
def runner(tmp_path) -> ClaudeRunner:
    """A ClaudeRunner over a temporary directory; classify does no I/O and no test here calls run()."""
    return ClaudeRunner(cwd=tmp_path, runs_dir=tmp_path / "runs")


def test_done(runner):
    """ClaudeRunner.classify maps a final `done: ...` line to Status.DONE. Guards the success signal that
    marks a journal item done.
    """
    status, _ = runner.classify("blah\ndone: 5 products found", 0)
    assert status == Status.DONE


def test_transient_with_reason(runner):
    """ClaudeRunner.classify maps `error_transient:` to ERROR_TRANSIENT and takes the reason after ` - `.
    Guards the hyphen separator rule for reasons.
    """
    assert runner.classify("error_transient: - network timeout", 0) == (Status.ERROR_TRANSIENT, "network timeout")


def test_fatal_with_emdash(runner):
    """ClaudeRunner.classify maps `error_fatal:` to ERROR_FATAL and takes the reason after an em-dash.
    Guards the em-dash separator rule for reasons.
    """
    assert runner.classify("error_fatal: — corrupt pdf", 0) == (Status.ERROR_FATAL, "corrupt pdf")


def test_colon_reason(runner):
    """ClaudeRunner.classify takes the text after `keyword:` as the reason. Guards the documented
    `error_fatal: <reason>` form.
    """
    assert runner.classify("error_fatal: corrupt pdf", 0) == (Status.ERROR_FATAL, "corrupt pdf")


def test_reason_with_hyphens(runner):
    """ClaudeRunner.classify keeps hyphens inside the reason. Guards against splitting `rate-limit` at its
    hyphen.
    """
    assert runner.classify("error_transient: rate-limit - x", 0) == (Status.ERROR_TRANSIENT, "rate-limit - x")


def test_done_payload(runner):
    """ClaudeRunner.classify returns the text after `done:` as the payload."""
    assert runner.classify("done: 5 products found", 0) == (Status.DONE, "5 products found")


def test_last_signal_wins(runner):
    """ClaudeRunner.classify scans the response in reverse, so the last signal line decides. Guards against
    an early `done:` hiding a final error.
    """
    status, _ = runner.classify("done: early\nsome more text\nerror_fatal: real outcome", 0)
    assert status == Status.ERROR_FATAL


def test_no_signal_is_transient(runner):
    """ClaudeRunner.classify returns ERROR_TRANSIENT with the exit code when no signal line exists. Guards
    the rule that a missing signal is retried, not lost or marked done.
    """
    status, reason = runner.classify("no signal here at all", 3)
    assert status == Status.ERROR_TRANSIENT
    assert "exit=3" in reason


def test_reserved_and_vars():
    """loop.render_prompt fills {item_path}, the signal placeholders and --var values. Guards the reserved
    placeholders injected per item.
    """
    entry = JournalEntry(files=[Path("data/a.pdf")])
    out = render_prompt("Read {item_path} write {out_dir}. End: {signal_done}: ok", entry, {"out_dir": "results"})
    assert out == "Read data/a.pdf write results. End: done: ok"


def test_item_paths_multifile():
    """loop.render_prompt joins all files of a cluster item with newlines in {item_paths}. Guards cluster
    items (N files, one invocation).
    """
    entry = JournalEntry(files=[Path("a.pdf"), Path("b.pdf")])
    assert render_prompt("{item_paths}", entry, {}) == "a.pdf\nb.pdf"


def test_missing_var_exits_before_running(tmp_path, runner):
    """loop.run_batch with a template placeholder that no --var supplies exits with `error: template needs
    {out_dir}; pass --var out_dir=...` before the runner starts Claude: no per-item log is written and the
    item stays pending. Guards the fail-fast on a missing variable.
    """
    journal = BatchJournal(tmp_path / "j.json")
    journal.add([JournalEntry(files=[Path("a.txt")])])
    with pytest.raises(SystemExit) as exc:
        run_batch(journal, "{out_dir}", {}, runner, tmp_path / "batch-run.log")
    assert exc.value.code == "error: template needs {out_dir}; pass --var out_dir=..."
    assert list(runner.runs_dir.iterdir()) == []
    assert len(journal) == 1


def test_eta_needs_two_samples():
    """loop.eta_str returns no ETA with fewer than two duration samples. Guards against an estimate from a
    single item.
    """
    assert eta_str(1, 10, [1.0]) == ""


def test_eta_seconds():
    """loop.eta_str multiplies the mean duration by the items left, the current one included, and formats
    seconds. Guards the remaining-count arithmetic and the seconds format.
    """
    assert eta_str(1, 5, [2.0, 2.0]) == " ETA ~10s"
