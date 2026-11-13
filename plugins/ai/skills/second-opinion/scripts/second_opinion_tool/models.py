"""The review model: `--model` (a `<provider>:<model>` id of `config.yaml` of `ai_models`),
else the model of task `vision` when an image is among the files, else of task `chat`.
Which inputs a model takes is the provider's to decide; a refused input fails the request."""

from __future__ import annotations

from ai_models import config

CHAT = "chat"
VISION = "vision"


def task(kinds) -> str:
    """VISION when "image" is among the file kinds, else CHAT."""
    return VISION if "image" in kinds else CHAT


def resolve(model: str | None, kinds) -> str:
    """`model`, else the model id of `task(kinds)`."""
    return config.resolve(model, task(kinds))


def describe() -> str:
    m = config.load().get("models") or {}
    return (f"Config: {config.path()}\n"
            f"chat    {m.get(CHAT, '(not set)')}  (default)\n"
            f"vision  {m.get(VISION, '(not set)')}  (when an image is among the files)\n"
            "--model takes any <provider>:<model> id of the config.")
