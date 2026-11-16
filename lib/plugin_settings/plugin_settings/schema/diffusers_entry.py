"""`DiffusersEntry`: a diffusers model entry, validated as the class of its role. The role is read from the keys
the entry has (`role_of`): a key only presenter models have makes it a presenter, then a key only video models
have (or `pipeline`, `fps`) a video model, then a music key a music model, else an image model. The class of
that role then refuses a key of another role and names each missing required key."""

from __future__ import annotations

from typing import Annotated, Any, Union

from pydantic import Discriminator, Tag

from .diffusers_image_model import DiffusersImageModel
from .diffusers_model import DiffusersModel
from .diffusers_music_model import DiffusersMusicModel
from .diffusers_presenter_model import DiffusersPresenterModel
from .diffusers_role import DiffusersRole
from .diffusers_video_model import DiffusersVideoModel

# The class of each role.
ROLE_CLASSES: dict[DiffusersRole, type[DiffusersModel]] = {
    c.role: c for c in (DiffusersImageModel, DiffusersMusicModel, DiffusersVideoModel, DiffusersPresenterModel)}


def _own_keys(role: DiffusersRole) -> frozenset[str]:
    """The keys of `role`'s class that no other role's class has."""
    others = set().union(*(c.model_fields for r, c in ROLE_CLASSES.items() if r != role))
    return frozenset(ROLE_CLASSES[role].model_fields) - others


# Role by keys, checked in this order; `pipeline` and `fps` (video and presenter) count as video.
_ROLE_KEYS = ((DiffusersRole.PRESENTER, _own_keys(DiffusersRole.PRESENTER)),
              (DiffusersRole.VIDEO, _own_keys(DiffusersRole.VIDEO) | {"pipeline", "fps"}),
              (DiffusersRole.MUSIC, _own_keys(DiffusersRole.MUSIC)))


def role_of(entry: Any) -> str:
    """The role of a raw entry (a mapping) or of a validated one."""
    if isinstance(entry, DiffusersModel):
        return entry.role.value
    keys = set(entry) if isinstance(entry, dict) else set()
    return next((r.value for r, own in _ROLE_KEYS if keys & own), DiffusersRole.IMAGE.value)


DiffusersEntry = Annotated[Union[tuple(Annotated[c, Tag(r.value)] for r, c in ROLE_CLASSES.items())],
                           Discriminator(role_of)]
