"""The model of each image-gen tier and of the media tasks the page shows, from `tasks` in config.yaml, and the
speech models the voice picker offers.

A model id is `<provider>:<model>`. Nothing here calls a model.
"""

from __future__ import annotations

from plugin_settings import ConfigFileError, load_config

from .paths import log

# Each image-gen tier (`--tier`, in the order the page lists them): its task without and with reference images.
TIERS = {"best": ("image_best", "image_best"), "multi-ref": ("image_multi_ref", "image_multi_ref"),
         "fast": ("image", "image_edit")}
# The image tasks, then the tasks the Videos tab names: the voice, made music, the `video` scene engine.
TASKS = ("image", "image_edit", "image_best", "image_multi_ref", "speech", "music", "video", "presenter")


def speech_models() -> tuple[list[dict], str | None]:
    """The speech models of media:voiceover's routes (`ai_models.routes`, task `speech`): the default row (the
    `speech` model of config.yaml) first, then the configured escalation rows, each once. Each: `id`, `default`
    (the default row), `when`, `why`, and what the model takes (`ai_models.speech`): `voice` (its default voice),
    `speed` ([low, high], or null for none), `style` and `clones` (a voice may be a reference recording); with the
    error that left the list empty (config.yaml or routes.md missing or malformed), else None. A row whose provider
    has no speech models is left out."""
    from ai_models import AIModelsError, routes, speech

    try:
        rows = routes.table(["speech"])
    except AIModelsError as e:
        return [], str(e)
    out: list[dict] = []
    for r in rows:
        if any(m["id"] == r.model for m in out):
            continue
        try:
            m = speech.model_of(r.model)
        except AIModelsError:
            continue
        rng = m.traits.speed
        out.append({"id": m.id, "default": r.is_default, "when": r.when, "why": r.why, "voice": m.default_voice,
                    "speed": list(rng) if rng else None, "style": m.instructions, "clones": m.traits.clones})
    return out, None


def read_models() -> dict:
    """`tasks`: the model id of each task of TASKS (None without one, or when config.yaml is missing or broken);
    `tiers`: each tier's `id`, `model` (without reference images) and `ref_model` (with them); `speech` and
    `speech_error`: the speech models of `speech_models` and its error; `error`: why config.yaml was not read, else
    None (the error is also logged, so the server keeps running)."""
    error = None
    try:
        configured = load_config().tasks
    except ConfigFileError as e:
        error = str(e)
        log(f"tasks not read: {e}")
        configured = {}
    tasks = {t: configured.get(t) for t in TASKS}
    speech, speech_error = speech_models()
    return {"tasks": tasks,
            "tiers": [{"id": tier, "model": tasks[task], "ref_model": tasks[ref]} for tier, (task, ref) in TIERS.items()],
            "speech": speech, "speech_error": speech_error, "error": error}
