"""A provider of kind diffusers: local models in process; each model needs an entry in `models`."""

from __future__ import annotations

from typing import Literal

from ..base import Strict
from ..diffusers_entry import DiffusersEntry
from ..fields import Catalogue


class DiffusersProvider(Strict):
    kind: Literal["diffusers"]
    models: Catalogue[DiffusersEntry] = {}
