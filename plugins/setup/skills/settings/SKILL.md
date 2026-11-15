---
name: settings
description: "Installs the pcingola-skills marketplace and plugins, and creates and explains config.yaml: providers, keys, models and every skill setting. TRIGGER when: install or set up a plugin, a setting not set or invalid, API keys, config.yaml, models."
allowed-tools: Read Write Edit
---

# Settings

## Install and update

The marketplace is named `pcingola-skills`. Add it once, from its GitHub repository (`pcingola/pcingola-skills`) or from a local clone (a path):

```
claude plugin marketplace add pcingola/pcingola-skills
claude plugin marketplace add /path/to/pcingola-skills
```

Install each plugin with its own command; there is no command that installs all of them. Installing a plugin also installs the plugins listed in its `dependencies`.

```
claude plugin install <plugin>@pcingola-skills --scope user
```

Update the marketplace, then each installed plugin:

```
claude plugin marketplace update pcingola-skills
claude plugin update <plugin>@pcingola-skills
```

Uninstall without losing data, and reinstall:

```
claude plugin uninstall <plugin>@pcingola-skills --keep-data
claude plugin install <plugin>@pcingola-skills --scope user
```

The data directory is outside the plugin directory, so updates keep it. Without `--keep-data`, `uninstall` deletes the plugin's data directory. That directory holds the plugin's Python environments under `env/`. The media data directory also holds the voiceover weights (the default `dir` of the `kokoro`, `chatterbox` and `torchaudio` providers) and voices, the image-gen and music environments, which hold torch and diffusers when `config.yaml` has a `diffusers` provider, and html-animation's pinned JavaScript libraries and headless Chromium.

`config.yaml` is outside every plugin data directory, so an uninstall keeps it. The weights of local `diffusers` models are in the Hugging Face cache (`HF_HOME`, default `~/.cache/huggingface`), and those of the `kokoro`, `chatterbox` and `torchaudio` providers in their `dir`, also kept when it is set; the default `dir`, `voiceover/` in the media data directory, goes with that directory.

A plugin installed from a local directory is read in place, so edits take effect at the next session start or `/reload-plugins`. A plugin installed from a git or remote marketplace loads a copy under `~/.claude/plugins/cache/`.

A skill installed as part of a plugin loads as `<plugin>:<skill>`. A skill that reports another skill missing names it as `<plugin>:<skill>`; the fix is `claude plugin install <plugin>@pcingola-skills --scope user`.

## Plugins

| Plugin | Contents |
|---|---|
| docs | raw PowerPoint (.pptx) operations: inspect, fill, shapes with measured text, overflow checks, slide copy between decks; offline reveal.js slideshows |
| media | image, music and voiceover generation, narrated short videos, image-to-image video effects, infographics, slide deck authoring, standalone HTML animations with an editor |
| dev | implementation plans, Agent Skill authoring and review |
| brand | brand folders (logos, colours, fonts, guidelines, PowerPoint templates) and a catalogue of visual styles |
| ai | text classification with a System-1 model (class probabilities) or a chat model; file review by a second model |
| studio | a page in the browser for making images, infographics, slide decks and short videos with Claude (`/studio`); projects under `STUDIO_DIR`, default `~/Documents/Studio` |
| setup | this skill: installation and settings |

## Python environments

Each skill with a CLI tool runs it with `uv run --project` in its own environment, so `uv` must be on `PATH`. uv builds the environment on first use, under `<plugin data dir>/env/`, outside the plugin directory. `<plugin data dir>` is `$CLAUDE_PLUGIN_DATA`, else `<config dir>/plugins/data/<plugin>-pcingola-skills`. The shared libraries (`plugin-settings`, `ai-models`) are git dependencies that uv downloads from the marketplace's GitHub repository while building the environment. That needs `git`, network access to GitHub and read access to the repository (the same git credentials as installing the marketplace from it).

## The settings file: config.yaml

Every skill reads its settings from one file: `<config dir>/plugins/data/config.yaml`. `<config dir>` is `$CLAUDE_CONFIG_DIR`, else `~/.claude`. `SKILLS_CONFIG` in the process environment names another file. The file has four sections:

| Section | Holds |
|---|---|
| `providers` | where models run: `kind`, `base_url`, the key as `api_key`, `timeout`, `api_version`, `vertex` |
| `models` | the model of each task, as `<provider name>:<model>` |
| `diffusers` | local image, music and video models (GPU) |
| `settings` | every other setting, `KEY: value` (for example `EXTRA_CA_CERT`, `HF_HOME`) |

`assets/config.example.yaml` is the template. It lists every setting a skill reads, commented, with its meaning, default, accepted values and the skills that require it. Read it to find a setting's name and values.

Rules:

- A skill reads `settings.<KEY>`, else the variable `KEY` of the process environment, else its default.
- A key with no value (`KEY:`) is unset. An empty string (`KEY: ""`) is set but empty, and a required setting treats it as missing.
- `true` and `false` are read as the strings `true` and `false`.
- A value with `: ` or ` #` in it needs quotes, for example `NO_PROXY: "localhost # local only"`.
- `CLAUDE_CONFIG_DIR`, `CLAUDE_PLUGIN_DATA` and `SKILLS_CONFIG` come from the process environment only.
- A skill exports `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`, `SSL_CERT_FILE`, `NODE_EXTRA_CA_CERTS`, `HF_HOME` and `HF_TOKEN` from `settings` to its process environment, where libraries and child processes read them.
- The file holds API keys; tell the user to run `chmod 600` on it.

## Create or change config.yaml

When the user asks to set up the skills, or a skill reports a missing config, setting or key:

1. Find the file: `$SKILLS_CONFIG`, else `<config dir>/plugins/data/config.yaml`. Read it when it exists.
2. When it does not exist, read `${CLAUDE_SKILL_DIR}/assets/config.example.yaml`. Ask the user's level (below), then write the file from the template: the `providers` and `models` of that level, `diffusers` only for the GPU level, and the whole commented `settings` section. Create the directory when it is missing.
   Then write `routes.md` in the same directory as a copy of `${CLAUDE_SKILL_DIR}/assets/routes.md` (Model routes below), unless it exists.
3. Ask for each key the chosen providers need and write it as `api_key` of the provider. Never echo a key back in the reply.
4. Ask for the settings of the skills the user wants (the table of required settings below), and uncomment or add them under `settings`.
5. Tell the user to run `chmod 600 <file>`.

Change an existing file with Edit, one entry at a time. Do not overwrite it.

### Levels

Each level adds to the one before.

| Level | Needs | Providers | Tasks it serves |
|---|---|---|---|
| 1. API only | a key of OpenRouter, of Azure OpenAI and Vertex AI, or of a company (enterprise) gateway that serves them; no GPU | `openrouter` (kind `openrouter`) or `azure` (kind `azure`) and `vertex` (kind `google`, `vertex: true`), each with the `base_url` of the service or of the gateway | `chat`, `vision`, `image`, `image_edit`, `image_best`, `image_multi_ref`, `speech`, `audio`; `music` on a provider of kind `google` (Lyria) |
| 2. Ollama | a running Ollama server with the models pulled (`ollama pull <tag>`); no key | add `ollama` (kind `ollama`) | `system1` (System-1 models, needed by classify `--backend system1`), small `chat` and `vision` models, `speech` on macOS (`lfm3-audio`, for tests only: its intonation is odd and uncontrolled) |
| 3. GPU | an NVIDIA GPU with driver 580 or later (CUDA 13.0 wheels of PyTorch) or Apple Silicon | add `local` (kind `diffusers`) and the `diffusers` section | `image`, `image_edit`, `image_best`, `image_multi_ref`, `music`, `video`, `presenter` in the skill's process |

Point each task the user needs at a provider of the chosen level. A task without a model fails only when a skill asks for it. The model ids of the template are examples; ask the user which models to use when the template has none for a provider. At level 3 the image-gen, music and short-video wrappers install torch and diffusers (the skill's `local` extra) when they build the environment, and the first run downloads the weights. The default local image model is FLUX.2 klein 4B (`local:flux2-klein-4b`); Qwen-Image 2.1 (`local:qwen-image`) spells text right at about 9 times the wall time; Z-Image-Turbo is optional.

## Settings errors

A missing required setting exits with a message like:

```
Error: <KEY> is not set.
Settings are read from ~/.claude/plugins/data/config.yaml (not found), section `settings`, then from the process environment.
Add it to that file:
  settings:
    <KEY>: <value>
The setup:settings skill describes every setting and creates the file.
```

A value a skill rejects exits with `KEY='value' (set in settings.KEY in <file>) is not valid: <what is accepted>`, or `(set in the process environment)`, and the same line naming the file.

A model call without the file exits with `no config at <file>; the setup:settings skill creates it`. A task without a model names the missing `models.<task>`. A provider with an empty `api_key` names the provider kind and the file.

Required settings, per skill:

| Plugin | Skill and command | Required |
|---|---|---|
| ai, media | classify, second-opinion, image-gen, music, voiceover, short-video video and presenter scenes | a model for the task in `models`, and the `api_key` of its provider when the provider needs one |
| media | image-gen with a model of kind `openai`, `azure`, `openrouter`, `ollama` or `diffusers` | `IMAGE_GEN_OPENAI_MAX_EDGE`, `IMAGE_GEN_OPENAI_MIN_PIXELS`, `IMAGE_GEN_OPENAI_MAX_PIXELS`, `IMAGE_GEN_LOCAL_MAX_EDGE`, `IMAGE_GEN_LOCAL_MIN_EDGE` |

The values of these settings are in `assets/config.example.yaml`.

## Models

A model id is `<provider name>:<model>`; the first colon splits it, so `ollama:d3:4b` is the Ollama tag `d3:4b`. A skill flag `--model <provider>:<model>` replaces the task's model for one call.

Provider kinds (`providers.<name>.kind`):

| Kind | Serves | Keys of the entry |
|---|---|---|
| `ollama` | chat, vision, embeddings, System-1 models, speech (Ollama on macOS) | `base_url` (default `http://localhost:11434/v1`) |
| `openrouter` | chat, vision, audio input, embeddings, images, image edits, speech | `api_key` |
| `openai` | any OpenAI-compatible server: chat, embeddings, images, speech | `base_url`, `api_key` |
| `azure` | Azure OpenAI: chat, images with masks, speech | `base_url` (the Azure endpoint), `api_version`, `api_key` |
| `google` | Gemini chat with audio and video input, Gemini image models, Gemini TTS, Lyria music | `api_key`, `base_url`; `vertex: true` for a Vertex endpoint; `predict_models`, the music models served by the Vertex `:predict` endpoint (the others stream) |
| `diffusers` | local images, image edits with masks, music, image to video, portrait and speech to video, in the skill's process on a CUDA or Apple MPS GPU | none; the models are in `diffusers` |
| `kokoro` | local speech (Kokoro 82M) on the CPU, in the skill's process | `model_url`, `voices_url` (the model files), `langs` (voice-name prefix to espeak language), `dir` (optional: weights directory, default `voiceover/` in the data directory of the plugin that runs the model, media's for voiceover) |
| `chatterbox` | local speech with voice cloning (Chatterbox Turbo) on the CPU, in a worker process of its own Python environment | `python` (the environment's interpreter), `url` and `files` (the model files under that URL), `dir`, `start_timeout` and `timeout` (optional, seconds for the load and for each sentence, default 600) (optional, as for `kokoro`) |
| `torchaudio` | forced alignment (`align`) on the CPU, in the skill's process | `url` (the pipeline's weights file), `dir` (optional, as for `kokoro`) |
| `vllm-omni` | local speech (Fish Audio Drama 3) on a CUDA GPU, served by vLLM-Omni from its own Python environment for the length of one command | `python` (the environment's interpreter), `repo`, `deploy` (vLLM-Omni deploy config name or path), `memory_share` (share of the free memory the server takes), `style` (optional: a format with `{instructions}` and `{text}`), `args` (optional: more server arguments), `env` (optional: server environment variables), `start_timeout` (optional, seconds, default 1800) |

A provider that serves speech takes `voice` (optional: its default voice, else the kind's: `marin` for `openai`, `azure` and `openrouter`, `Kore` for `google`, `af_heart` for `kokoro`, and `default`, the model's own voice, for `ollama`, `vllm-omni` and `chatterbox`) and `voices` (optional: the list `voiceover voices` prints; without it a `kokoro` model lists its voices and the others their default voice).

Every provider except `diffusers` takes `timeout` (seconds per request, default 600). System-1 models go to the `base_url` of their provider, so any provider with a `base_url` can serve them; Ollama serves them at `/v1/systemone`.

Tasks (`models.<task>`) and the skills that ask for them:

| Task | Skill |
|---|---|
| `chat` | classify (`--backend chat`), second-opinion |
| `vision` | second-opinion when an image is among the files |
| `system1` | classify (`--backend system1`, System-1 models with class probabilities) |
| `image`, `image_edit` | image-gen `--tier fast` (the default) without and with `--ref` |
| `image_best` | image-gen `--tier best` (Studio "Best", video-effects keyframes), with and without `--ref` |
| `image_multi_ref` | image-gen `--tier multi-ref` (Studio "Multi-reference"), with and without `--ref` |
| `speech` | voiceover (`synth`, `voices`) |
| `align` | voiceover word times (`synth` without `--no-align`) |
| `music` | music `generate` |
| `audio` | music `analyze` (a chat model that takes audio) |
| `video` | short-video video scenes (`Engine: video`): an image animated into a clip |
| `presenter` | short-video presenter scenes (`Engine: presenter`): a portrait and the scene's narration recording made into a clip of the person speaking it |

The `audio` task is optional; without it `music analyze` skips the model section. `image_best` and `image_multi_ref` are optional; without them the image-gen tiers `best` and `multi-ref` fail with a message naming the task. `video` is optional; without it a short-video scene with `Engine: video` fails at `render` with a message naming the task.

`diffusers.<name>` describes one local model: `repo` (a Hugging Face repository; weights go to the Hugging Face cache), `steps`, `guidance`, and `inpaint` (the diffusers pipeline class for edits with a mask). A model id `local:<name>` names it. A video model also has these keys, all required: `pipeline` (the diffusers class to load), `fps`, `size_multiple` (width and height are rounded to it), `frame_step` (frame counts are `frame_step * k + 1`), `width`, `height` (the default size) and `max_frames`.

## Model routes: routes.md

A route row names the model for some requests of a task. Per task, a `default` row names the recommended default model with its strengths and limits, and the other rows are escalations: another model for the requests their condition names. The table is `routes.md` in the directory of `config.yaml` (beside `$SKILLS_CONFIG` when that is set); no plugin update changes it. Its template is `${CLAUDE_SKILL_DIR}/assets/routes.md`, with wall times and quality notes measured on an NVIDIA GB10 for the `local` models of `config.example.yaml`.

The model in use is still `models.<task>`. Each model-calling skill's `routes` command prints, per task, the default row with the model of `models.<task>`, then the escalation rows. When `models.<task>` differs from the table's default model, the default row's `why` is `set in config.yaml; the table recommends <model>: <its why>`. Without `routes.md` the command prints only the defaults of `models.<task>` and says that the table is missing.

The file holds one Markdown table; text outside the table is ignored:

```markdown
| task | model | when | why |
|---|---|---|---|
| image | local:flux2-klein-4b | default | about 16 s per 2K image; misspells text |
| image | local:qwen-image | only when the image is an architecture diagram | labels spelled right |
```

- `task`: a task of the `models` section (`image`, `video`, `speech`, ...).
- `model`: `<provider name>:<model>` of `config.yaml`. A row whose provider is not in `providers`, or whose `diffusers` model is not in `diffusers`, is left out.
- `when`: `default`, or a condition beginning with `only when`. A task has at most one `default` row. To change the model in use, change `models.<task>`. The agent uses the default row and takes an escalation row only when its condition holds for the request; the first such row wins.
- `why`: strengths and limits (quality, wall time).

To add a row, create the file from the template when it is missing and add the row with Edit; put a more specific row above a general one of the same task. A malformed row makes the `routes` command fail with the file and line.

### Update routes.md from the template

When the user asks to update the routes, for example after a plugin update:

1. Read `${CLAUDE_SKILL_DIR}/assets/routes.md` and the user's `routes.md`.
2. List the template rows that the user's file lacks or holds with another `model`, `when` or `why`, matched by task and `when`. Show each to the user next to the user's row of that task and `when`, if any.
3. For each row the user accepts, Edit the user's file: replace the matched row, or add the row after the last row of its task. Keep every other user row as it is, including rows the template lacks.
