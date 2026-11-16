"""The provider kinds each task takes (`TASK_KINDS`) and the diffusers role a task needs (`TASK_ROLES`); checked
for every `tasks.<task>` at load and for a model a caller names for a task (`Config.task_error`)."""

from __future__ import annotations

from .diffusers_role import DiffusersRole
from .provider_kind import API_KINDS, OPENAI_KINDS, SPEECH_KINDS, ProviderKind
from .task import Task

_IMAGE_KINDS = OPENAI_KINDS | {ProviderKind.GOOGLE, ProviderKind.DIFFUSERS}
_IMAGE_TASKS = (Task.IMAGE, Task.IMAGE_EDIT, Task.IMAGE_BEST, Task.IMAGE_MULTI_REF)

TASK_KINDS: dict[Task, frozenset[ProviderKind]] = {
    Task.CHAT: API_KINDS,
    Task.VISION: API_KINDS,
    Task.SYSTEM1: API_KINDS,
    Task.EMBED: API_KINDS,
    **{t: _IMAGE_KINDS for t in _IMAGE_TASKS},
    Task.SPEECH: SPEECH_KINDS,
    Task.ALIGN: frozenset({ProviderKind.TORCHAUDIO}),
    Task.MUSIC: frozenset({ProviderKind.GOOGLE, ProviderKind.DIFFUSERS}),
    Task.AUDIO: API_KINDS,
    Task.VIDEO: frozenset({ProviderKind.DIFFUSERS}),
    Task.PRESENTER: frozenset({ProviderKind.DIFFUSERS}),
    Task.FILM_CRITIC: API_KINDS,
}

TASK_ROLES: dict[Task, DiffusersRole] = {
    **{t: DiffusersRole.IMAGE for t in _IMAGE_TASKS},
    Task.MUSIC: DiffusersRole.MUSIC,
    Task.VIDEO: DiffusersRole.VIDEO,
    Task.PRESENTER: DiffusersRole.PRESENTER,
}
