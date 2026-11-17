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

The data directory is outside the plugin directory, so updates keep it. Without `--keep-data`, `uninstall` deletes the plugin's data directory. That directory holds the plugin's Python environments under `env/`. The media data directory also holds the voiceover weights (the default `dir` of the `kokoro`, `chatterbox` and `torchaudio` providers) and voices, and the image-gen and music environments, which hold torch and diffusers when `config.yaml` has a `diffusers` provider.

`config.yaml` is outside every plugin data directory, so an uninstall keeps it. The weights of local `diffusers` models are in the Hugging Face cache (`huggingface.home`, default `~/.cache/huggingface`), as are those of `fish` models given by repository, and those of the `kokoro`, `chatterbox` and `torchaudio` providers in their `dir`, also kept when it is set; the default `dir`, `voiceover/` in the media data directory, goes with that directory.

A plugin installed from a local directory is read in place, so edits take effect at the next session start or `/reload-plugins`. A plugin installed from a git or remote marketplace loads a copy under `~/.claude/plugins/cache/`.

A skill installed as part of a plugin loads as `<plugin>:<skill>`. A skill that reports another skill missing names it as `<plugin>:<skill>`; the fix is `claude plugin install <plugin>@pcingola-skills --scope user`.

## Plugins

| Plugin | Contents |
|---|---|
| docs | raw PowerPoint (.pptx) operations: inspect, fill, shapes with measured text, overflow checks, slide copy between decks; offline reveal.js slideshows |
| media | image, music and voiceover generation, narrated short videos, image-to-image video effects, infographics, slide deck authoring |
| dev | implementation plans, Agent Skill authoring and review |
| brand | brand folders (logos, colours, fonts, guidelines, PowerPoint templates) and a catalogue of visual styles |
| ai | text classification with a System-1 model (class probabilities) or a chat model; file review by a second model |
| studio | a page in the browser for making images, infographics, slide decks and short videos with Claude (`/studio`); projects under `studio.dir`, default `~/Documents/Studio` |
| setup | this skill: installation and settings |

## Python environments

Each skill with a CLI tool runs it with `uv run --project` in its own environment, so `uv` must be on `PATH`. uv builds the environment on first use, under `<plugin data dir>/env/`, outside the plugin directory. `<plugin data dir>` is `$CLAUDE_PLUGIN_DATA`, else `<config dir>/plugins/data/<plugin>-pcingola-skills`. The shared libraries (`plugin-settings`, `ai-models`) are git dependencies that uv downloads from the marketplace's GitHub repository while building the environment. That needs `git` and network access to `https://github.com/pcingola/pcingola-skills`; the repository is public, so no credentials. uv downloads Python 3.11 or later when the system has none. Most environments build in seconds; voiceover always installs PyTorch and Chatterbox (on Linux the CPU build of PyTorch, about 200 MB, or, when `config.yaml` has a `fish` provider, the CUDA 13.0 build, about 2.7 GB, and fish-speech), and image-gen, music and short-video install it at the GPU level.

## System tools

When the user sets up the skills, name the tools that the skills the user wants need on `PATH`, with their install command:

| Tool | Skills | macOS | Linux (Debian, Ubuntu) |
|---|---|---|---|
| `uv`, `git` | every CLI skill | `brew install uv git` | `curl -LsSf https://astral.sh/uv/install.sh \| sh`, `apt-get install git` |
| `ffmpeg` | music, short-video, video-effects, voiceover recordings, second-opinion large video | `brew install ffmpeg` | `apt-get install ffmpeg` |
| `soffice`, `pdftoppm` | pptx previews and slide export | `brew install libreoffice poppler` | `apt-get install libreoffice poppler-utils` |
| `node` 22 or later, `npm` | short-video HTML scenes (the first render runs `npm ci` and downloads a headless Chrome) | `brew install node` | Node.js 22 from nodejs.org or NodeSource |
| `latex`, `dvisvgm` | short-video Manim scenes with formulas | `brew install --cask mactex` | `apt-get install texlive texlive-latex-extra dvisvgm` |
| `ollama` | the `ollama` provider | ollama.com | ollama.com |

Short-video Manim scenes on Linux also need `libcairo2-dev`, `libpango1.0-dev`, `pkg-config` and a C compiler. On macOS, PyTorch has wheels only for Apple Silicon, so voiceover does not run on an Intel Mac.

## The settings file: config.yaml

Every skill reads its settings from one file: `<config dir>/plugins/data/config.yaml`. `<config dir>` is `$CLAUDE_CONFIG_DIR`, else `~/.claude`. `SKILLS_CONFIG` in the process environment names another file. The sections:

| Section | Holds |
|---|---|
| `providers` | where models run: `kind`, `base_url`, the key as `api_key`, `timeout` and the keys of each kind (Models below); `models`, the attributes of each model of the provider (a model of a local kind must have one) |
| `tasks` | the model of each task, as `<provider name>:<model>` |
| `network` | `http_proxy`, `https_proxy`, `all_proxy`, `no_proxy` (a list), `extra_ca_cert` (a CA trusted on top of the public roots, for a TLS-intercepting proxy), `ca_bundle` (a trust store that replaces the default one) |
| `huggingface` | `home` (the weights cache of the `diffusers` and `fish` models, default `~/.cache/huggingface`), `token` (gated repositories only) |
| `local_models` | `lock_wait`: the seconds a command waits for another process that holds the local GPU models (`diffusers`, `fish`) before it fails naming that process's PID; a positive number; unset, no limit (a second command waits for a render to finish) |
| `brand` | `path`: directories searched for brand folders after the bundled ones |
| `studio` | `dir` (the Studio projects, absolute or `~`, default `~/Documents/Studio`), `author` (the default "Made by" names of a new film) |
| `voiceover` | `voices_dir`: the reference recordings of `add-voice` and the saved Fish voices (`<name>.fish/`) |

`assets/config.example.yaml` is the template. It lists every section and key, commented, with its meaning, default, accepted values and the skills that read it. Read it to find a key's name and values.

Rules:

- The whole file is validated when a skill starts. A misspelt section or key, a missing required key, a wrong type, a URL without `http://` or `https://` (a proxy also takes `socks4`, `socks5`, `socks5h`), a CA file that does not exist, a task whose provider is not in `providers` or is of a kind the task does not take (Models below), a task naming a model of a local kind without an entry, or a task naming a `diffusers` model of another role stops the skill with an error that names the YAML path of each problem. A `--model` flag is checked the same way when the skill starts the call.
- A section, `models:` map, model entry or list that is empty or holds only comments takes its defaults (empty). Every key is optional unless the template says "required".
- A list is a YAML list: `brand.path: [/path/to/brands]`, `studio.author: [Alice Example]`, `network.no_proxy: [localhost, 127.0.0.1]`. Paths take `~`.
- An empty `api_key`, `huggingface.token` or `tasks.<task>` is an error; leave the key out instead.
- A value with `: ` or ` #` in it needs quotes.
- A variable exported in the shell is not a setting: skills ignore it. `CLAUDE_CONFIG_DIR`, `CLAUDE_PLUGIN_DATA` and `SKILLS_CONFIG` come from the process environment only.
- A skill sets these variables in its process environment from the file, where libraries and child processes read them, and removes each one the file does not set:

  | Variable | From |
  |---|---|
  | `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY` (also in lower case) | `network.http_proxy`, `https_proxy`, `all_proxy`, `no_proxy` |
  | `SSL_CERT_FILE` | `network.ca_bundle` |
  | `NODE_EXTRA_CA_CERTS` | `network.extra_ca_cert` |
  | `HF_HOME`, `HF_TOKEN` | `huggingface.home`, `huggingface.token` |

- A skill removes the variables that would replace a setting of the file: every `OPENAI_*`, `AZURE_OPENAI_*`, `AZURE_VOICELIVE_*`, `OPENROUTER_*`, `OLLAMA_*`, `GOOGLE_GENAI_*`, `GOOGLE_CLOUD_*` and `SYSTEM_ONE_*` variable (keys, endpoints and headers of the model client libraries), `GOOGLE_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS`, `GOOGLE_GEMINI_BASE_URL`, `GOOGLE_VERTEX_BASE_URL` (Google clients), `SSL_CERT_DIR`, `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE` (trust stores), and `HF_HUB_CACHE`, `HUGGINGFACE_HUB_CACHE`, `HF_HUB_OFFLINE`, `HUGGING_FACE_HUB_TOKEN` (Hugging Face cache, offline switch and token, which would replace `huggingface.*`). A key or proxy exported in the shell (for example `OPENAI_API_KEY`, `https_proxy`) has no effect: a user who relied on one moves it into the file (keys as `api_key` of the provider, proxies under `network`).
- The file holds API keys; tell the user to run `chmod 600` on it.

## Create or change config.yaml

When the user asks to set up the skills, or a skill reports a missing config, setting or key:

1. Find the file: `$SKILLS_CONFIG`, else `<config dir>/plugins/data/config.yaml`. Read it when it exists.
2. When it does not exist, read `${CLAUDE_SKILL_DIR}/assets/config.example.yaml`. Ask the user's level (below), then write the file from the template: the `providers` and `tasks` of that level (every level includes `kokoro` and `torchaudio` with the tasks `speech` and `align`: voiceover aligns by default), the `local` provider of kind `diffusers` only for the GPU level, and the sections `network`, `huggingface`, `local_models`, `brand`, `studio` and `voiceover` with their keys commented. Create the directory when it is missing.
   Then write `routes.md` in the same directory as a copy of `${CLAUDE_SKILL_DIR}/assets/routes.md` (Model routes below), unless it exists.
3. Ask for each key the chosen providers need and write it as `api_key` of the provider. Never echo a key back in the reply.
4. Ask for the settings of the skills the user wants (the table of required settings below and the other sections), and uncomment or add them.
5. Tell the user to run `chmod 600 <file>`.

Change an existing file with Edit, one entry at a time. Do not overwrite it.

### Levels

Each level adds to the one before.

| Level | Needs | Providers | Tasks it serves |
|---|---|---|---|
| 1. API only | a key of OpenRouter, of Azure OpenAI and Vertex AI, or of a company (enterprise) gateway that serves them; no GPU | `openrouter` (kind `openrouter`) or `azure` (kind `azure`) and `vertex` (kind `google`, `vertex: true`), each with the `base_url` of the service or of the gateway; `kokoro` (kind `kokoro`) and `torchaudio` (kind `torchaudio`) on the CPU, no key | `chat`, `vision`, `image`, `image_best`, `speech`, `align`, `audio`; `image_edit` and `image_multi_ref` on `azure` or `vertex` (OpenRouter serves no image edits: `POST /images/edits` returns 404); `music` on a provider of kind `google` (Lyria) |
| 2. Ollama | a running Ollama server with the models pulled (`ollama pull <tag>`); no key | add `ollama` (kind `ollama`) | `system1` (System-1 models, needed by classify `--backend system1`), small `chat` and `vision` models, `speech` on macOS (`lfm3-audio`, for quick drafts only: its intonation is odd and uncontrolled) |
| 3. GPU | an NVIDIA GPU with driver 580 or later (CUDA 13.0 wheels of PyTorch) or Apple Silicon | add `local` (kind `diffusers`) with its `models` | `image`, `image_edit`, `image_best`, `image_multi_ref`, `music`, `video`, `presenter` in the skill's process; `speech` with a `fish` provider (Fish Audio Drama 3, NVIDIA on Linux only) |

Point each task the user needs at a provider of the chosen level. A task without a model fails only when a skill asks for it. The model ids of the template are examples; ask the user which models to use when the template has none for a provider. An image model of an OpenAI kind (`openai`, `azure`, `openrouter`, `ollama`) gets an `image` entry under its provider's `models` with its size limits, as `gpt-image-2` has in the template; `max_edge: 3840`, `min_pixels: 655360` and `max_pixels: 8294400` are gpt-image-2's and serve when the model's own are unknown. At level 3 the image-gen, music and short-video wrappers install torch and diffusers (the skill's `local` extra) when they build the environment, and the first run downloads the weights. The default local image model is FLUX.2 klein 4B (`local:flux2-klein-4b`); Qwen-Image 2.1 (`local:qwen-image`) spells text right at about 9 times the wall time; Z-Image-Turbo is optional. The default local music model is `local:ace-step-sft` (50 steps, about 12 s per 30 s clip); `local:ace-step` (8 steps, about 2 s per 30 s clip) gives loud, compressed sound and serves quick drafts and test films. A music model entry's optional `min_crest_db` makes `music generate` send a request again when a track's crest factor is below it (`--min-crest-db` overrides it per call); the template sets 10 on `ace-step-sft` only.

## Settings errors

A file that is not valid stops the skill with one message that lists every problem, each with its YAML path:

```
Error: ~/.claude/plugins/data/config.yaml is not valid:
  providers.azure.api_version: required for kind azure
  providers.openrouter.api_key: required for kind openrouter
  network.extra_ca_cert: file /path/ca.pem does not exist
  studio.dirr: not a setting
The setup:settings skill describes every key and creates the file.
```

Fix each line in the file with Edit. The task references are checked once the rest is valid: `tasks.music: provider 'vertex' is not in providers`, `tasks.image: model 'qwen-image' is not in providers.local.models`, `tasks.align: provider 'ollama' is of kind ollama; task align takes kinds torchaudio`, `tasks.video: providers.local.models.flux2-klein-4b is an image model; task video takes a video model`.

A key of an earlier layout of the file is an error that names its new place. Move each one there:

```
Error: ~/.claude/plugins/data/config.yaml is not valid:
  models: renamed to tasks
  settings.BRAND_PATH: moved to brand.path, a list of directories
  settings.IMAGE_GEN_LOCAL_MAX_EDGE: moved to providers.<p>.models.<m>.image.max_edge of each diffusers image model
The setup:settings skill describes every key and creates the file.
```

The earlier `diffusers:` section becomes the `models` of the provider of kind `diffusers`, with the same entries. `predict_models: [m]` of a provider becomes `models: {m: {predict: true}}`. The model keys of a `kokoro`, `torchaudio` or `chatterbox` provider (`model_url`, `voices_url`, `langs`, `url`, `files`, `repo`, `memory`, `style`) and the `voice` and `voices` of any provider move to `providers.<p>.models.<m>`, under the model name of `tasks.speech` or `tasks.align` (for example `kokoro-v1.0`, `MMS_FA`). Values change type: `BRAND_PATH: a:b` is `brand.path: [a, b]`, `AUTHOR_NAME: A, B` is `studio.author: [A, B]`, `NO_PROXY: a,b` is `network.no_proxy: [a, b]`; `IMAGE_GEN_SIZED_MODELS` becomes `always_sized: true` and `IMAGE_GEN_SIZED_QUALITY` `default_quality` in the `image` entry of each listed model. `EXTRA_CA_CERT` and `NODE_EXTRA_CA_CERTS` become one key, `network.extra_ca_cert`. A `chatterbox` provider's `python`, `start_timeout` and `timeout` are removed: delete them (Chatterbox runs in the voiceover process). The earlier provider kind of Fish Audio Drama 3 is an error that names `kind: fish` and the keys that kind lacks: set `kind: fish`, delete the keys the error names, keep `repo` and `style`, and delete `memory` for Drama 3's default (44, the GB it takes at its peak).

A model call without the file exits with `no config at <file>; the setup:settings skill creates it`. A task without a model exits with `no model for task 'chat': add `tasks.chat: <provider>:<model>` to <file>`. A provider without `api_key` whose server refuses the request (401 or 403) exits naming `providers.<name>.api_key` and the file. A client library's own variables (`OPENAI_API_KEY`, `GOOGLE_API_KEY`, `AZURE_OPENAI_ENDPOINT`, ...) are ignored.

Required settings, per skill:

| Plugin | Skill and command | Required |
|---|---|---|
| ai, media | classify, second-opinion, image-gen, music, voiceover, short-video video and presenter scenes | a model for the task in `tasks`, and the `api_key` of its provider when the provider kind needs one |
| media | image-gen with `--size` on a model of kind `openai`, `azure`, `openrouter` or `ollama` | `providers.<p>.models.<m>.image` with `max_edge`, `min_pixels`, `max_pixels` (an `image` entry always needs all three) |
| media | image-gen on a `diffusers` model, except an edit without `--size` and `--aspect` | `providers.<p>.models.<m>.image` with `max_edge` and `min_edge` (an `image` entry always needs both) |

A missing `image` entry exits with `<provider>:<model> has no image limits: add providers.<p>.models.<m>.image with max_edge, min_pixels, max_pixels to <file>` (`max_edge, min_edge` for a `diffusers` model). The values for the template's models are in `assets/config.example.yaml`.

## Models

A model id is `<provider name>:<model>`; the first colon splits it, so `ollama:d3:4b` is the Ollama tag `d3:4b`. A skill flag `--model <provider>:<model>` replaces the task's model for one call.

Provider kinds (`providers.<name>.kind`):

| Kind | Serves | Keys of the entry |
|---|---|---|
| `ollama` | chat, vision, embeddings, System-1 models, speech (Ollama on macOS) | `base_url` (default `http://localhost:11434/v1`) |
| `openrouter` | chat, vision, audio input, embeddings, images (no image edits: `image_edit`, `image_multi_ref` and `--ref` need another kind), speech | `api_key` |
| `openai` | any OpenAI-compatible server: chat, embeddings, images, speech | `base_url` (default the OpenAI API), `api_key` (required without `base_url`) |
| `azure` | Azure OpenAI: chat, images with masks, speech | `base_url` (the Azure endpoint), `api_version`, `api_key` |
| `google` | Gemini chat with audio and video input, Gemini image models, Gemini TTS, Lyria music | `api_key`, `base_url`; `vertex: true` for a Vertex endpoint, which takes Google Cloud credentials in place of `api_key`: `credentials` (path to a service-account JSON file; its project unless `project` is set), else Application Default Credentials (`gcloud auth application-default login`), with `project` and `location` (default `us-central1`); the `:predict` models need `api_key`; `models.<m>.predict: true` for a music model served by the Vertex `:predict` endpoint (the others stream) |
| `diffusers` | local images, image edits with masks, music, image to video, portrait and speech to video, in the skill's process on a CUDA or Apple MPS GPU | `models`: one entry per local model (below) |
| `kokoro` | local speech (Kokoro 82M) on the CPU, in the skill's process | `dir` (optional: weights directory; without it the voiceover skill keeps the weights in `voiceover/` of the media data directory); each model: `model_url`, `voices_url` (the model files), `langs` (voice-name prefix to espeak language) |
| `chatterbox` | local speech with voice cloning (Chatterbox Turbo) on the CPU, in the skill's process | `dir` (optional, as for `kokoro`); each model: `url` and `files` (the model files under that URL) |
| `torchaudio` | forced alignment (`align`) on the CPU, in the skill's process | `dir` (optional, as for `kokoro`); each model, named by its `torchaudio.pipelines` name (`MMS_FA`): `url` (the pipeline's weights file) |
| `fish` | local speech with inline tags (Fish Audio Drama 3) on an NVIDIA GPU (Linux), in the skill's process through fish-speech; the load takes about 4 min and 44 GB | no provider keys; each model: `repo` (required: a Hugging Face repository, downloaded to the Hugging Face cache, or a local folder, absolute or `~`), `memory` (optional: GB the model takes at its peak, checked against the free memory before the load, default 44), `style` (optional: a format with `{instructions}` and `{text}` that puts voiceover's `--style` into the text; without it the model takes no style), `max_frames` (optional: the audio frames one request makes at most, about 21.5 per second; default fish-speech's, 1024) |

A speech model's entry (`providers.<p>.models.<m>`) takes `voice` (optional: its default voice, else the kind's: `marin` for `openai`, `azure` and `openrouter`, `Kore` for `google`, `af_heart` for `kokoro`, and `default`, the model's own voice, for `ollama`, `fish` and `chatterbox`; `default` is a `fish` model's only voice) and `voices` (optional: the list `voiceover voices` prints; without it a `kokoro` model lists its voices and the others their default voice).

The remote kinds take `timeout` (seconds per request, default 600). System-1 models go to the `base_url` of their provider (an `ollama` provider's default included), so a remote provider with a `base_url` can serve them; Ollama serves them at `/v1/systemone`.

Tasks (`tasks.<task>`) and the skills that ask for them:

| Task | Skill | Provider kinds |
|---|---|---|
| `chat` | classify (`--backend chat`), second-opinion | remote: `ollama`, `openrouter`, `openai`, `azure`, `google` |
| `vision` | second-opinion when an image is among the files | remote |
| `system1` | classify (`--backend system1`, System-1 models with class probabilities) | remote, with a `base_url` |
| `image`, `image_edit` | image-gen `--tier fast` (the default) without and with `--ref` | `ollama`, `openrouter`, `openai`, `azure`, `google`, `diffusers` (an image model) |
| `image_best` | image-gen `--tier best` (Studio "Best", video-effects keyframes), with and without `--ref` | as `image` |
| `image_multi_ref` | image-gen `--tier multi-ref` (Studio "Multi-reference"), with and without `--ref` | as `image` |
| `speech` | voiceover (`synth`, `voices`) | remote, `fish`, `kokoro`, `chatterbox` |
| `align` | voiceover word times (`synth` without `--no-align`) | `torchaudio` |
| `music` | music `generate` | `google`, `diffusers` (a music model) |
| `audio` | music `analyze` (a chat model that takes audio) | remote |
| `video` | short-video video scenes (`Engine: video`): an image animated into a clip | `diffusers` (a video model) |
| `presenter` | short-video presenter scenes (`Engine: presenter`): a portrait and the scene's narration recording made into a clip of the person speaking it | `diffusers` (a presenter model) |
| `film_critic` | short-video film critic, through second-opinion (a model that takes video with sound) | remote |
| `embed` | embeddings | remote |

The `audio` task is optional; without it `music analyze` skips the model section. `image_best` and `image_multi_ref` are optional; without them the image-gen tiers `best` and `multi-ref` fail with a message naming the task. `video` is optional; without it a short-video scene with `Engine: video` fails at `render` with a message naming the task.

`providers.<p>.models.<m>` holds the attributes of one model, by the model name after the colon. For a remote provider it is optional; such a provider serves any model id. An entry of a model of kind `openai`, `azure`, `openrouter` or `ollama` holds `image` (image-gen size limits: `max_edge`, `min_pixels`, `max_pixels`, required, and `always_sized`, `default_quality`), `voice` and `voices`; one of kind `google` holds `predict`, `voice` and `voices`. A provider of a local kind (`diffusers`, `kokoro`, `torchaudio`, `chatterbox`, `fish`) serves only the models it lists. A `diffusers` entry has `repo` (required: a Hugging Face repository, whose weights go to the Hugging Face cache, or a folder of a saved pipeline as an absolute or `~` path), `steps`, `guidance`, `args` and `skip`, and the keys of its role; the keys make the role, and a key of another role is an error. An image model (no key of another role) has `inpaint` (the diffusers pipeline class for edits with a mask) and `image` (`max_edge`, `min_edge`, both required). A music model has `duration_arg` (required), `lyrics_arg` and `min_crest_db`. A video model has these keys, all required: `pipeline` (the diffusers class to load), `fps`, `size_multiple` (width and height are rounded to it), `frame_step` (frame counts are `frame_step * k + 1`), `width`, `height` (the default size) and `max_frames`. A presenter model has `pipeline`, `fps`, `buckets`, `audio_rate` and `output`, all required. A model id `local:<name>` names the entry `<name>` of the provider `local`. The template's comments give the meaning of each key.

## Model routes: routes.md

A route row names the model for some requests of a task. Per task, a `default` row names the recommended default model with its strengths and limits, and the other rows are escalations: another model for the requests their condition names. The table is `routes.md` in the directory of `config.yaml` (beside `$SKILLS_CONFIG` when that is set); no plugin update changes it. Its template is `${CLAUDE_SKILL_DIR}/assets/routes.md`, with wall times and quality notes measured on an NVIDIA GB10 for the `local` models of `config.example.yaml`.

The model in use is still `tasks.<task>`. Each model-calling skill's `routes` command prints, per task, the default row with the model of `tasks.<task>`, then the escalation rows. When `tasks.<task>` differs from the table's default model, the default row's `why` is `set in config.yaml; the table recommends <model>: <its why>`. Without `routes.md` the command prints only the defaults of `tasks.<task>` and says that the table is missing.

The file holds one Markdown table; text outside the table is ignored:

```markdown
| task | model | when | why |
|---|---|---|---|
| image | local:flux2-klein-4b | default | about 16 s per 2K image; misspells text |
| image | local:qwen-image | only when the image is an architecture diagram | labels spelled right |
```

- `task`: a task of the `tasks` section (`image`, `video`, `speech`, ...).
- `model`: `<provider name>:<model>` of `config.yaml`. A row whose model could not serve its task as `tasks.<task>` (provider missing or of another kind, a local model without an entry or of another role) is left out.
- `when`: `default`, or a condition beginning with `only when`. A task has at most one `default` row. To change the model in use, change `tasks.<task>`. The agent uses the default row and takes an escalation row only when its condition holds for the request; the first such row wins.
- `why`: strengths and limits (quality, wall time).

To add a row, create the file from the template when it is missing and add the row with Edit; put a more specific row above a general one of the same task. A malformed row makes the `routes` command fail with the file and line.

### Update routes.md from the template

When the user asks to update the routes, for example after a plugin update:

1. Read `${CLAUDE_SKILL_DIR}/assets/routes.md` and the user's `routes.md`.
2. List the template rows that the user's file lacks or holds with another `model`, `when` or `why`, matched by task and `when`. Show each to the user next to the user's row of that task and `when`, if any.
3. For each row the user accepts, Edit the user's file: replace the matched row, or add the row after the last row of its task. Keep every other user row as it is, including rows the template lacks.
