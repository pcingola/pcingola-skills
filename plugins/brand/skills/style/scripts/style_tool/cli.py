"""Argparse dispatcher for `style <command>`.

Commands:
    index    write references/index.md and references/catalogue.json from the style files
"""

from __future__ import annotations

import argparse
import sys

from . import index
from .index import StyleError


def cmd_index(args: argparse.Namespace) -> int:
    text = index.render_index()
    catalogue = index.render_catalogue()
    index.INDEX_FILE.write_text(text, encoding="utf-8")
    index.CATALOGUE_FILE.write_text(catalogue, encoding="utf-8")
    print(index.INDEX_FILE)
    print(index.CATALOGUE_FILE)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="style", description="Maintain the style catalogue.")
    sub = p.add_subparsers(dest="command", required=True)
    sp = sub.add_parser("index", help="write references/index.md and references/catalogue.json from the style files")
    sp.set_defaults(func=cmd_index)
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        rc = args.func(args)
    except (StyleError, OSError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(rc)
