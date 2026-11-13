"""Slide decks: a project of kind `slide` is a deck.

`<deck>/deck.json` (written by the agent) lists the slides in deck order, `[{"k": 1, "title": ...}, ...]`; slide k's
image versions are in `<deck>/slide-<k>/` with the files of an image project (`v<N>.png`, `v<N>.json`, `marks/`).
`project.json` holds `assembly` and `chosen` (`{"<k>": N}`, set by the page); a slide without a chosen version that
exists uses its newest. Assembled decks are `deck-<N>.pptx` with a `deck-<N>.json` sidecar.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .paths import HttpError, positive, read_json

DECK_FILE = "deck.json"
SLIDES_MD = "slides.md"
# Values of `assembly` in project.json and in an `assemble` request; the first is the default of a new deck.
ASSEMBLY = ("images", "native")
SLIDE_DIR = re.compile(r"^slide-([1-9][0-9]*)$")
VERSION_JSON = re.compile(r"^v([1-9][0-9]*)\.json$")
DECK_JSON = re.compile(r"^deck-([1-9][0-9]*)\.json$")


def versions_of(directory: Path) -> list[dict]:
    """`[<v<N>.json> + {"n": N, "image": <abs v<N>.png>}]` of a directory, newest first; a version whose PNG is
    missing or whose JSON is not an object is left out."""
    out = []
    try:
        entries = list(directory.iterdir())
    except OSError:
        return []
    for f in entries:
        m = VERSION_JSON.match(f.name)
        if not m:
            continue
        n = int(m.group(1))
        image = directory / f"v{n}.png"
        data = read_json(f)
        if image.is_file() and isinstance(data, dict):
            out.append({**data, "n": n, "image": str(image)})
    out.sort(key=lambda v: v["n"], reverse=True)
    return out


def slide_titles(deck: Path) -> list[str] | None:
    """The slide titles of deck.json in deck order (slide k is entry k-1), an empty list included; None when it is
    missing or not a list. An entry without a string `title` has the title ""."""
    data = read_json(deck / DECK_FILE)
    if not isinstance(data, list):
        return None
    return [e["title"] if isinstance(e, dict) and isinstance(e.get("title"), str) else "" for e in data]


def slide_count(deck: Path) -> int:
    """The number of slides: the entries of deck.json (0 for an empty list); without a deck.json that is a list,
    the slide-<k> directories numbered 1, 2, ... without a gap."""
    titles = slide_titles(deck)
    if titles is not None:
        return len(titles)
    n = 0
    while (deck / f"slide-{n + 1}").is_dir():
        n += 1
    return n


def slide_dir(deck: Path, k: int) -> Path:
    """`<deck>/slide-<k>`; 400 when it is a link (dangling included) that does not resolve to a directory directly in
    the deck."""
    d = deck / f"slide-{k}"
    if d.is_symlink() or os.path.lexists(d):
        target = d.resolve()
        if target.parent != deck or not target.is_dir():
            raise HttpError(400, f"{d} is not a directory inside the deck")
    return d


def slide_images(deck: Path, body: dict, new: bool = False) -> Path:
    """The directory of the slide `body["slide"]` of the deck, for a request or a write that acts on it: a slide of
    the deck whose directory exists; with `new` (a generate), also a listed slide without a directory yet or the
    slide one past the last. 400 otherwise."""
    k = positive(body, "slide")
    n = slide_count(deck)
    d = slide_dir(deck, k)
    if new and k <= n + 1:
        return d
    if k > n or not d.is_dir():
        raise HttpError(400, f"slide {k} is not a slide of the deck {deck} ({n} slides)")
    return d


def chosen_map(meta: object) -> dict[str, int]:
    """`chosen` of project.json: the entries whose key is a slide number and whose value a version number."""
    chosen = meta.get("chosen") if isinstance(meta, dict) else None
    if not isinstance(chosen, dict):
        return {}
    return {k: v for k, v in chosen.items()
            if isinstance(k, str) and k.isdigit() and isinstance(v, int) and not isinstance(v, bool) and v > 0}


def slides_of(deck: Path, meta: object) -> list[dict]:
    """`[{"k", "title", "dir", "versions", "chosen"}]` in deck order; `chosen` is the version of project.json's
    `chosen` when it exists, else the newest version, else null. A slide whose directory is a link out of the deck
    has `error`, no versions and no chosen version."""
    titles = slide_titles(deck) or []
    chosen = chosen_map(meta)
    out = []
    for k in range(1, slide_count(deck) + 1):
        try:
            d = slide_dir(deck, k)
        except HttpError as e:
            out.append({"k": k, "title": titles[k - 1] if k <= len(titles) else "", "dir": str(deck / f"slide-{k}"),
                        "versions": [], "chosen": None, "error": e.message})
            continue
        versions = versions_of(d) if d.is_dir() else []
        numbers = [v["n"] for v in versions]
        pick = chosen.get(str(k))
        out.append({
            "k": k,
            "title": titles[k - 1] if k <= len(titles) else "",
            "dir": str(d),
            "versions": versions,
            "chosen": pick if pick in numbers else (numbers[0] if numbers else None),
        })
    return out


def decks_of(deck: Path) -> list[dict]:
    """`[<deck-<N>.json> + {"n": N, "path": <abs deck-<N>.pptx>}]`, newest first; a deck whose pptx is missing or
    whose sidecar is not an object is left out."""
    out = []
    for f in deck.iterdir():
        m = DECK_JSON.match(f.name)
        if not m:
            continue
        n = int(m.group(1))
        pptx = deck / f"deck-{n}.pptx"
        data = read_json(f)
        if pptx.is_file() and isinstance(data, dict):
            out.append({**data, "n": n, "path": str(pptx)})
    out.sort(key=lambda d: d["n"], reverse=True)
    return out


def deck_details(deck: Path, meta: object) -> dict:
    """`{"slides_md", "slides", "decks"}` of a deck; `slides_md` is the text of slides.md, or null."""
    try:
        slides_md = (deck / SLIDES_MD).read_text(encoding="utf-8")
    except (OSError, ValueError):
        slides_md = None
    return {"slides_md": slides_md, "slides": slides_of(deck, meta), "decks": decks_of(deck)}


def versions_used(deck: Path, meta: object) -> dict[str, int]:
    """`{"<k>": N}`: the chosen version of every slide, for an `assemble` request; 400 when the deck has no slide or a
    slide has no version."""
    slides = slides_of(deck, meta)
    if not slides:
        raise HttpError(400, "the deck has no slides to assemble")
    bad = [s for s in slides if "error" in s]
    if bad:
        raise HttpError(400, bad[0]["error"])
    missing = [s["k"] for s in slides if s["chosen"] is None]
    if missing:
        raise HttpError(400, f"slide {', '.join(map(str, missing))} has no image yet")
    return {str(s["k"]): s["chosen"] for s in slides}
