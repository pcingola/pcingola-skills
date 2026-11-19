#!/usr/bin/env python3
"""
BatchJournal — persistent JSON journal with pending/done/error states.

Library usage:
    j = BatchJournal("jobs/extract.json")

    for entry in j:
        ...use entry.files[0], entry.description...
        j.done(entry)            # or:
        j.error(entry, Status.ERROR_TRANSIENT, "reason")

    j.add([JournalEntry(files=[Path("data/a.pdf")])])
    j.retry()

The journal is a plain JSON file. Writes are atomic (`.tmp` + os.replace) and
iteration re-reads from disk before each step, so a crashed run resumes at the
first still-PENDING item on restart.
"""
import glob as globlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from .status import Status


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class JournalError(BaseModel):
    """Records one failure attempt on a journal entry."""
    reason:    str
    status:    Status
    timestamp: str = Field(default_factory=_now_ts)


class JournalEntry(BaseModel):
    """
    One item in a journal.

    files:       All files associated with this entry. files[0] is the primary file.
                 A list so a cluster item (N files → one invocation) fits without a
                 breaking change.
    description: Optional human-readable label. If empty, display falls back to files[0].name.
    """
    files:       list[Path]
    description: str = ""
    status:      Status = Status.PENDING
    created_at:  str = Field(default_factory=_now_ts)
    done_at:     str | None = None
    errors:      list[JournalError] = Field(default_factory=list)

    @property
    def label(self) -> str:
        return self.description or self.files[0].name


class JournalData(BaseModel):
    items: list[JournalEntry] = Field(default_factory=list)


class BatchJournal:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    # ── iteration ─────────────────────────────────────────────────────────────

    def __iter__(self):
        """
        Iterate over pending entries, re-reading from disk before each step
        so crash-resume works: a restarted process picks up where it left off.
        Advances by index to avoid re-yielding the same entry if the caller
        does not mark it done between steps.
        """
        idx = 0
        while True:
            data = self._load()
            found = None
            for i, entry in enumerate(data.items):
                if i >= idx and entry.status == Status.PENDING:
                    found = (i, entry)
                    break
            if found is None:
                return
            idx = found[0] + 1
            yield found[1]

    # ── reads ─────────────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return sum(1 for entry in self._load().items if entry.status == Status.PENDING)

    def has_pending(self) -> bool:
        return self._next() is not None

    def paths(self) -> set[Path]:
        """Return the set of primary file paths (files[0]) currently in the journal."""
        return {entry.files[0] for entry in self._load().items}

    def pending_paths(self) -> set[Path]:
        """Return primary file paths for entries that are currently PENDING."""
        return {entry.files[0] for entry in self._load().items if entry.status == Status.PENDING}

    # ── mutations ─────────────────────────────────────────────────────────────

    def add(self, entries: list[JournalEntry]) -> None:
        data = self._load()
        data.items.extend(entries)
        self._save(data)

    def done(self, entry: JournalEntry) -> None:
        data = self._load()
        stored = self._resolve(data, entry)
        stored.status = Status.DONE
        stored.done_at = _now_ts()
        self._save(data)

    def error(self, entry: JournalEntry, status: Status, reason: str) -> None:
        """
        Mark an entry as failed.

        Args:
            entry:  The entry returned by iteration.
            status: Status.ERROR_TRANSIENT (safe to retry) or Status.ERROR_FATAL (do not retry).
            reason: Human-readable description of the failure.
        """
        assert status in (Status.ERROR_TRANSIENT, Status.ERROR_FATAL), f"expected ERROR_TRANSIENT or ERROR_FATAL, got {status}"
        data = self._load()
        stored = self._resolve(data, entry)
        stored.status = status
        stored.errors.append(JournalError(reason=reason, status=status))
        self._save(data)

    def retry(self, force: bool = False) -> None:
        """
        Reset failed entries back to PENDING.

        Args:
            force: If False (default), only resets ERROR_TRANSIENT errors.
                   If True, also resets ERROR_FATAL errors.
        """
        data = self._load()
        for stored in data.items:
            if stored.status == Status.ERROR_TRANSIENT or (force and stored.status == Status.ERROR_FATAL):
                stored.status = Status.PENDING
        self._save(data)

    def scan(self, patterns: list[str], cwd: Path | None = None) -> int:
        """
        Add files matching any glob pattern that are not already in the journal.

        Patterns are resolved relative to `cwd` (default: current directory).
        A matched path is stored relative to `cwd` when it lives under it, else
        as an absolute path. Returns the count added.
        """
        cwd = Path(cwd) if cwd else Path.cwd()
        cwd = cwd.resolve()

        data = self._load()
        existing = self.paths()
        added = 0
        matches: list[Path] = []
        for pattern in patterns:
            pat = pattern if os.path.isabs(pattern) else str(cwd / pattern)
            for m in globlib.glob(pat, recursive=True):
                mp = Path(m)
                if mp.is_file():
                    matches.append(mp.resolve())

        for f in sorted(set(matches)):
            try:
                rel = f.relative_to(cwd)
            except ValueError:
                rel = f
            if rel not in existing:
                data.items.append(JournalEntry(files=[rel]))
                existing.add(rel)
                print(f"  + {rel}")
                added += 1
        self._save(data)
        return added

    def show(self, verbose: bool = False) -> None:
        data = self._load()
        if not data.items:
            print("(empty)")
            return
        for i, entry in enumerate(data.items, 1):
            if entry.status == Status.DONE:
                box = "[x]"
            elif entry.status == Status.ERROR_TRANSIENT:
                box = "[!]"
            elif entry.status == Status.ERROR_FATAL:
                box = "[X]"
            else:
                box = "[ ]"
            line = f"- {box} {i}. {entry.label}"
            if entry.errors:
                last = entry.errors[-1]
                line += f"  ← [{last.status.value}] {last.reason} ({last.timestamp})"
            if verbose and entry.errors:
                print(line)
                for n, e in enumerate(entry.errors, 1):
                    print(f"       {n}. [{e.status.value}] {e.reason} ({e.timestamp})")
                continue
            print(line)

    # ── internals ─────────────────────────────────────────────────────────────

    def _next(self) -> JournalEntry | None:
        for entry in self._load().items:
            if entry.status == Status.PENDING:
                return entry
        return None

    def _load(self) -> JournalData:
        if self.path.exists():
            return JournalData.model_validate_json(self.path.read_text())
        return JournalData()

    def _save(self, data: JournalData) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(data.model_dump_json(indent=2))
        os.replace(tmp, self.path)

    def _resolve(self, data: JournalData, entry: JournalEntry) -> JournalEntry:
        """Find the stored copy of entry by matching files[0]."""
        for stored in data.items:
            if stored.files[0] == entry.files[0]:
                return stored
        sys.exit(f"error: entry not found in journal: {entry.files[0]}")


# Alias for brevity
Journal = BatchJournal
