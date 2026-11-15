"""Command dispatch. Every command prints JSON on stdout; errors go to stderr with exit status 1."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from plugin_settings import Plugin

from .browser import Browser
from .builder import Builder
from .common import HAError
from .enums import ExtraLib, Size, TimingLib
from .mark import Mark
from .project import Project
from .renderer import Renderer, still_name
from .validator import Validator


def parse_times(text: str) -> list[float]:
    try:
        times = [float(v) for v in text.split(",") if v.strip()]
    except ValueError:
        raise HAError(f"--at {text!r}: expected seconds, comma separated") from None
    if not times or any(t < 0 for t in times):
        raise HAError(f"--at {text!r}: expected one or more times of at least 0 seconds")
    return times


def parse_extras(text: str | None) -> tuple[ExtraLib, ...]:
    names = [v.strip() for v in (text or "").split(",") if v.strip()]
    valid = [e.value for e in ExtraLib]
    bad = [n for n in names if n not in valid]
    if bad:
        raise HAError(f"--with: unknown {', '.join(bad)}; expected some of {', '.join(valid)}")
    return tuple(ExtraLib(n) for n in names)


def cmd_init(a: argparse.Namespace) -> dict:
    return Project(a.folder).init(TimingLib(a.lib), Size(a.size), a.title, parse_extras(a.with_libs))


def cmd_add_chapter(a: argparse.Namespace) -> dict:
    return Project(a.folder).add_chapter(a.id, a.duration, a.title)


def cmd_build(a: argparse.Namespace) -> dict:
    return Builder(Project(a.folder)).build()


def cmd_validate(a: argparse.Namespace) -> dict:
    return Validator(Project(a.folder)).run().to_dict()


def _check_times(project: Project, times: list[float]) -> None:
    total = project.load().duration
    late = [t for t in times if t > total + 1e-9]
    if late:
        raise HAError(f"--at {', '.join(f'{t:g}' for t in late)} is past the end of the animation ({total:g} s)")


def cmd_still(a: argparse.Namespace) -> dict:
    project = Project(a.folder)
    t = parse_times(a.at)
    if len(t) != 1:
        raise HAError("still takes one time; stills takes several")
    _check_times(project, t)
    mark = Mark.parse(a.mark) if a.mark else None
    out = Path(a.out).resolve() if a.out else project.folder / "stills" / still_name(t[0])
    result = Renderer(project).render(t, [out])
    if mark:
        mark.draw(out)
    return {"png": str(out), "t": t[0], **({"mark": mark.to_dict()} if mark else {}), "warnings": result["warnings"]}


def cmd_stills(a: argparse.Namespace) -> dict:
    project = Project(a.folder)
    times = parse_times(a.at)
    _check_times(project, times)
    outdir = Path(a.outdir).resolve() if a.outdir else project.folder / "stills"
    return Renderer(project).render(times, [outdir / still_name(t) for t in times])


def cmd_snapshot(a: argparse.Namespace) -> dict:
    return Project(a.folder).snapshot()


def cmd_install_browser(a: argparse.Namespace) -> dict:
    b = Browser()
    b.install()
    return {"browsers": str(b.root), "executable": str(b.executable())}


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="html-animation", description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create an animation folder, or refresh player.js and add libraries")
    p.add_argument("folder")
    p.add_argument("--lib", required=True, choices=[v.value for v in TimingLib])
    p.add_argument("--size", default=Size.WIDE.value, choices=[v.value for v in Size])
    p.add_argument("--title")
    p.add_argument("--with", dest="with_libs", metavar="d3,three", help="extra libraries: d3, three")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("add-chapter", help="append a chapter with an empty html and a stub script")
    p.add_argument("folder")
    p.add_argument("id")
    p.add_argument("--duration", required=True, type=float, help="seconds")
    p.add_argument("--title")
    p.set_defaults(func=cmd_add_chapter)

    p = sub.add_parser("build", help="write index.html")
    p.add_argument("folder")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("validate", help="check the format, determinism, ids and content keys")
    p.add_argument("folder")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("still", help="PNG of the frame at --at seconds, with an optional mark")
    p.add_argument("folder")
    p.add_argument("--at", required=True)
    p.add_argument("--mark", help="point:X,Y or rect:X,Y,W,H in stage pixels")
    p.add_argument("--out")
    p.set_defaults(func=cmd_still)

    p = sub.add_parser("stills", help="PNGs at several times in one browser session")
    p.add_argument("folder")
    p.add_argument("--at", required=True, help="T1,T2,...")
    p.add_argument("--outdir")
    p.set_defaults(func=cmd_stills)

    p = sub.add_parser("snapshot", help="copy the content into the next v<N>/")
    p.add_argument("folder")
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("install-browser", help="install headless Chromium (still does it on first use)")
    p.set_defaults(func=cmd_install_browser)
    return ap


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    Plugin.of(__file__).load()
    try:
        result = args.func(args)
    except HAError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.command == "validate" and not result["ok"]:
        sys.exit(1)
