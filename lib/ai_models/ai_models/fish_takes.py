"""The first take of each Fish voice in this process (`Takes`).

Drama 3 picks a new speaker for each request without a reference, and a fixed seed does not keep it (the speaker
still changes with the text). So the first answer of a model for a speaker (`Take`) is the reference of every later
request of that speaker: one process, one voice per speaker.
"""

from __future__ import annotations

from .fish_take import Take


class Takes:
    """The first `Take` per (model id, speaker); the speaker None is the narrator."""

    def __init__(self) -> None:
        self._takes: dict[tuple[str, str | None], Take] = {}

    def get(self, model_id: str, speaker: str | None = None) -> Take | None:
        """The first take of `speaker` by `model_id`, None before it."""
        return self._takes.get((model_id, speaker))

    def keep(self, model_id: str, speaker: str | None, take: Take) -> Take:
        """Keep `take` as the first take of `speaker` by `model_id` when it has none yet; the first take."""
        return self._takes.setdefault((model_id, speaker), take)

    def clear(self) -> None:
        """Forget every take."""
        self._takes.clear()
