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
from pathlib import Path

from ai_models import routes

from . import config
from .models import ASPECT_RATIOS, BACKGROUNDS, DEFAULT_TIER, IMAGE_SIZES, QUALITIES, TIERS

# The config tasks of the tiers; `routes` prints their rows.
ROUTE_TASKS = ("image", "image_edit", "image_best", "image_multi_ref")
_EXT_FORMATS = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".webp": "webp"}


def _read_reference_image(path: str) -> bytes:
    p = Path(path).expanduser()
    if not p.is_file():
        config.error(f"Reference image not found: {p}")
    return p.read_bytes()


def _resolve_output_path(output: str, index: int, total: int) -> Path:
    """Resolve the output path for one image.

    When generating multiple images from a single --out path, an index suffix is
    inserted before the extension: out.png -> out_1.png, out_2.png.
    """
    p = Path(output).expanduser()
    if total > 1:
        p = p.with_stem(f"{p.stem}_{index + 1}")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _cmd_generate(args: argparse.Namespace) -> int:
    from .generate import ImageError, generate

    ext = Path(args.out).suffix.lower()
    output_format = _EXT_FORMATS.get(ext)
    if output_format is None:
        config.error(f"Unsupported output extension {ext!r}; use one of {', '.join(_EXT_FORMATS)}")
    if args.n < 1:
        config.error("--n must be at least 1")

    refs = [_read_reference_image(r) for r in (args.ref or [])]
    if args.mask and not refs:
        config.error("--mask needs a --ref: the mask applies to the first reference image")
    mask = _read_reference_image(args.mask) if args.mask else None
    try:
        images = generate(
            args.prompt,
            negative=args.negative or "",
            reference_images=refs,
            mask=mask,
            aspect_ratio=args.aspect,
            image_size=args.size,
            num_images=args.n,
            model=args.model,
            tier=args.tier,
            quality=args.quality,
            background=args.background,
            output_format=output_format,
        )
    except ImageError as e:
        config.error(e.message)

    for i, image in enumerate(images):
        out_path = _resolve_output_path(args.out, i, len(images))
        out_path.write_bytes(image.data)
        print(str(out_path))
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
        help="OpenAI-style models only (default: IMAGE_GEN_SIZED_QUALITY for the models of IMAGE_GEN_SIZED_MODELS, else the model's)"
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


def main(argv: list[str] | None = None) -> None:
    config.load_settings()
    parser = _build_parser()
    args = parser.parse_args(argv)
    sys.exit(args.func(args))
