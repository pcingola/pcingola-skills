"""The crest factor check of `generate`: `--min-crest-db`, else the model entry's `min_crest_db`.

A request with a track whose crest factor (`measure.track_crest_db`) is below the threshold (loud, compressed sound) is
sent again, up to `--crest-attempts` requests in all: with the next seed when a seed is given, else as the same request.
The first request with every track at or above the threshold is kept; when every request is below it, the one with the
highest lowest crest factor is kept.
"""

from __future__ import annotations

from collections.abc import Callable

from .measure import MeasureError, track_crest_db

DEFAULT_ATTEMPTS = 3


def regenerate(compose: Callable[[int | None], list], min_crest_db: float, attempts: int,
               seed: int | None) -> tuple[list, list[dict], str | None]:
    """The kept tracks of `compose(seed)`, `compose(seed + 1)`, ... (`compose(None)` each time without a seed), one
    record per request (`seed` when given, `crest_db` of each track, `kept`: true on the kept request) and None. When
    a measurement fails: the tracks of that request, kept with `crest_db` None, and the error. A track has `.audio`,
    its encoded file."""
    kept, kept_low, records = None, None, []
    for n in range(attempts):
        s = None if seed is None else seed + n
        tracks = compose(s)
        try:
            crests = [track_crest_db(t.audio) for t in tracks]
        except MeasureError as e:
            for r in records:
                r["kept"] = False
            records.append({**({"seed": s} if s is not None else {}), "crest_db": None, "kept": True})
            return tracks, records, str(e)
        records.append({**({"seed": s} if s is not None else {}), "crest_db": crests, "kept": False})
        if kept is None or min(crests) > kept_low:
            kept, kept_low = tracks, min(crests)
            for r in records:
                r["kept"] = r is records[-1]
        if kept_low >= min_crest_db:
            break
    return kept, records, None
