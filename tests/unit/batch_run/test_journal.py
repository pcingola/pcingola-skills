"""BatchJournal: iteration order, done/error/retry transitions, crash-resume and glob scan."""
from pathlib import Path

from batch_run_tool.journal import BatchJournal, JournalEntry
from batch_run_tool.status import Status


def test_add_and_iterate(tmp_path):
    """BatchJournal iteration yields pending entries in insertion order and done() removes them from the
    pending count. Guards the order of a batch run and the done transition.
    """
    j = BatchJournal(tmp_path / "j.json")
    j.add([JournalEntry(files=[Path("a.txt")]), JournalEntry(files=[Path("b.txt")])])
    assert len(j) == 2
    seen = []
    for entry in j:
        seen.append(entry.files[0].name)
        j.done(entry)
    assert seen == ["a.txt", "b.txt"]
    assert len(j) == 0


def test_error_and_retry(tmp_path):
    """BatchJournal.error with ERROR_TRANSIENT takes an entry out of pending and retry() puts it back.
    Guards the transient retry path of `batch-run retry`.
    """
    j = BatchJournal(tmp_path / "j.json")
    j.add([JournalEntry(files=[Path("a.txt")])])
    entry = next(iter(j))
    j.error(entry, Status.ERROR_TRANSIENT, "boom")
    assert len(j) == 0
    j.retry()
    assert len(j) == 1


def test_fatal_not_retried_without_force(tmp_path):
    """BatchJournal.retry leaves ERROR_FATAL entries alone unless force=True (`retry --all`). Guards the
    transient/fatal split that keeps fatal items from rerunning.
    """
    j = BatchJournal(tmp_path / "j.json")
    j.add([JournalEntry(files=[Path("a.txt")])])
    entry = next(iter(j))
    j.error(entry, Status.ERROR_FATAL, "corrupt")
    j.retry()
    assert len(j) == 0
    j.retry(force=True)
    assert len(j) == 1


def test_crash_resume_by_reload(tmp_path):
    """A second BatchJournal on the same file sees an entry marked done by the first and yields only the
    rest. Guards crash-resume, which depends on re-reading the journal from disk.
    """
    path = tmp_path / "j.json"
    j = BatchJournal(path)
    j.add([JournalEntry(files=[Path("a.txt")]), JournalEntry(files=[Path("b.txt")])])
    first = next(iter(j))
    assert first.files[0].name == "a.txt"
    j.done(first)
    assert [e.files[0].name for e in BatchJournal(path)] == ["b.txt"]


def test_scan_globs_relative_to_cwd(tmp_path):
    """BatchJournal.scan matches the glob relative to cwd and stores matched paths relative to it. Guards
    the relative-path rule that keeps a journal portable with its working directory.
    """
    for name in ("one.pdf", "two.pdf", "skip.txt"):
        (tmp_path / name).write_text("x")
    j = BatchJournal(tmp_path / "j.json")
    assert j.scan(["*.pdf"], cwd=tmp_path) == 2
    assert sorted(p.name for p in j.paths()) == ["one.pdf", "two.pdf"]
    assert all(not p.is_absolute() for p in j.paths())


def test_scan_dedupes(tmp_path):
    """BatchJournal.scan skips files already in the journal and returns 0 on a rescan. Guards against
    duplicate items when scan is rerun.
    """
    (tmp_path / "one.pdf").write_text("x")
    j = BatchJournal(tmp_path / "j.json")
    assert j.scan(["*.pdf"], cwd=tmp_path) == 1
    assert j.scan(["*.pdf"], cwd=tmp_path) == 0
