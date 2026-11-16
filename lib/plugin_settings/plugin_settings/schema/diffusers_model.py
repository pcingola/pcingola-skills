"""`providers.<p>.models.<m>` of a diffusers provider: a local model, loaded in process. `DiffusersModel` holds the
keys of every role; the subclass of each role (`DiffusersRole`) adds its own, and `DiffusersEntry` picks the role
from the keys an entry has (`role_of`), so a key of another role is an error at load."""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import PositiveInt

from .base import Strict
from .diffusers_role import DiffusersRole


class DiffusersModel(Strict):
    """`repo` (Hugging Face repository), `steps`, `guidance` (none: no `guidance_scale`), `args` (more call
    arguments, after steps and guidance), `skip` (components loaded as None)."""

    role: ClassVar[DiffusersRole]

    repo: str
    steps: PositiveInt | None = None
    guidance: float | None = None
    args: dict[str, Any] = {}
    skip: list[str] = []
