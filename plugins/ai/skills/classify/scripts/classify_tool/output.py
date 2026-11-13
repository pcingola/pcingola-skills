"""The JSONL output of `run` and `eval`: appended and flushed per item, read
back to resume a run, rewritten in input order when the run ends.

While a run is going, each finished item's line is appended in completion
order, and a retried item gets another line; the last line of an id is its
record. When the run ends the file is replaced (temporary file and
`os.replace`) by one line per id in input order. A process killed while
writing leaves a last line without a newline; `read_records` drops it.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, TextIO

from .items import ItemError


def _dump(rec: dict[str, Any]) -> str:
    return json.dumps(rec, ensure_ascii=False) + "\n"


def read_records(path: str | Path, drop_torn: bool = False) -> dict[Any, dict[str, Any]]:
    """The records of a JSONL output by id, the last line of an id winning,
    in order of first appearance. A last line without a newline (a process
    killed while writing it) is ignored; with `drop_torn` it is also cut from
    the file, so lines appended later start on a line of their own."""
    path = Path(path).expanduser()
    try:
        data = path.read_bytes()
    except OSError as e:
        raise ItemError(f"{path}: {e}") from None
    if data and not data.endswith(b"\n"):
        data = data[:data.rfind(b"\n") + 1]
        if drop_torn:
            with path.open("r+b") as f:
                f.truncate(len(data))
    records: dict[Any, dict[str, Any]] = {}
    for n, line in enumerate(data.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError as e:
            raise ItemError(f"{path}:{n}: not JSON: {e}") from None
        if not isinstance(rec, dict) or "id" not in rec:
            raise ItemError(f"{path}:{n}: not an output record (no id)")
        records[rec["id"]] = rec
    return records


def done(rec: dict[str, Any]) -> bool:
    return "error" not in rec


class Output:
    """An output file opened for appending, with the records it already held."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.records = read_records(self.path, drop_torn=True) if self.path.exists() else {}
        self._f: TextIO | None = None

    def open(self) -> None:
        """Open for appending; the file is created only now."""
        self._f = self.path.open("a", encoding="utf-8")

    def write(self, rec: dict[str, Any]) -> None:
        self._f.write(_dump(rec))
        self._f.flush()
        self.records[rec["id"]] = rec

    def finish(self, ids: Iterable[Any],
               update: Callable[[dict[str, Any]], dict[str, Any]] = lambda r: r) -> None:
        """Replace the file with one line per id of `ids` that has a record,
        in the order of `ids`, each passed through `update`."""
        self.close()
        tmp = self.path.with_name(self.path.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for i in ids:
                if i in self.records:
                    f.write(_dump(update(self.records[i])))
        os.replace(tmp, self.path)

    def close(self) -> None:
        if self._f:
            self._f.close()
            self._f = None
