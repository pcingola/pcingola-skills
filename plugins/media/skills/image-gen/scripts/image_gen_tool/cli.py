"""Argparse dispatcher for `image-gen <command>`.

Commands:
    generate   Generate one or more images from a text prompt.
    routes     Print the model routes of the image tasks (`ai_models.routes`).

The model is `--model`, else the model of the config task of `--tier`:
`fast` (default) takes `image` (`image_edit` with `--ref`), `best` takes
`image_best`, `multi-ref` takes `image_multi_ref`. Reference images (`--ref`) steer or edit
from existing images; `--mask` marks the area of the first reference image to
edit (OpenAI-style and local models). Each generated file's path is printed
to stdout, one per line.
"""

from __future__ import annotations

import argparse
import sys

from ai_models import routes

from . import config
from .models import ASPECT_RATIOS, BACKGROUNDS, DEFAULT_TIER, IMAGE_SIZES, QUALITIES, TIERS

# The config tasks of the tiers; `routes` prints their rows.
ROUTE_TASKS = ("image", "image_edit", "image_best", "image_multi_ref")


def _cmd_generate(args: argparse.Namespace) -> int:
    """`generate`: write the images (`generate.write_images`) and print each path as soon as it is written; an
    `ImageError` exits 1 with `Error: <message>` on stderr."""
    from .generate import ImageError, write_images

    try:
        write_images(args.prompt, args.out, negative=args.negative or "", refs=args.ref or [], mask=args.mask,
                     aspect_ratio=args.aspect, image_size=args.size, num_images=args.n, model=args.model,
                     tier=args.tier, quality=args.quality, background=args.background,
                     on_written=lambda path: print(str(path)))
    except ImageError as e:
        config.error(e.message)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="image-gen",
        description="Generate images from text prompts with the image models of the ai_models config.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="Generate image(s) from a text prompt")
    g.add_argument("--prompt", required=True, help="Text prompt describing the image")
    g.add_argument("--out", required=True, help="Output path, e.g. images/hero.png")
    g.add_argument("--negative", default="", help="What NOT to include (folded into the prompt)")
    g.add_argument(
        "--ref",
        action="append",
        metavar="PATH",
        help="Reference image for editing/style; repeat for multiple",
    )
    g.add_argument(
        "--mask",
        metavar="PATH",
        help="OpenAI-style and local models: PNG of the first --ref's pixel size, transparent where the "
             "image may change",
    )
    g.add_argument("--aspect", choices=ASPECT_RATIOS, default=None,
                   help="Aspect ratio (default: the model's; a local edit keeps the first --ref's size)")
    g.add_argument("--size", choices=IMAGE_SIZES, default=None, help="Image size (default: the model's)")
    g.add_argument("--n", type=int, default=1, help="Number of images (default 1)")
    g.add_argument(
        "--model",
        default=None,
        help="Model id <provider>:<model> of the ai_models config; replaces the --tier model",
    )
    g.add_argument(
        "--tier", choices=TIERS, default=DEFAULT_TIER,
        help="Config task of the model: fast (image, image_edit with --ref), best (image_best), "
             f"multi-ref (image_multi_ref); default {DEFAULT_TIER}",
    )
    g.add_argument(
        "--quality", choices=QUALITIES, default=None,
        help="OpenAI-style models only (default: the model's image.default_quality in config.yaml, else the model's)"
    )
    g.add_argument(
        "--background",
        choices=BACKGROUNDS,
        default=None,
        help="OpenAI-style models only; transparent needs a .png or .webp output",
    )
    g.set_defaults(func=_cmd_generate)

    routes.command(sub, ROUTE_TASKS)
    return p


def main(argv: list[str] | None = None) -> int:
    """Run the command in `argv` (default: `sys.argv[1:]`) and return its exit code; `--help`, argument errors and
    command errors (`config.error`: `Error: <msg>` on stderr, exit 1) return their code. Checks the settings
    (`config.check_settings`) and leaves `os.environ` unchanged: the wrapper path (`__main__`) exports the settings
    to the environment before it calls `main`."""
    try:
        config.check_settings()
        args = _build_parser().parse_args(argv)
        return args.func(args)
    except SystemExit as e:
        if e.code is None or isinstance(e.code, int):
            return e.code or 0
        print(e.code, file=sys.stderr)
        return 1
