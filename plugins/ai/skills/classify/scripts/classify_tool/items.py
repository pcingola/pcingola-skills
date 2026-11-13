"""Items to classify: `--item` texts or a `.jsonl`, `.csv` or `.txt` file.

    .jsonl  one object per line with `text`, optional `id` (default: line number)
    .csv    header row with a `text` column, optional `id` (default: row number)
    .txt    one item per non-blank line, id = line number

Labelled files (`eval`) are `.jsonl` or `.csv` with a `label` as well; a JSON
boolean label becomes "true"/"false". Ids are strings or integers and must be
unique. A UTF-8 byte order mark at the start of a CSV file is ignored.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ItemError(ValueError):
    """An unreadable or invalid items file."""


@dataclass(frozen=True)
class Item:
    id: Any
    text: str
    label: str | None = None


def normalize_label(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v).strip()


def _item(where: str, id_: Any, text: Any, label: Any, labeled: bool) -> Item:
    if isinstance(id_, bool) or not isinstance(id_, (str, int)):
        raise ItemError(f"{where}: id must be a string or an integer, got {id_!r}")
    if not isinstance(text, str):
        raise ItemError(f"{where}: no text")
    if labeled:
        if label is None or normalize_label(label) == "":
            raise ItemError(f"{where}: no label")
        return Item(id_, text, normalize_label(label))
    return Item(id_, text)


def _jsonl(path: Path, labeled: bool) -> list[Item]:
    items = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        where = f"{path}:{n}"
        try:
            d = json.loads(line)
        except ValueError as e:
            raise ItemError(f"{where}: not JSON: {e}") from None
        if not isinstance(d, dict):
            raise ItemError(f"{where}: not a JSON object")
        items.append(_item(where, d.get("id", n), d.get("text"), d.get("label"), labeled))
    return items


def _csv(path: Path, labeled: bool) -> list[Item]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        need = {"text", "label"} if labeled else {"text"}
        missing = need - set(reader.fieldnames or ())
        if missing:
            raise ItemError(f"{path}: no {', '.join(sorted(missing))} column")
        return [
            _item(f"{path}: row {n}", row.get("id") or n, row["text"], row.get("label"), labeled)
            for n, row in enumerate(reader, 1)
        ]


def _txt(path: Path) -> list[Item]:
    return [Item(n, line) for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if line.strip()]


def check_unique(items: list[Item]) -> list[Item]:
    seen = set()
    for it in items:
        if it.id in seen:
            raise ItemError(f"duplicate id {it.id!r}")
        seen.add(it.id)
    return items


def read_items(path: str | Path, labeled: bool = False) -> list[Item]:
    """The items of a `.jsonl`, `.csv` or `.txt` file (`.txt` not for labelled items)."""
    path = Path(path).expanduser()
    suffix = path.suffix.lower()
    try:
        if suffix == ".jsonl":
            items = _jsonl(path, labeled)
        elif suffix == ".csv":
            items = _csv(path, labeled)
        elif suffix == ".txt" and not labeled:
            items = _txt(path)
        else:
            kinds = ".jsonl or .csv" if labeled else ".jsonl, .csv or .txt"
            raise ItemError(f"{path}: items file must be {kinds}")
    except OSError as e:
        raise ItemError(f"{path}: {e}") from None
    if not items:
        raise ItemError(f"{path}: no items")
    return check_unique(items)


def items_from_texts(texts: list[str]) -> list[Item]:
    """`--item` texts, ids 1..N."""
    return [Item(n, t) for n, t in enumerate(texts, 1)]
