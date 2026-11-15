"""The crest factor check of `generate`, for a model whose config entry has `min_crest_db`.

A request with a track whose crest factor (`measure.crest_db`) is below the model's `min_crest_db` (loud, compressed
sound) is sent again, up to `MUSIC_CREST_ATTEMPTS` requests in all: with the next seed when a seed is given, else as the
same request. The first request with every track at or above the threshold is kept; when every request is below it, the
one with the highest lowest crest factor is kept.
"""

from __future__ import annotations

from collections.abc import Callable

from . import config
from .measure import crest_db, decode

ATTEMPTS_KEY = "MUSIC_CREST_ATTEMPTS"
DEFAULT_ATTEMPTS = 3


def attempts_setting() -> int:
    """`MUSIC_CREST_ATTEMPTS` of the settings (an integer, at least 1), else DEFAULT_ATTEMPTS."""
    raw = config.PLUGIN.get(ATTEMPTS_KEY)
    try:
        n = DEFAULT_ATTEMPTS if raw is None else int(raw)
    except ValueError:
        n = 0
    if n < 1:
        config.PLUGIN.invalid(ATTEMPTS_KEY, raw, "an integer of at least 1")
    return n


def regenerate(compose: Callable[[int | None], list], min_crest_db: float, attempts: int,
               seed: int | None) -> tuple[list, list[dict]]:
    """The kept tracks of `compose(seed)`, `compose(seed + 1)`, ... (`compose(None)` each time without a seed), and
    one record per request: `seed` (when given), `crest_db` (the crest factor of each track) and `kept` (true on the
    kept request). A track has `.audio`, its encoded file."""
    kept, kept_low, records = None, None, []
    for n in range(attempts):
        s = None if seed is None else seed + n
        tracks = compose(s)
        crests = [crest_db(decode(t.audio, sr=None)) for t in tracks]
        records.append({**({"seed": s} if s is not None else {}), "crest_db": crests, "kept": False})
        if kept is None or min(crests) > kept_low:
            kept, kept_low = tracks, min(crests)
            for r in records:
                r["kept"] = r is records[-1]
        if kept_low >= min_crest_db:
            break
    return kept, records
