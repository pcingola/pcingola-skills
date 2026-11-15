"""One chapter of animation.json."""
from __future__ import annotations

import re
from dataclasses import dataclass

ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")


@dataclass
class Chapter:
    id: str
    title: str
    duration: float

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "duration": self.duration}
