"""Models for the skills, set per task in `config.yaml` (`config`), reached through Pydantic-AI.

    config   the config file, `provider:model` ids, `model_for(task)`
    routes   the model routes table (the user's `routes.md` beside the config file); the `routes` CLI command
    models   Pydantic-AI providers per kind; `chat_model`, `agent`, `embedder`
    images   `image_generator` (generation, edits with reference images, masks)
    system1  `system1_model`, `decide`
    speech   `speak` (OpenAI-style `audio/speech`, Gemini TTS, vLLM-Omni)
    omni     the vLLM-Omni server of a `vllm-omni` provider, one per process
    music    `compose` (Google predict and stream models, local diffusers)
    video    `animate`, `aanimate` (image to video), `present`, `apresent` (portrait and speech to video), local diffusers
    local    diffusers image, music, video and presenter models (extra `ai-models[diffusers]`)
    tls      certifi roots plus EXTRA_CA_CERT for remote clients

Every error of this package is an `AIModelsError`.
"""

import os

from .errors import AIModelsError, ConfigError

# Pydantic-AI prints a banner on the first agent run; the skills' output is read by programs.
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

__all__ = ["AIModelsError", "ConfigError"]
