# Agent Skills marketplace

A Claude Code marketplace, `pcingola-skills`, of Agent Skills grouped into the plugins below, most with CLI tools. Installed, a skill loads as `<plugin>:<skill>`. Installing a plugin also installs the plugins it depends on.

| Plugin | Skills | Depends on |
| --- | --- | --- |
| docs | pptx, revealjs-slideshow | brand, setup |
| media | image-gen, infographic, music, pptx-author, short-video, video-effects, voiceover | ai, brand, docs, setup |
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

Inside a Claude Code session the same commands are `/plugin marketplace add pcingola/pcingola-skills` and `/plugin install <plugin>@pcingola-skills`. Installing `studio` alone also installs every other plugin except `dev`.

Added from GitHub, each installed plugin loads from a copy in `~/.claude/plugins/cache/pcingola-skills/<plugin>/<commit>/`. Added from a local clone (`claude plugin marketplace add /path/to/pcingola-skills`), the marketplace is a directory source: Claude Code reads each installed plugin in place from `plugins/<plugin>/`, and working-tree edits, uncommitted ones included, take effect at the next session start or `/reload-plugins`; the cache copy is then written but not loaded. The version label is the commit. These commands fetch the latest commit and refresh the installed plugins:

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

The CLI tools need `uv` on `PATH`. uv builds each skill's environment on first use (a few seconds for most skills; minutes and several GB for the skills that install PyTorch) and fetches the shared packages in `lib/` from `https://github.com/pcingola/pcingola-skills` (branch `main`), which needs `git` and network access to GitHub, no credentials. uv downloads Python 3.11 or later when the system has none.

## Uninstall

`claude plugin uninstall` deletes the plugin's data directory unless `--keep-data` is passed. That directory holds the plugin's environments. The media data directory also holds the voiceover weights, the cloned voices, and the image-gen and music environments (with torch and diffusers when `config.yaml` has a `diffusers` provider).

The settings file `config.yaml` and the weights of local `diffusers` models (Hugging Face cache, `huggingface.home` of `config.yaml`, default `~/.cache/huggingface`) are outside every plugin data directory, so an uninstall keeps them.

Reinstall a plugin without losing them:

```
claude plugin uninstall <plugin>@pcingola-skills --keep-data
claude plugin install <plugin>@pcingola-skills --scope user
```

## Models

The skills that call a model (classify, second-opinion, image-gen, music, voiceover, short-video) go through the shared package `lib/ai_models`, built on Pydantic-AI. One YAML file holds every setting: `~/.claude/plugins/data/config.yaml` (`SKILLS_CONFIG` names another file). Its sections are `providers` (each provider's key in `api_key`, and the attributes of its models in `models`, including the local `diffusers` models), `tasks` (the model of each task), `network` (proxies, CA files), `huggingface`, `brand`, `studio` and `voiceover`. The file is validated at load; an error names the YAML path of each wrong key. The `setup:settings` skill creates it from `plugins/setup/skills/settings/assets/config.example.yaml`. A model id is `<provider name>:<model>`, for example `ollama:d3:4b`.

Provider kinds: `ollama`, `openrouter`, `openai` (any OpenAI-compatible server), `azure`, `google` (Gemini API or Vertex), `diffusers` (local models in process), `kokoro` and `chatterbox` (local speech on the CPU), `torchaudio` (word alignment on the CPU) and `vllm-omni` (local speech on a GPU). Tasks: `chat`, `vision`, `system1`, `embed`, `image`, `image_edit`, `image_best`, `image_multi_ref`, `speech`, `align`, `music`, `audio`, `video`, `presenter`, `film_critic`. The `setup:settings` skill documents the file, every kind and every task.

Three levels of setup, each adding to the one before:

1. API only: a key of OpenRouter, of Azure OpenAI and Vertex AI, or of a company (enterprise) gateway that serves them (kinds `azure` and `google`). No GPU.
2. Ollama: System-1 models, small chat models and speech (macOS) on a local Ollama server. No key.
3. GPU: a `diffusers` provider for local images and music. The image-gen, music and short-video wrappers then install torch and diffusers. It needs an NVIDIA GPU with driver 580 or later (CUDA 13.0 wheels of PyTorch) or Apple Silicon.

## Requirements

- Linux, or macOS on Apple Silicon (PyTorch, which voiceover always installs, has no wheels for Intel Macs).
- `uv` and `git` on `PATH`.
- FFmpeg for the audio and video skills (music, short-video, video-effects, voiceover recordings, and large video input of second-opinion).
- LibreOffice and Poppler (`pdftoppm`) for the pptx previews and PDF export. macOS: `brew install libreoffice poppler`. Linux: `apt-get install libreoffice poppler-utils`.
- Node.js 22 or later with `npm` for short-video HTML scenes. Its first render runs `npm ci` and downloads a headless Chrome through HyperFrames.
- For short-video Manim scenes, Manim's system libraries (on Linux the Cairo and Pango development packages, `pkg-config` and a C compiler), and LaTeX with `dvisvgm` for formulas.
- Ollama for local chat, vision and System-1 models.
- On Linux, voiceover installs the CPU build of PyTorch (about 200 MB), or the CUDA 13.0 build (about 2.7 GB) when `config.yaml` has a `vllm-omni` provider.
- An NVIDIA GPU or Apple Silicon only for the local `diffusers` models (level 3 above).

## First use

With an OpenRouter key only:

1. Ask Claude to set up the skills; the `setup:settings` skill asks for the level and the keys and writes `~/.claude/plugins/data/config.yaml`.
2. By hand, a minimal file for this level (`chmod 600` it):

<!-- minimal-config -->
```yaml
providers:
  openrouter:
    kind: openrouter
    api_key: sk-or-v1-replace-me
    models:
      google/gemini-3-pro-image:
        image: {max_edge: 3840, min_pixels: 655360, max_pixels: 8294400}
  kokoro:
    kind: kokoro
    models:
      kokoro-v1.0:
        model_url: https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
        voices_url: https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
        langs: {af_: en-us, am_: en-us, bf_: en-gb, bm_: en-gb}
        voice: af_heart
  torchaudio:
    kind: torchaudio
    models:
      MMS_FA: {url: https://dl.fbaipublicfiles.com/mms/torchaudio/ctc_alignment_mling_uroman/model.pt}
tasks:
  chat: openrouter:google/gemini-3.1-pro-preview
  vision: openrouter:google/gemini-3.1-pro-preview
  image: openrouter:google/gemini-3-pro-image
  image_best: openrouter:google/gemini-3-pro-image
  speech: kokoro:kokoro-v1.0
  align: torchaudio:MMS_FA
```

The `image` entry gives image-gen the size limits of the model for `--size`. Kokoro speech and the torchaudio aligner run on the CPU with no key; their first use downloads about 1.6 GB. OpenRouter serves no image edits (`POST /images/edits` returns 404), so `image_edit`, `image_multi_ref` and every image-gen call with `--ref` need a provider of kind `azure`, `google` or `openai` (a server with image edits), or level 3. Music needs a provider of kind `google` (Lyria) or level 3. Copied unchanged, `config.example.yaml` is a level 3 file: its `local` provider of kind `diffusers` makes the image-gen, music and short-video wrappers install PyTorch and diffusers, and several of its tasks name local GPU models.

With no key:

1. Install Ollama and pull the models the config names with `ollama pull <tag>`. A skill that finds a model not pulled names the command.
2. For images and music, add a provider of kind `diffusers` with its `models` to the config (see the example). The first run downloads the weights.

## Studio

`/studio` in a Claude Code session with the `studio` plugin starts a local server on `127.0.0.1` (a free port) and opens its page in the default browser (`open` on macOS, `xdg-open` on Linux). Projects are kept in `studio.dir` of `config.yaml`, default `~/Documents/Studio`. The session carries out the page's requests with the media skills, so Studio needs the models of the work it is asked for.

## Settings and documentation

The settings file, every setting and the settings errors are documented in the `setup:settings` skill; `plugins/setup/skills/settings/assets/config.example.yaml` lists every setting with placeholder values. Maintainer documentation is in `docs/`, with the repository rules in `docs/architecture.md`.
