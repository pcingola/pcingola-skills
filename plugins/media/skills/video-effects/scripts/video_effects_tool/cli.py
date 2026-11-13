"""video-effects CLI: keys, morph, region, crossfade, blur-crossfade."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from . import effects, keys
from .frames import (STRIP_SUFFIXES, Clip, EffectError, aspect_differs, check_writable, clip_frames, cover_fit,
                     default_strip, encode, ffmpeg_path, ffmpeg_version, load_image, parse_size, sha256,
                     sidecar_path, warn, write_json)

DEFAULT_STEPS_CAP = 240
MAX_STEPS = 480

Build = Callable[[list[np.ndarray], Clip], effects.Frame]


def cmd_keys(args: argparse.Namespace) -> None:
    data = keys.plan(Path(args.start), args.style, Path(args.dir),
                     end=Path(args.end) if args.end else None, model=args.model,
                     tier=args.tier, fractions=keys.parse_fractions(args.fractions))
    path = keys.write(data, Path(args.dir).resolve(), args.force)
    print(keys.describe(data))
    print(f"\nwrote {path}")


def make_clip(args: argparse.Namespace) -> Clip:
    w, h = parse_size(args.size)
    hold_start = args.hold if args.hold_start is None else args.hold_start
    hold_end = args.hold if args.hold_end is None else args.hold_end
    return Clip(width=w, height=h, fps=args.fps, trans=args.trans, hold_start=hold_start,
                hold_end=hold_end, push_in=args.push_in)


def render(args: argparse.Namespace, effect: str, key_paths: list[Path], params: dict, build: Build,
           clip: Clip | None = None) -> dict:
    """Check every option and input, load and fit the keys, render the clip,
    write MP4, strip and sidecar. Returns the sidecar content."""
    clip = clip or make_clip(args)
    if len(key_paths) < 2:
        raise EffectError("need at least 2 key images")
    out = Path(args.out).resolve()
    if out.suffix.lower() != ".mp4":
        raise EffectError(f"--out must end in .mp4: {out}")
    strip = Path(args.strip).resolve() if args.strip else default_strip(out)
    if strip.suffix.lower() not in STRIP_SUFFIXES:
        raise EffectError(f"--strip must end in {', '.join(STRIP_SUFFIXES)}: {strip}")
    side = sidecar_path(out)
    ffmpeg_path()
    check_writable([out, strip, side], args.force)
    canvas = []
    for p in key_paths:  # one decoded original in memory at a time
        img = load_image(p)
        if aspect_differs(img, clip.width, clip.height):
            warn(f"{p}: aspect {img.shape[1]}x{img.shape[0]} differs from the output {clip.width}x{clip.height} "
                 "by more than 2 %; it is centre-cropped")
        canvas.append(cover_fit(img, *clip.canvas))
    del img
    frame = build(canvas, clip)
    count = encode(clip_frames(clip, canvas[0], canvas[-1], frame), clip, out, strip)
    data = {
        "effect": effect,
        "params": {"trans": clip.trans, "hold_start": clip.hold_start, "hold_end": clip.hold_end,
                   "push_in": clip.push_in, **params},
        "inputs": [{"path": str(p.resolve()), "sha256": sha256(p)} for p in key_paths],
        "fps": clip.fps,
        "size": [clip.width, clip.height],
        "canvas": list(clip.canvas),
        "frames": {"hold_start": clip.n_hold_start, "transformation": clip.n_trans,
                   "hold_end": clip.n_hold_end, "total": count},
        "duration": round(count / clip.fps, 6),
        "out": str(out),
        "strip": str(strip),
        "versions": {"opencv": cv2.__version__, "numpy": np.__version__, "ffmpeg": ffmpeg_version()},
    }
    write_json(side, data)
    print(out)
    print(strip)
    print(side)
    return data


def chain(args: argparse.Namespace) -> tuple[list[Path], list[float]]:
    """Key paths and their chain times: the keys.json fractions with --from,
    equal spacing with --keys."""
    if args.from_dir:
        return keys.read_chain(Path(args.from_dir).resolve())
    paths = [Path(p) for p in args.keys]
    n = len(paths)
    return paths, [i / (n - 1) for i in range(n)] if n > 1 else [0.0]


def cmd_morph(args: argparse.Namespace) -> None:
    paths, times = chain(args)
    render(args, "morph", paths, {"key_times": times}, lambda c, clip: effects.morph(c, times))


def cmd_region(args: argparse.Namespace) -> None:
    if not 0 <= args.spread < 1:
        raise EffectError("--spread must be in [0, 1)")
    if not 0 <= args.lum_weight <= 1:
        raise EffectError("--lum-weight must be in [0, 1]")
    if args.seed < 0:
        raise EffectError("--seed must be zero or positive")
    if args.steps is not None and not 2 <= args.steps <= MAX_STEPS:
        raise EffectError(f"--steps must be in [2, {MAX_STEPS}]")
    clip = make_clip(args)
    steps = args.steps or default_steps(clip)
    paths, times = chain(args)
    params = {"spread": args.spread, "lum_weight": args.lum_weight, "seed": args.seed, "steps": steps,
              "key_times": times}
    render(args, "region", paths, params,
           lambda c, clip: effects.region(c, steps, args.spread, args.lum_weight, args.seed, times), clip)


def default_steps(clip: Clip) -> int:
    """Region flow-sequence length: twice the transformation frames, capped."""
    return min(2 * clip.n_trans, DEFAULT_STEPS_CAP)


def cmd_crossfade(args: argparse.Namespace) -> None:
    render(args, "crossfade", [Path(args.a), Path(args.b)], {}, lambda c, clip: effects.crossfade(c[0], c[1]))


def cmd_blur_crossfade(args: argparse.Namespace) -> None:
    if args.blur < 0:
        raise EffectError("--blur must be zero or positive")
    render(args, "blur-crossfade", [Path(args.a), Path(args.b)], {"blur": args.blur},
           lambda c, clip: effects.blur_crossfade(c[0], c[1], args.blur * (1 + clip.push_in)))


def common_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--out", required=True, help="output MP4")
    p.add_argument("--trans", type=float, default=3.5, help="transformation seconds (default 3.5)")
    p.add_argument("--hold", type=float, default=1.5, help="hold seconds on start and end (default 1.5)")
    p.add_argument("--hold-start", type=float, help="hold seconds on the start image (overrides --hold)")
    p.add_argument("--hold-end", type=float, help="hold seconds on the end image (overrides --hold)")
    p.add_argument("--push-in", type=float, default=0.08, help="centred zoom over the clip (default 0.08, 0 = off)")
    p.add_argument("--size", default="1920x1080", help="output WxH, even (default 1920x1080)")
    p.add_argument("--fps", type=float, default=30, help="frames per second (default 30)")
    p.add_argument("--strip", help="frame strip PNG (default <out stem>_frames.png)")
    p.add_argument("--force", action="store_true", help="replace existing outputs")
    return p


def add_chain(p: argparse.ArgumentParser) -> None:
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--keys", nargs="+", metavar="KEY", help="key images in order, start first, end last")
    g.add_argument("--from", dest="from_dir", metavar="DIR", help="directory with keys.json (from `keys`)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="video-effects", description=__doc__)
    sub = parser.add_subparsers(dest="command")
    common = common_parser()

    p = sub.add_parser("keys", help="write DIR/keys.json: the keyframe images to generate")
    p.add_argument("start", help="start image")
    p.add_argument("--style", required=True, help="the target style, in words")
    p.add_argument("--dir", required=True, help="directory for keys.json and the generated images")
    p.add_argument("--end", help="an existing end image (default: generate one from the start image)")
    p.add_argument("--model", default=keys.DEFAULT_MODEL,
                   help="image-gen model id <provider>:<model>; replaces the tier's model (default: none)")
    p.add_argument("--tier", choices=keys.TIERS, default=keys.DEFAULT_TIER,
                   help=f"image-gen tier (default {keys.DEFAULT_TIER}: the image_best model of its config)")
    p.add_argument("--fractions", default=",".join(f"{f:g}" for f in keys.DEFAULT_FRACTIONS),
                   help="in-between positions (default 0.25,0.5,0.75)")
    p.add_argument("--force", action="store_true", help="replace an existing keys.json")
    p.set_defaults(func=cmd_keys)

    p = sub.add_parser("morph", parents=[common], help="optical-flow morph along a key chain")
    add_chain(p)
    p.set_defaults(func=cmd_morph)

    p = sub.add_parser("region", parents=[common], help="flow morph where parts of the image change at different times")
    add_chain(p)
    p.add_argument("--spread", type=float, default=0.55, help="fraction of the clip over which regions are staggered")
    p.add_argument("--lum-weight", type=float, default=0.35, help="weight of the end image's luminance in the delay")
    p.add_argument("--seed", type=int, default=7, help="noise seed (same seed, same output)")
    p.add_argument("--steps", type=int,
                   help=f"frames of the underlying flow sequence (default 2 x transformation frames, "
                        f"at most {DEFAULT_STEPS_CAP}; override up to {MAX_STEPS})")
    p.set_defaults(func=cmd_region)

    for name, func, helptext in (("crossfade", cmd_crossfade, "eased crossfade of two images"),
                                 ("blur-crossfade", cmd_blur_crossfade, "eased crossfade under a rising and falling blur")):
        p = sub.add_parser(name, parents=[common], help=helptext)
        p.add_argument("a", help="start image")
        p.add_argument("b", help="end image")
        if name == "blur-crossfade":
            p.add_argument("--blur", type=float, default=20.0, help="Gaussian sigma at mid-transition, output px (default 20)")
        p.set_defaults(func=func)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    try:
        args.func(args)
    except EffectError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
