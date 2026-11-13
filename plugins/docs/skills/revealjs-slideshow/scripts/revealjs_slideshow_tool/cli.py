"""revealjs-slideshow CLI: new, vendor, check, themes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import deck


def cmd_new(args: argparse.Namespace) -> int:
    try:
        index = deck.new_deck(Path(args.dir), title=args.title, theme=args.theme, force=args.force)
    except (FileExistsError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(index)
    return 0


def cmd_vendor(args: argparse.Namespace) -> int:
    print(deck.copy_vendor(Path(args.dir)))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    failed = False
    for name in args.html:
        path = Path(name)
        if not path.is_file():
            print(f"{path}: error: no such file", file=sys.stderr)
            failed = True
            continue
        problems = deck.check_deck(path)
        for p in problems:
            print(f"{path}: {p.level}: {p.message}")
        errors = [p for p in problems if p.level == "error"]
        failed = failed or bool(errors)
        if not errors:
            print(f"{path}: ok")
    return 1 if failed else 0


def cmd_themes(args: argparse.Namespace) -> int:
    print("\n".join(deck.themes()))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="revealjs-slideshow", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("new", help="Create DIR/index.html from the template and copy reveal.js into DIR/reveal.js/")
    p.add_argument("dir", help="Deck directory (created if missing)")
    p.add_argument("--title", default="Presentation")
    p.add_argument("--theme", default="black", help="Theme name (see `themes`)")
    p.add_argument("--force", action="store_true", help="Overwrite an existing DIR/index.html")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("vendor", help="Copy or refresh reveal.js into DIR/reveal.js/ (for an existing deck)")
    p.add_argument("dir", help="Directory holding the deck HTML")
    p.set_defaults(func=cmd_vendor)

    p = sub.add_parser("check", help="Check that every file a deck loads exists locally; exit 1 on errors")
    p.add_argument("html", nargs="+", help="Deck HTML file(s)")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("themes", help="List the vendored themes")
    p.set_defaults(func=cmd_themes)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    sys.exit(args.func(args))
