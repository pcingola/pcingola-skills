"""The crest factor check of `generate`, for the audio of any music model.

Each request's tracks are measured (`measure.crest_db`). A request whose lowest track crest factor is below
`MUSIC_MIN_CREST_DB` (loud, compressed sound) is sent again, up to `MUSIC_CREST_ATTEMPTS` requests in all. A model that
takes a seed gets the next seed on each request; another model gets the same request again. The first request whose
tracks are all at or above the threshold is kept; when every request is below it, the one with the highest lowest crest
factor is kept. `MUSIC_CREST_ATTEMPTS: 1` or `MUSIC_MIN_CREST_DB: 0` turns the regeneration off; the crest factor is
still measured and recorded.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Generic, TypeVar

from . import config
from .measure import crest_db, decode_bytes

MIN_CREST_KEY = "MUSIC_MIN_CREST_DB"
ATTEMPTS_KEY = "MUSIC_CREST_ATTEMPTS"
DEFAULT_MIN_CREST_DB = 13.0
DEFAULT_ATTEMPTS = 3

T = TypeVar("T")


@dataclass(frozen=True)
class Attempt:
    """One request: its seed (None for a model without one) and the crest factor (dB) of each track."""

    seed: int | None
    crest_db: list[float]

    @property
    def lowest(self) -> float:
        return min(self.crest_db)


@dataclass
class Checked(Generic[T]):
    """The kept request's tracks and attempt, every attempt in order and the threshold."""

    tracks: list[T]
    kept: Attempt
    min_crest_db: float
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def below(self) -> bool:
        return self.kept.lowest < self.min_crest_db

    def record(self, i: int) -> dict:
        """The `crest` entry of the sidecar JSON of track `i` (0-based) of the kept request."""
        return {"crest_db": self.kept.crest_db[i], "min_crest_db": self.min_crest_db,
                "below_threshold": self.kept.crest_db[i] < self.min_crest_db,
                **({"seed": self.kept.seed} if self.kept.seed is not None else {}),
                "attempts": [asdict(a) for a in self.attempts]}


@dataclass(frozen=True)
class CrestCheck:
    """The threshold (dB) and the maximum number of requests."""

    min_crest_db: float = DEFAULT_MIN_CREST_DB
    attempts: int = DEFAULT_ATTEMPTS

    @classmethod
    def from_settings(cls) -> CrestCheck:
        """`MUSIC_MIN_CREST_DB` (a number) and `MUSIC_CREST_ATTEMPTS` (an integer, at least 1) of the settings, else
        the defaults."""
        raw = config.PLUGIN.get(MIN_CREST_KEY)
        try:
            threshold = DEFAULT_MIN_CREST_DB if raw is None else float(raw)
        except ValueError:
            config.PLUGIN.invalid(MIN_CREST_KEY, raw, "a number of dB")
        raw = config.PLUGIN.get(ATTEMPTS_KEY)
        try:
            attempts = DEFAULT_ATTEMPTS if raw is None else int(raw)
        except ValueError:
            attempts = 0
        if attempts < 1:
            config.PLUGIN.invalid(ATTEMPTS_KEY, raw, "an integer of at least 1")
        return cls(threshold, attempts)

    def run(self, generate: Callable[[int | None], Sequence[T]], audio: Callable[[T], bytes],
            seed: int | None) -> Checked[T]:
        """The tracks of `generate(seed)`, `generate(seed + 1)`, ... (`generate(None)` each time when `seed` is
        None) until every track of a request has a crest factor of at least `min_crest_db` or `attempts` requests
        were sent; `audio` gives a track's encoded file."""
        best: Checked[T] | None = None
        tried: list[Attempt] = []
        for n in range(self.attempts):
            s = None if seed is None else seed + n
            tracks = list(generate(s))
            attempt = Attempt(s, [crest_db(decode_bytes(audio(t))) for t in tracks])
            tried.append(attempt)
            if best is None or attempt.lowest > best.kept.lowest:
                best = Checked(tracks, attempt, self.min_crest_db)
            if attempt.lowest >= self.min_crest_db:
                break
        best.attempts = tried
        return best
