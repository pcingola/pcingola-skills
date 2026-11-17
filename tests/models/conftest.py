"""Tests of full-size models, run only by `scripts/tests.sh models`; their models are in tests/models/config.yaml.
Each test sets its own timeout, above the default 30 s.

`models_config` writes the settings file of one test. tests/models/config.yaml has no api_key, so it is not a valid
settings file by itself when it names a remote provider."""

from pathlib import Path

import yaml
from plugin_settings import LOCAL_KINDS, config_dir

from tests.prereq import require
from tests.settings_env import MODELS_CONFIG, config_sections, write_config

# The fields of a remote provider that come from the user's config: the key and the user's endpoint.
USER_FIELDS = ("api_key", "base_url", "api_version")
# The fields that make two providers of the user's config and of MODELS_CONFIG the same kind.
SAME_KIND = ("kind", "vertex")


def models_config(path: Path, model_id: str) -> Path:
    """Write at `path` the settings of MODELS_CONFIG with only the provider of `model_id`; for a remote provider,
    add the USER_FIELDS of the provider of the same kind in the user's config
    (`<config dir>/plugins/data/config.yaml`). Fail the test when the user's config has no such provider with an
    api_key. Return `path`."""
    sections = config_sections(MODELS_CONFIG)
    name = model_id.split(":", 1)[0]
    spec = sections["providers"][name]
    if spec["kind"] not in LOCAL_KINDS:
        user_file = config_dir() / "plugins" / "data" / "config.yaml"
        user = yaml.safe_load(user_file.read_text(encoding="utf-8")) if user_file.is_file() else {}
        same = [p for p in ((user or {}).get("providers") or {}).values()
                if all(p.get(k) == spec.get(k) for k in SAME_KIND) and p.get("api_key")]
        kind = ", ".join(f"{k}: {spec[k]}" for k in SAME_KIND if k in spec)
        require(same, f"a provider ({kind}) with an api_key in {user_file}")
        spec = {**spec, **{k: same[0][k] for k in USER_FIELDS if k in same[0]}}
    return write_config(path, **{**sections, "providers": {name: spec}})
