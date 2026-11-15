# Agent Skills marketplace

A Claude Code marketplace, `pcingola-skills`, of Agent Skills grouped into the plugins below, most with CLI tools. Installed, a skill loads as `<plugin>:<skill>`. Installing a plugin also installs the plugins it depends on.

| Plugin | Skills | Depends on |
| --- | --- | --- |
| docs | pptx, revealjs-slideshow | brand, setup |
| media | html-animation, image-gen, infographic, music, pptx-author, short-video, video-effects, voiceover | ai, brand, docs, setup |
| dev | plan, skill-author | setup |
| brand | brand, style | setup |
| ai | classify, second-opinion | setup |
| studio | images, videos | brand, media, setup |
| setup | settings | |

## Install and update

```
claude plugin marketplace add pcingola/pcingola-skills
claude plugin install docs@pcingola-skills --scope user
claude plugin install media@pcingola-skills --scope user
claude plugin install dev@pcingola-skills --scope user
claude plugin install brand@pcingola-skills --scope user
claude plugin install ai@pcingola-skills --scope user
claude plugin install studio@pcingola-skills --scope user
claude plugin install setup@pcingola-skills --scope user
```

Added from a local path, the marketplace is a directory source: Claude Code reads each installed plugin in place from `plugins/<plugin>/`, and working-tree edits, uncommitted ones included, take effect at the next session start or `/reload-plugins`. Install and update also write a copy to `~/.claude/plugins/cache/pcingola-skills/<plugin>/<HEAD sha>/`, which is not loaded. The version label is the HEAD commit; after a commit these commands refresh the label and that copy:

```
claude plugin marketplace update pcingola-skills
claude plugin update docs@pcingola-skills
claude plugin update media@pcingola-skills
claude plugin update dev@pcingola-skills
claude plugin update brand@pcingola-skills
claude plugin update ai@pcingola-skills
claude plugin update studio@pcingola-skills
claude plugin update setup@pcingola-skills
```

The CLI tools need `uv` on `PATH`. uv builds each skill's environment on first use and fetches the shared packages in `lib/` from the repository's git origin, which needs git read access to it.

## Uninstall

`claude plugin uninstall` deletes the plugin's data directory unless `--keep-data` is passed. That directory holds the plugin's environments. The media data directory also holds the voiceover weights, the cloned voices, the image-gen and music environments (with torch and diffusers when `config.yaml` has a `diffusers` provider), and html-animation's pinned JavaScript libraries and headless Chromium.

The settings file `config.yaml` and the weights of local `diffusers` models (Hugging Face cache, `HF_HOME`, default `~/.cache/huggingface`) are outside every plugin data directory, so an uninstall keeps them.

Reinstall a plugin without losing them:

```
claude plugin uninstall <plugin>@pcingola-skills --keep-data
claude plugin install <plugin>@pcingola-skills --scope user
```

## Models

The skills that call a model (classify, second-opinion, image-gen, music, voiceover) go through the shared package `lib/ai_models`, built on Pydantic-AI. One YAML file holds every setting: `~/.claude/plugins/data/config.yaml` (`SKILLS_CONFIG` names another file). Its sections are `providers` (with each provider's key in `api_key`), `models` (the model of each task), `diffusers` (local models) and `settings` (every other setting). The `setup:settings` skill creates it from `plugins/setup/skills/settings/assets/config.example.yaml`. A model id is `<provider name>:<model>`, for example `ollama:d3:4b`.

Provider kinds: `ollama`, `openrouter`, `openai` (any OpenAI-compatible server), `azure`, `google` (Gemini API or Vertex) and `diffusers` (local models in process). Tasks: `chat`, `vision`, `system1`, `image`, `image_edit`, `speech`, `music`, `audio`. The `setup:settings` skill documents the file, every kind and every task.

Three levels of setup, each adding to the one before:

1. API only: a key of OpenRouter, of Azure OpenAI and Vertex AI, or of a company (enterprise) gateway that serves them (kinds `azure` and `google`). No GPU.
2. Ollama: System-1 models, small chat models and speech (macOS) on a local Ollama server. No key.
3. GPU: a `diffusers` provider for local images and music. The image-gen and music wrappers then install torch and diffusers. It needs an NVIDIA GPU with driver 580 or later (CUDA 13.0 wheels of PyTorch) or Apple Silicon.

## Requirements

- macOS or Linux.
- `uv` and `git` on `PATH`.
- FFmpeg for the audio and video skills (music, short-video, video-effects, and large video input of second-opinion).
- LibreOffice and Poppler (`pdftoppm`) for the pptx previews and PDF export.
- Ollama for local chat and System-1 models.

## First use

With an OpenRouter key only:

1. Ask Claude to set up the skills; the `setup:settings` skill writes `~/.claude/plugins/data/config.yaml`. By hand: copy `plugins/setup/skills/settings/assets/config.example.yaml` there and `chmod 600` it.
2. Keep an `openrouter` provider (`kind: openrouter`, `api_key: <key>`) and point each task you use at an OpenRouter model.

With no key:

1. Install Ollama and pull the models the config names with `ollama pull <tag>`. A skill that finds a model not pulled names the command.
2. For images and music, add a `diffusers` provider and its models to the config (see the example). The first run downloads the weights.

## Settings and documentation

The settings file, every setting and the settings errors are documented in the `setup:settings` skill; `plugins/setup/skills/settings/assets/config.example.yaml` lists every setting with placeholder values. Maintainer documentation is in `docs/`, with the repository rules in `docs/architecture.md`.
