"""Models for the skills, set per task in `config.yaml` (`config`), reached through Pydantic-AI.

    config   the typed config file (`plugin_settings.Config`), `provider:model` ids, `model_for(task)`,
             `model_entry`, `diffusers_model`, `image_limits`
    routes   the model routes table (the user's `routes.md` beside the config file); the `routes` CLI command
    models   Pydantic-AI providers per kind; `chat_model`, `agent`, `embedder`
    images   `image_generator` (generation, edits with reference images, masks)
    system1  `system1_model`, `decide`
    speech   `speak`, `voices`, `check` (OpenAI-style `audio/speech`, Gemini TTS, Fish, Kokoro, Chatterbox)
    fish     Fish Audio Drama 3 in process on an NVIDIA GPU (fish-speech); `fish_span`, `fish_take`, `fish_takes`
    kokoro   Kokoro in process on the CPU (extra `ai-models[kokoro]`)
    chatterbox  Chatterbox Turbo in process on the CPU (extra `ai-models[chatterbox]`)
    cpu      torch's CPU threads on the fast cores (`performance_threads`)
    align    `aligner` (forced alignment of speech against its text, torchaudio, extra `ai-models[align]`)
    weights  weight files of the kokoro, chatterbox and torchaudio kinds
    music    `compose` (Google predict and stream models, local diffusers)
    video    `animate`, `aanimate` (image to video), `present`, `apresent` (portrait and speech to video), local diffusers
    local    diffusers image, music, video and presenter models (extra `ai-models[diffusers]`)
    tls      certifi roots plus `network.extra_ca_cert` for remote clients

Every error of this package is an `AIModelsError`.
"""

import os

from .errors import AIModelsError, ConfigError

# Pydantic-AI prints a banner on the first agent run; the skills' output is read by programs.
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

__all__ = ["AIModelsError", "ConfigError"]
