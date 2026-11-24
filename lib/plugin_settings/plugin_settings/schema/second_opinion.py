"""`second_opinion:`: settings of ai:second-opinion."""

from __future__ import annotations

from .base import Strict


class SecondOpinionSettings(Strict):
    """`codex`: review with the Codex CLI (`codex exec`) instead of a model of `tasks`, when no `--model` is given;
    the review fails when `codex` is not on PATH."""

    codex: bool = False
