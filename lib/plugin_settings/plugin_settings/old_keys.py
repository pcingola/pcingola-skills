"""Keys of the earlier config.yaml layout: each fails at load with its new place.

The layout had the sections `models` (now `tasks`), `diffusers` (now the `models` of the diffusers provider) and
`settings` (upper-case keys, now sections), and the provider keys `predict_models` and `memory_share`. A provider
of kind kokoro, torchaudio, chatterbox or vllm-omni held its one model's keys, and every provider the speech
voices; these are now keys of `providers.<p>.models.<m>` (`MODEL_KEYS`)."""

from __future__ import annotations

from typing import Any

OLD_SECTIONS: dict[str, str] = {
    "models": "renamed to tasks",
    "diffusers": "moved: each entry is providers.<p>.models.<name> of the provider of kind diffusers",
    "settings": "removed: its keys are sections now (network, huggingface, brand, studio, voiceover)",
}

OLD_SETTINGS: dict[str, str] = {
    "IMAGE_GEN_OPENAI_MAX_EDGE": "moved to providers.<p>.models.<m>.image.max_edge of each OpenAI-kind image model",
    "IMAGE_GEN_OPENAI_MIN_PIXELS": "moved to providers.<p>.models.<m>.image.min_pixels of each OpenAI-kind image "
                                   "model",
    "IMAGE_GEN_OPENAI_MAX_PIXELS": "moved to providers.<p>.models.<m>.image.max_pixels of each OpenAI-kind image "
                                   "model",
    "IMAGE_GEN_LOCAL_MAX_EDGE": "moved to providers.<p>.models.<m>.image.max_edge of each diffusers image model",
    "IMAGE_GEN_LOCAL_MIN_EDGE": "moved to providers.<p>.models.<m>.image.min_edge of each diffusers image model",
    "IMAGE_GEN_SIZED_MODELS": "moved: providers.<p>.models.<m>.image.always_sized: true for each listed <p>:<m>",
    "IMAGE_GEN_SIZED_QUALITY": "moved to providers.<p>.models.<m>.image.default_quality of each sized model",
    "BRAND_PATH": "moved to brand.path, a list of directories",
    "STUDIO_DIR": "moved to studio.dir",
    "AUTHOR_NAME": "moved to studio.author, a list of names",
    "VOICEOVER_VOICES_DIR": "moved to voiceover.voices_dir",
    "EXTRA_CA_CERT": "moved to network.extra_ca_cert",
    "NODE_EXTRA_CA_CERTS": "moved to network.extra_ca_cert (one file for Python and Node.js)",
    "HTTP_PROXY": "moved to network.http_proxy",
    "HTTPS_PROXY": "moved to network.https_proxy",
    "ALL_PROXY": "moved to network.all_proxy",
    "NO_PROXY": "moved to network.no_proxy, a list of hosts",
    "SSL_CERT_FILE": "moved to network.ca_bundle",
    "HF_HOME": "moved to huggingface.home",
    "HF_TOKEN": "moved to huggingface.token",
}

# The model settings of an earlier media:voiceover, `VOICEOVER_*` other than VOICEOVER_VOICES_DIR.
VOICEOVER_PREFIX = "VOICEOVER_"
VOICEOVER_MODEL_DIR = "VOICEOVER_MODEL_DIR"
VOICEOVER_OBSOLETE = ("no longer read: the speech and align models are tasks.speech and tasks.align and their "
                      "providers; copy the provider entries kokoro and torchaudio (and chatterbox for cloned voices) "
                      "and tasks.speech and tasks.align of the setup:settings template into config.yaml")
DRAMA3_MEMORY_GB = 70  # the `memory` the config template gives Fish Audio Drama 3

OLD_PROVIDER_KEYS: dict[str, str] = {
    "predict_models": "moved: providers.{p}.models.<m>.predict: true for each listed model",
    "memory_share": ("replaced by memory, the GB the server's stages take together "
                     f"(Fish Audio Drama 3: {DRAMA3_MEMORY_GB})"),
}


# Keys of a model that a provider held in the earlier layout.
MODEL_KEYS = ("model_url", "voices_url", "langs", "url", "files", "repo", "deploy", "memory", "overhead", "style",
              "voice", "voices")
OLD_PROVIDER_KEYS.update({k: f"moved to providers.{{p}}.models.<m>.{k}" for k in MODEL_KEYS})


def _setting_error(key: str, value: Any) -> str:
    if key in OLD_SETTINGS:
        return f"settings.{key}: {OLD_SETTINGS[key]}"
    if key.startswith(VOICEOVER_PREFIX):
        msg = f"settings.{key}: {VOICEOVER_OBSOLETE}"
        if key == VOICEOVER_MODEL_DIR and value:
            msg += f"; to keep the weights in {value}, give those provider entries dir: {value}"
        return msg
    return f"settings.{key}: not a setting"


def old_key_errors(raw: dict[str, Any]) -> list[str]:
    """One line per key of the earlier layout in the parsed file `raw`: its path and its new place."""
    errors = []
    for section, text in OLD_SECTIONS.items():
        if section not in raw:
            continue
        settings = raw[section]
        if section == "settings" and isinstance(settings, dict) and settings:
            errors += [_setting_error(str(k), v) for k, v in settings.items()]
        else:
            errors.append(f"{section}: {text}")
    providers = raw.get("providers")
    if isinstance(providers, dict):
        for name, spec in providers.items():
            if isinstance(spec, dict):
                errors += [f"providers.{name}.{k}: {v.format(p=name)}" for k, v in OLD_PROVIDER_KEYS.items()
                           if k in spec]
    return errors
