"""One `validate` error."""
from __future__ import annotations

from dataclasses import dataclass

from .enums import Rule


@dataclass(frozen=True)
class Issue:
    file: str
    line: int | None
    rule: Rule
    message: str

    def to_dict(self) -> dict:
        return {"file": self.file, "line": self.line, "rule": self.rule.value, "message": self.message}
