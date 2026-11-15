"""The model of each image-gen tier and of the media tasks the page shows, from `models` in config.yaml.

A model id is `<provider>:<model>`. Nothing here calls a model.
"""

from __future__ import annotations

from plugin_settings import ConfigFileError, read_config

# Each image-gen tier (`--tier`, in the order the page lists them): its task without and with reference images.
TIERS = {"best": ("image_best", "image_best"), "multi-ref": ("image_multi_ref", "image_multi_ref"),
         "fast": ("image", "image_edit")}
# The image tasks, then the tasks the Videos tab names: the online voice, made music, the `video` scene engine.
TASKS = ("image", "image_edit", "image_best", "image_multi_ref", "speech", "music", "video", "presenter")


def read_models() -> dict:
    """`tasks`: the model id of each task of TASKS (None without one, or when config.yaml is missing or broken);
    `tiers`: each tier's `id`, `model` (without reference images) and `ref_model` (with them)."""
    try:
        models = read_config().get("models") or {}
    except ConfigFileError:
        models = {}
    tasks = {t: models.get(t) or None for t in TASKS}
    return {"tasks": tasks,
            "tiers": [{"id": tier, "model": tasks[task], "ref_model": tasks[ref]} for tier, (task, ref) in TIERS.items()]}
