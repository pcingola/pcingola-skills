"""`keys`: the list of keyframe images to generate for a morph, written to
DIR/keys.json, and reading it back as a key chain for `morph --from` and
`region --from`. Prompt templates are in assets/prompts.toml."""

from __future__ import annotations

import json
import math
import tomllib
from pathlib import Path

from .frames import EffectError, load_image, write_json

PROMPTS = Path(__file__).resolve().parents[2] / "assets" / "prompts.toml"
KEYS_FILE = "keys.json"
ASPECTS = ["21:9", "16:9", "3:2", "4:3", "5:4", "1:1", "4:5", "3:4", "2:3", "9:16"]
IMAGE_SIZE = "2K"
# None: the model of the image-gen tier.
DEFAULT_MODEL = None
# image-gen tiers (`--tier`); best takes the `image_best` model of image-gen's config.
TIERS = ("best", "fast", "multi-ref")
DEFAULT_TIER = "best"
DEFAULT_FRACTIONS = (0.25, 0.5, 0.75)


def nearest_aspect(width: int, height: int) -> str:
    """The ASPECTS value closest to width/height on a log scale."""
    r = math.log(width / height)

    def dist(a: str) -> float:
        w, h = (int(x) for x in a.split(":"))
        return abs(math.log(w / h) - r)

    return min(ASPECTS, key=dist)


def parse_fractions(text: str) -> list[float]:
    try:
        values = [float(x) for x in text.split(",") if x.strip()]
    except ValueError:
        raise EffectError(f"bad --fractions {text!r}: expected numbers such as 0.25,0.5,0.75") from None
    return check_fractions(values)


def check_fractions(values: list[float] | tuple[float, ...]) -> list[float]:
    """In-between positions: non-empty, in (0, 1), increasing, distinct names."""
    values = list(values)
    if not values:
        raise EffectError("--fractions is empty")
    if any(not 0 < v < 1 for v in values):
        raise EffectError("--fractions must lie strictly between 0 and 1")
    if any(b <= a for a, b in zip(values, values[1:])):
        raise EffectError("--fractions must be increasing")
    names = [pct(v) for v in values]
    if len(set(names)) != len(names):
        raise EffectError(f"--fractions give the same percentage twice: {', '.join(names)}")
    return values


def templates() -> dict:
    with PROMPTS.open("rb") as f:
        return tomllib.load(f)


def pct(fraction: float) -> str:
    return f"{round(fraction * 100, 2):g}"


def stage_text(t: dict, fraction: float) -> str:
    for stage in t["stage"]:
        if fraction <= stage["upto"]:
            return stage["text"]
    return t["stage"][-1]["text"]


def plan(start: Path, style: str, out_dir: Path, end: Path | None = None,
         model: str | None = DEFAULT_MODEL, tier: str = DEFAULT_TIER, fractions: list[float] | tuple[float, ...] = DEFAULT_FRACTIONS) -> dict:
    """The keys.json content: every image to generate, in order."""
    fractions = check_fractions(fractions)
    style = style.strip()
    if not style:
        raise EffectError("--style is empty")
    start = start.resolve()
    img = load_image(start)
    if end is not None:
        end = end.resolve()
        load_image(end)
    out_dir = out_dir.resolve()
    aspect = nearest_aspect(img.shape[1], img.shape[0])
    t = templates()
    images = []
    end_path = end if end is not None else out_dir / "end.png"
    if end is None:
        images.append({
            "name": "end", "role": "end", "fraction": 1.0,
            "prompt": t["end"].format(style=style),
            "refs": [str(start)], "out": str(end_path),
            "tier": tier, "model": model, "aspect": aspect, "size": IMAGE_SIZE,
        })
    betweens = []
    for f in fractions:
        p = pct(f)
        betweens.append({
            "name": f"k{p}", "role": "between", "fraction": f,
            "prompt": t["between"].format(style=style, pct=p, stage=stage_text(t, f)),
            "refs": [str(start), str(end_path)], "out": str(out_dir / f"k{p}.png"),
            "tier": tier, "model": model, "aspect": aspect, "size": IMAGE_SIZE,
        })
    images.extend(betweens)
    return {
        "style": style,
        "tier": tier,
        "model": model,
        "start": str(start),
        "end": str(end_path),
        "chain": [str(start), *(b["out"] for b in betweens), str(end_path)],
        "images": images,
    }


def write(data: dict, out_dir: Path, force: bool) -> Path:
    path = out_dir / KEYS_FILE
    if path.exists() and not force:
        raise EffectError(f"output exists (use --force to replace): {path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(path, data)
    return path


def describe(data: dict) -> str:
    lines = [f"start: {data['start']}", f"end:   {data['end']}", "",
             f"{len(data['images'])} images to generate, in order (references in order):"]
    for i, e in enumerate(data["images"], 1):
        lines += [f"{i}. {e['name']} -> {e['out']}",
                  f"   tier {e['tier']}, model {e['model'] or 'of the tier'}, aspect {e['aspect']}, size {e['size']}",
                  f"   refs: {', '.join(e['refs'])}",
                  f"   prompt: {e['prompt']}"]
    lines += ["", "chain: " + " -> ".join(Path(p).name for p in data["chain"])]
    return "\n".join(lines)


def read_chain(out_dir: Path) -> tuple[list[Path], list[float]]:
    """Key chain from DIR/keys.json: start, in-betweens by fraction, end, and
    their chain times (0, fractions, 1); every file must exist."""
    path = out_dir / KEYS_FILE
    if not path.is_file():
        raise EffectError(f"no {KEYS_FILE} in {out_dir} (run keys first)")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        betweens = sorted((e for e in data["images"] if e.get("role") == "between"), key=lambda e: e["fraction"])
        chain = [Path(data["start"]), *(Path(e["out"]) for e in betweens), Path(data["end"])]
        times = [0.0, *(float(e["fraction"]) for e in betweens), 1.0]
        if betweens:
            check_fractions(times[1:-1])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        raise EffectError(f"bad {path}: {e}") from None
    missing = [str(p) for p in chain if not p.is_file()]
    if missing:
        raise EffectError("keyframes not generated yet: " + ", ".join(missing))
    return chain, times
