"""The first take of each Fish voice in this process (`Takes`).

Drama 3 picks a new speaker for each request without a reference, and a fixed seed does not keep it (the speaker
still changes with the text). So the first answer of a model for a voice (`Take`) is the reference of every later
request of that voice: one process, one voice per voice key.

A voice is keyed by the caller's speaker (`speak`'s `speaker`, None for the narrator) and the span's speaker tag
number (`Span.speaker_id`, 0 for a span without a tag). So `<|speaker:1|>` spans of the narrator share one voice,
distinct from the narrator's untagged spans and from `<|speaker:1|>` spans of another caller speaker. A caller that
names no tag number (a saved voice that seeds a speaker) gets tag number 0: the untagged spans of that speaker.

A voice can be linked to a folder of a saved take (`link`): the take is loaded when the folder exists at the link,
else at the first `get` that finds the folder. `fish` calls `get` with the local-model lock held, so a folder that
another process saved while this one waited for the lock seeds the voice before its first request.
"""

from __future__ import annotations

from pathlib import Path

from .fish_take import Take

DEFAULT_TAG = 0  # the speaker tag number of a span without a speaker tag

Key = tuple[str, str | None, int]  # model id, speaker, speaker tag number


class Takes:
    """The first `Take` per (model id, speaker, speaker tag number); the speaker None is the narrator."""

    def __init__(self) -> None:
        self._takes: dict[Key, Take] = {}
        self._folders: dict[Key, Path] = {}  # the saved take each linked voice is seeded from
        self._loaded: set[Key] = set()  # the voices whose take came from their linked folder

    def get(self, model_id: str, speaker: str | None = None, tag: int = DEFAULT_TAG) -> Take | None:
        """The first take of `speaker`'s spans with speaker tag number `tag` by `model_id`, None before it; the take
        of the linked folder when there is none yet and the folder exists (`link`)."""
        key = (model_id, speaker, tag)
        if key not in self._takes and (folder := self._folders.get(key)) is not None and folder.is_dir():
            self._takes[key] = Take.load(folder)
            self._loaded.add(key)
        return self._takes.get(key)

    def keep(self, model_id: str, speaker: str | None, take: Take, tag: int = DEFAULT_TAG) -> Take:
        """Keep `take` as the first take of `speaker`'s spans with speaker tag number `tag` by `model_id` when it
        has none yet; the first take."""
        return self._takes.setdefault((model_id, speaker, tag), take)

    def link(self, model_id: str, speaker: str | None, folder: str | Path) -> Take | None:
        """Seed the untagged spans of `speaker` by `model_id` with the take saved in `folder` (`Take.save`): now when
        the folder exists, else at the first `get` that finds it. The take seeded now, None when the folder does not
        exist yet; `AIModelsError` for a folder that holds no saved take."""
        self._folders[(model_id, speaker, DEFAULT_TAG)] = Path(folder)
        return self.get(model_id, speaker)

    def loaded(self, model_id: str, speaker: str | None = None) -> bool:
        """Whether the take of `speaker`'s untagged spans by `model_id` came from its linked folder."""
        return (model_id, speaker, DEFAULT_TAG) in self._loaded

    def clear(self) -> None:
        """Forget every take and link."""
        self._takes.clear()
        self._folders.clear()
        self._loaded.clear()
