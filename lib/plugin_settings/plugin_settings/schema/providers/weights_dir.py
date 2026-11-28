"""A local provider that downloads its models' weight files to a directory of its own."""

from __future__ import annotations

from pathlib import Path
from typing import Self

from ..fields import UserPath
from .local import LocalProvider


class WeightsDir(LocalProvider):
    """`dir`: the weights directory; a model's files go to `<dir>/<model lowercased>/`. None: the caller's
    default (`with_dir`)."""

    dir: UserPath | None = None

    def with_dir(self, default: str | Path | None) -> Self:
        """This provider with `dir` set to `default` when it has none (a copy; this one is unchanged)."""
        if self.dir is not None or default is None:
            return self
        return self.model_copy(update={"dir": Path(default).expanduser()})
