"""The review model: `--model` (a `<provider>:<model>` id of `config.yaml`), else Codex when
`second_opinion.codex` is true, else the model of task `vision` when an image is among the files, else of task
`chat`. Which inputs a model takes is the provider's to decide; a refused input fails the request."""

from __future__ import annotations

from ai_models import config
from plugin_settings import config as settings

from .codex import MODEL_NAME as CODEX

CHAT = "chat"
VISION = "vision"


def uses_codex(model: str | None) -> bool:
    """True when no `model` is given and `second_opinion.codex` is true in config.yaml."""
    return model is None and settings().second_opinion.codex


def task(kinds) -> str:
    """VISION when "image" is among the file kinds, else CHAT."""
    return VISION if "image" in kinds else CHAT


def resolve(model: str | None, kinds) -> str:
    """`model`, else the model id of `task(kinds)`."""
    return config.resolve(model, task(kinds))


def describe() -> str:
    cfg = config.load()
    return (f"Config: {config.path()}\n"
            f"chat    {cfg.task_model(CHAT) or '(not set)'}  (default)\n"
            f"vision  {cfg.task_model(VISION) or '(not set)'}  (when an image is among the files)\n"
            f"codex   {'on: Codex reviews when no --model is given' if uses_codex(None) else 'off'}"
            "  (second_opinion.codex)\n"
            "--model takes any <provider>:<model> id of the config.")
