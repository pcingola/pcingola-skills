"""The first take of each Fish voice in this process (`Takes`).

Drama 3 picks a new speaker for each request without a reference, and a fixed seed does not keep it (the speaker
still changes with the text). So the first answer of a model for a voice (`Take`) is the reference of every later
request of that voice: one process, one voice per voice key.

A voice is keyed by the caller's speaker (`speak`'s `speaker`, None for the narrator) and the span's speaker tag
number (`Span.speaker_id`, 0 for a span without a tag). So `<|speaker:1|>` spans of the narrator share one voice,
distinct from the narrator's untagged spans and from `<|speaker:1|>` spans of another caller speaker. A caller that
names no tag number (a saved voice that seeds a speaker) gets tag number 0: the untagged spans of that speaker.
"""

from __future__ import annotations

from .fish_take import Take

DEFAULT_TAG = 0  # the speaker tag number of a span without a speaker tag


class Takes:
    """The first `Take` per (model id, speaker, speaker tag number); the speaker None is the narrator."""

    def __init__(self) -> None:
        self._takes: dict[tuple[str, str | None, int], Take] = {}

    def get(self, model_id: str, speaker: str | None = None, tag: int = DEFAULT_TAG) -> Take | None:
        """The first take of `speaker`'s spans with speaker tag number `tag` by `model_id`, None before it."""
        return self._takes.get((model_id, speaker, tag))

    def keep(self, model_id: str, speaker: str | None, take: Take, tag: int = DEFAULT_TAG) -> Take:
        """Keep `take` as the first take of `speaker`'s spans with speaker tag number `tag` by `model_id` when it
        has none yet; the first take."""
        return self._takes.setdefault((model_id, speaker, tag), take)

    def clear(self) -> None:
        """Forget every take."""
        self._takes.clear()
