"""second-opinion CLI: `review`, `models` and `routes` (the model routes of the chat and vision tasks).

Settings are loaded by `plugin_settings` (`Plugin.load`), which documents the sources.
The models, the providers and their keys are in `config.yaml`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_models import AIModelsError, routes
from plugin_settings import Plugin, config, error, exit_code

PLUGIN = Plugin.of(__file__)


def load_settings() -> None:
    """Load the settings and export them to the process environment (`Plugin.load`); exit when the file is not
    valid. The wrapper path (`__main__`) only: an in-process `main(argv)` calls `check_settings` and leaves
    `os.environ` unchanged."""
    PLUGIN.load()


def check_settings() -> None:
    """Exit when the settings file is not valid (`config()`). Leaves the process environment unchanged."""
    config()


from . import files as files_mod
from . import models, review

# The review takes the vision model when an image is among the files, else the chat model.
ROUTE_TASKS = ("chat", "vision")


def cmd_review(args: argparse.Namespace) -> None:
    brief = args.brief if args.brief is not None else _read_brief(args.brief_file)
    if not brief.strip():
        error("the brief is empty")
    if args.out and Path(args.out).exists() and not args.force:
        error(f"{args.out} exists; pass --force to replace it")
    try:
        result = run_review(brief, args.file, args.model, Path(args.out) if args.out else None)
    except (files_mod.FileError, review.ReviewError, AIModelsError) as e:
        error(str(e))
    print(review.markdown(result), end="")


def run_review(brief: str, paths: list[str], model: str | None = None, out: Path | None = None) -> dict:
    """Review the files at `paths` against `brief` with `model` (default: `models.resolve` by the file kinds); the
    result (model, files, brief, summary, findings), also written as JSON to `out` when given. Raises
    `files.FileError`, `review.ReviewError` or `AIModelsError`."""
    inputs = files_mod.load_all(paths)
    model_id = models.resolve(model, {f.kind for f in inputs})
    answer = review.review(model_id, brief, inputs)
    result = {"model": model_id, "files": [f.record() for f in inputs], "brief": brief, **answer}
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def _read_brief(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as e:
        error(f"cannot read the brief {path}: {e.strerror or e}")
    except UnicodeDecodeError as e:
        error(f"the brief {path} is not valid UTF-8 (byte {e.start})")


def cmd_models(args: argparse.Namespace) -> None:
    try:
        print(models.describe())
    except AIModelsError as e:
        error(str(e))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="second-opinion",
        description="Review of files against a brief by a model other than Claude, set in config.yaml "
                    "of ai_models.")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("review", help="review files against a brief; prints Markdown findings")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--brief", help="the brief: criteria or checklist to review against")
    g.add_argument("--brief-file", help="file holding the brief")
    r.add_argument("--file", action="append", required=True, metavar="PATH",
                   help="file to review (repeat for several): text, PNG, JPEG, WebP, WAV, MP3, FLAC, MP4, MOV, PDF")
    r.add_argument("--model", help="review model <provider>:<model> (default: tasks.vision of config.yaml "
                                   "when an image is among the files, else tasks.chat)")
    r.add_argument("--out", help="write the findings JSON (model, files, brief, summary, findings) here")
    r.add_argument("--force", action="store_true", help="replace an existing --out file")
    r.set_defaults(func=cmd_review)

    m = sub.add_parser("models", help="show the review models of config.yaml")
    m.set_defaults(func=cmd_models)

    routes.command(sub, ROUTE_TASKS)
    return p


def main(argv: list[str] | None = None) -> int:
    """Run the command in `argv` (default: `sys.argv[1:]`) and return its exit code; `--help`, argument errors and
    command errors (`error`: `Error: <msg>` on stderr, exit 1) return their code. Checks the settings
    (`check_settings`) and leaves `os.environ` unchanged: the wrapper path (`__main__`) exports the settings to the
    environment before it calls `main`."""
    try:
        check_settings()
        args = build_parser().parse_args(argv)
        return args.func(args) or 0
    except SystemExit as e:
        return exit_code(e)
