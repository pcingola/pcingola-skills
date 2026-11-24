"""The review by the Codex CLI, selected by `second_opinion.codex` of `config.yaml` when no `--model` is given.

`codex exec` runs as an agent in the working directory with a read-only sandbox, so it reads the files under
review itself, and any other file or command output it needs. The prompt is the fixed instructions
(`review.INSTRUCTIONS` without the boundary paragraph, plus `AGENT_INSTRUCTIONS`), the brief and the absolute path
of each file; images are also attached with `--image`. The answer is the final message, constrained by
`--output-schema` to `review.SCHEMA` and checked by `review.check_answer`. Codex uses its own login and model
(`~/.codex/config.toml`). A missing `codex`, a failed run or an answer that does not match the schema raises
ReviewError.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import review
from .files import ReviewFile

MODEL_NAME = "codex"
TIMEOUT_SECONDS = 1800

AGENT_INSTRUCTIONS = """You run as a reviewer in a read-only sandbox. Read the files under review yourself. You may read any other file and run read-only commands when they help you check the brief: related source files, git history, tools that extract text from a PDF or frames from a video. Do not change any file.

Your final message is the findings JSON, nothing else."""


def instructions() -> str:
    """`review.INSTRUCTIONS` without its paragraph on boundary lines (Codex reads the files itself), then
    AGENT_INSTRUCTIONS."""
    paragraphs = [p for p in review.INSTRUCTIONS.split("\n\n") if "BOUNDARY" not in p]
    return "\n\n".join([*paragraphs, AGENT_INSTRUCTIONS])


@dataclass
class CodexReviewer:
    """One review by `codex exec` started in `cwd`; `executable` is the path of `codex`."""

    executable: str
    cwd: Path

    @classmethod
    def find(cls, cwd: Path, path: str | None = None) -> CodexReviewer:
        """The reviewer with `codex` from `path` (default: PATH); ReviewError when it is not there."""
        exe = shutil.which("codex", path=path)
        if exe is None:
            raise review.ReviewError("second_opinion.codex is true in config.yaml and codex is not on PATH; "
                                     "install the Codex CLI or pass --model")
        return cls(exe, cwd)

    def prompt(self, brief: str, files: list[ReviewFile]) -> str:
        """The instructions, the brief and the files under review by absolute path, kind and MIME type."""
        listing = "\n".join(f"- {Path(f.path).resolve()} ({f.kind}, {f.mime})" for f in files)
        return f"{instructions()}\n\nBrief:\n{brief.strip()}\n\nFiles under review:\n{listing}\n"

    def command(self, files: list[ReviewFile], schema: Path, answer: Path) -> list[str]:
        """The `codex exec` command line; the prompt goes on stdin (`-`)."""
        images = [a for f in files if f.kind == "image" for a in ("--image", str(Path(f.path).resolve()))]
        return [self.executable, "exec", "--sandbox", "read-only", "--ephemeral", "--skip-git-repo-check",
                "--color", "never", "--cd", str(self.cwd), "--output-schema", str(schema),
                "--output-last-message", str(answer), *images, "-"]

    def review(self, brief: str, files: list[ReviewFile]) -> dict:
        """Run Codex on the brief and files; the checked findings (`summary`, `findings`)."""
        with tempfile.TemporaryDirectory(prefix="second-opinion-codex-") as tmp:
            schema, answer = Path(tmp) / "schema.json", Path(tmp) / "answer.json"
            schema.write_text(json.dumps(review.SCHEMA), encoding="utf-8")
            try:
                proc = subprocess.run(self.command(files, schema, answer), input=self.prompt(brief, files),
                                      capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                raise review.ReviewError(f"codex did not finish the review in {TIMEOUT_SECONDS} s") from None
            if proc.returncode != 0:
                tail = (proc.stderr or proc.stdout).strip()[-500:]
                raise review.ReviewError(f"codex exited with {proc.returncode}: {tail}")
            text = answer.read_text(encoding="utf-8") if answer.is_file() else ""
        return parse_answer(text)


def parse_answer(text: str) -> dict:
    """The findings of Codex's final message, checked by `review.check_answer`; ReviewError otherwise."""
    try:
        return review.check_answer(json.loads(text))
    except (ValueError, AttributeError) as e:
        raise review.ReviewError(f"codex answer is not the findings JSON ({e}): {text.strip()[:300]!r}") from None
