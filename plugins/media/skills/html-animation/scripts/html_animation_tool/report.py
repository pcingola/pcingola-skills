"""The result of `validate`."""
from __future__ import annotations

from dataclasses import dataclass, field

from .issue import Issue


@dataclass
class Report:
    errors: list[Issue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def rules(self) -> set[str]:
        return {e.rule.value for e in self.errors}

    def to_dict(self) -> dict:
        return {"ok": self.ok, "errors": [e.to_dict() for e in self.errors]}
