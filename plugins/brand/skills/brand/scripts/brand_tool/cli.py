"""Argparse dispatcher for `brand <command>`.

Commands:
    list                 every brand name and the folder it resolves to
    show <name>          the resolved folder, then the text of its brand.yaml
    copy <name> <dest>   copy the brand folder to <dest>/<name>/
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from plugin_settings import exit_code

from . import config
from .config import BrandError


def cmd_list(args: argparse.Namespace) -> int:
    brands = config.list_brands()
    if not brands:
        dirs = config.search_dirs()
        raise BrandError(f"no brands found. Searched: {config.searched(dirs)}")
    width = max(len(name) for name, _ in brands)
    for name, folder in brands:
        print(f"{name:<{width}}  {folder}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    folder = config.find(args.name)
    print(folder)
    text = (folder / config.BRAND_FILE).read_text(encoding="utf-8")
    sys.stdout.write(text if text.endswith("\n") else text + "\n")
    return 0


def copy_brand(name: str, dest: Path, force: bool = False, bundled: Path | None = None) -> Path:
    """Copy brand `name` to `<dest>/<name>/` and return the target path."""
    src = config.find(name, bundled)
    target = dest / name
    # Resolve dest only: a symlink at the target is replaced, never followed.
    s, t = src.resolve(), dest.resolve() / name
    if t.is_relative_to(s) or s.is_relative_to(t):
        raise BrandError(f"source {src} and target {target} overlap")
    if (target.exists() or target.is_symlink()) and not force:
        raise BrandError(f"{target} exists; pass --force to replace it")
    try:
        dest.mkdir(parents=True, exist_ok=True)
        # Copy next to the target first, so a failed copy leaves the old target intact.
        tmp = Path(tempfile.mkdtemp(prefix=f".{name}.", dir=dest))
        try:
            shutil.copytree(src, tmp / name)
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            elif target.exists() or target.is_symlink():
                target.unlink()
            (tmp / name).rename(target)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    except OSError as e:
        raise BrandError(f"cannot copy {src} to {target}: {e}") from e
    return target


def cmd_copy(args: argparse.Namespace) -> int:
    target = copy_brand(args.name, Path(args.dest).expanduser(), force=args.force)
    print(target)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="brand",
        description="Find, show and copy brand folders (bundled brands, then the brand.path setting).",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("list", help="every brand name and the folder it resolves to")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("show", help="the resolved folder and its brand.yaml")
    sp.add_argument("name")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("copy", help="copy the brand folder to <dest>/<name>/")
    sp.add_argument("name")
    sp.add_argument("dest", help="directory that receives <name>/ (created if missing)")
    sp.add_argument("--force", action="store_true", help="replace an existing <dest>/<name>/")
    sp.set_defaults(func=cmd_copy)
    return p


def main(argv: list[str] | None = None) -> int:
    """Run the command in `argv` (default: `sys.argv[1:]`) and return its exit code; `--help`, argument errors,
    an invalid settings file and `BrandError` (`Error: <msg>` on stderr, exit 1) return their code. Checks the
    settings (`config.check_settings`) and leaves `os.environ` unchanged: the wrapper path (`__main__`) exports the
    settings to the environment before it calls `main`."""
    try:
        config.check_settings()
        args = build_parser().parse_args(argv)
        return args.func(args)
    except BrandError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except SystemExit as e:
        return exit_code(e)
