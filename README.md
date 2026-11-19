# Agent Skills marketplace

A Claude Code marketplace, `pcingola-skills`, of Agent Skills for images, infographics, slide decks, short videos, music and voiceovers, with Studio, a Claude Code mod that drives them from a web page.

https://github.com/user-attachments/assets/711239a6-bca4-4202-b2b4-bc7f1aea4dfc

Full tutorial (6 min): [Studio for Claude Code](https://youtu.be/uZZ1xvNixfE)

## Quick start

Install every plugin (needs `uv` and `git`, see [Requirements](#requirements)):

```
claude plugin marketplace add pcingola/pcingola-skills
claude plugin install studio@pcingola-skills --scope user
claude plugin install dev@pcingola-skills --scope user
```

Start `claude` and ask it to "set up the skills". The `setup:settings` skill asks for your API keys and writes the settings file (see [Settings](#settings)).

Run Studio: type `/studio` in the Claude Code session. The page opens in your browser.

## Studio

Studio is a local web page for making images, infographics, slide decks and short videos. The Claude Code session carries out every request from the page with the media skills.

1. Start `claude` in any directory.
2. Type `/studio`. The session starts a local server on `127.0.0.1` (a free port) and opens its page in the default browser (`open` on macOS, `xdg-open` on Linux).
3. In the page, create a project, write a brief and send it. The session's progress notes and answers show in the page.

The server stops when the session ends. Projects are kept in `studio.dir` of the settings file, default `~/Documents/Studio`. Studio needs the models of the work it is asked for.

## Plugins

Installed, a skill loads as `<plugin>:<skill>`. Installing a plugin also installs the plugins it depends on.

| Plugin | Skills | Depends on |
| --- | --- | --- |
| docs | pptx, revealjs-slideshow | brand, setup |
| media | image-gen, infographic, music, pptx-author, short-video, video-effects, voiceover | ai, brand, docs, setup |
| dev | plan, skill-author | setup |
| brand | brand, style | setup |
| ai | batch-run, classify, second-opinion | setup |
| studio | images, videos | brand, media, setup |
| setup | settings | |

## Requirements

- Linux, or macOS on Apple Silicon (PyTorch, which voiceover always installs, has no wheels for Intel Macs).
- `uv` and `git` on `PATH`. uv builds each skill's environment on first use (a few seconds for most skills; minutes and several GB for the skills that install PyTorch) and fetches the shared packages in `lib/` from this repository, which needs network access to GitHub, no credentials. uv downloads Python 3.11 or later when the system has none.
- FFmpeg for the audio and video skills (music, short-video, video-effects, voiceover recordings, and large video input of second-opinion).
- LibreOffice and Poppler (`pdftoppm`) for the pptx previews and PDF export. macOS: `brew install libreoffice poppler`. Linux: `apt-get install libreoffice poppler-utils`.
- Node.js 22 or later with `npm` for short-video HTML scenes. Its first render runs `npm ci` and downloads a headless Chrome through HyperFrames.
- For short-video Manim scenes, Manim's system libraries (on Linux the Cairo and Pango development packages, `pkg-config` and a C compiler), and LaTeX with `dvisvgm` for formulas.
- Ollama for local chat, vision and System-1 models.
- On Linux, voiceover installs the CPU build of PyTorch (about 200 MB), or the CUDA 13.0 build (about 2.7 GB) and fish-speech when the settings file has a `fish` provider. Kokoro, Chatterbox and the word aligner run on the CPU.
- An NVIDIA GPU or Apple Silicon only for the local `diffusers` models (level 3 below); an NVIDIA GPU under Linux for `fish`.

## Settings

The skills that call a model (classify, second-opinion, image-gen, music, voiceover, short-video) go through the shared package `lib/ai_models`, built on Pydantic-AI. One YAML file holds every setting: `~/.claude/plugins/data/config.yaml` (`SKILLS_CONFIG` names another file). Its sections are `providers` (each provider's key in `api_key`, and the attributes of its models in `models`, including the local `diffusers` models), `tasks` (the model of each task), `network` (proxies, CA files), `huggingface`, `local_models`, `brand`, `studio` and `voiceover`. The file is validated at load; an error names the YAML path of each wrong key. The `setup:settings` skill creates it from `plugins/setup/skills/settings/assets/config.example.yaml`, which lists every setting with placeholder values, and documents every setting and error. A model id is `<provider name>:<model>`, for example `ollama:d3:4b`.

Provider kinds: `ollama`, `openrouter`, `openai` (any OpenAI-compatible server), `azure`, `google` (Gemini API or Vertex), `diffusers` (local models in process), `kokoro` and `chatterbox` (local speech on the CPU), `torchaudio` (word alignment on the CPU) and `fish` (local speech on an NVIDIA GPU, Linux). Tasks: `chat`, `vision`, `system1`, `embed`, `image`, `image_edit`, `image_best`, `image_multi_ref`, `speech`, `align`, `music`, `audio`, `video`, `presenter`, `film_critic`.

Three levels of setup, each adding to the one before:

1. API only: a key of OpenRouter, of Azure OpenAI and Vertex AI, or of a company (enterprise) gateway that serves them (kinds `azure` and `google`). No GPU.
2. Ollama: System-1 models, small chat models and speech (macOS) on a local Ollama server. No key.
3. GPU: a `diffusers` provider for local images, music and video. The image-gen, music and short-video wrappers then install torch and diffusers. It needs an NVIDIA GPU with driver 580 or later (CUDA 13.0 wheels of PyTorch) or Apple Silicon. A `fish` provider adds Fish Audio Drama 3 speech on an NVIDIA GPU under Linux (about 44 GB of GPU memory).

A minimal file for an OpenRouter key only (`chmod 600` it):

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

With no key, Ollama serves the chat models: `ollama pull <tag>` fetches each model the file names, and a skill that finds a model not pulled names the command. Images and music then need a provider of kind `diffusers` with its `models` (see the example file); the first run downloads the weights.

## Install, update and uninstall each plugin

Install one plugin at a time:

```
claude plugin marketplace add pcingola/pcingola-skills
claude plugin install <plugin>@pcingola-skills --scope user
```

`<plugin>` is a name from [Plugins](#plugins). Inside a Claude Code session the same commands are `/plugin marketplace add pcingola/pcingola-skills` and `/plugin install <plugin>@pcingola-skills`. Installing `studio` alone also installs every other plugin except `dev`.

Update to the latest commit:

```
claude plugin marketplace update pcingola-skills
claude plugin update <plugin>@pcingola-skills
```

Added from GitHub, each installed plugin loads from a copy in `~/.claude/plugins/cache/pcingola-skills/<plugin>/<commit>/`. Added from a local clone (`claude plugin marketplace add /path/to/pcingola-skills`), the marketplace is a directory source: Claude Code reads each installed plugin in place from `plugins/<plugin>/`, and working-tree edits, uncommitted ones included, take effect at the next session start or `/reload-plugins`. The version label is the commit.

Uninstall:

```
claude plugin uninstall <plugin>@pcingola-skills
```

An uninstall deletes the plugin's data directory unless `--keep-data` is passed. That directory holds the plugin's environments. The media data directory also holds the voiceover weights, the cloned voices, and the image-gen and music environments (with torch and diffusers when the settings file has a `diffusers` provider). The settings file and the weights of local `diffusers` models (Hugging Face cache, `huggingface.home` of the settings file, default `~/.cache/huggingface`) are outside every plugin data directory, so an uninstall keeps them. A reinstall after `uninstall --keep-data` reuses the environments and weights.

## Documentation

Maintainer documentation is in `docs/`, with the repository rules in `docs/architecture.md`.
