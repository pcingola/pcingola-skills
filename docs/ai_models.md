# ai_models

`lib/ai_models` (distribution `ai-models`) makes every model call of the skills (`docs/architecture.md`, One home
per concern). It has four parts:

1. Pydantic-AI: chat, vision, audio input, embeddings, image generation, image edits with reference images and
   System-1 models. The package reads the config and builds the Pydantic-AI object (`Agent`, `Embedder`,
   `ImageGenerator`, `SystemOneModel`); the call itself is Pydantic-AI's.
2. Adapters for what Pydantic-AI lacks: speech, music, video and image masks. One function per task, one branch per
   provider kind.
3. Local models with `diffusers`, in the caller's process: image, music and image-to-video models. The extra
   `ai-models[diffusers]` installs torch and diffusers, so only the skills that need it carry them.
4. Local speech and alignment (Local speech and alignment): Kokoro and the torchaudio aligner in the caller's
   process (extras `ai-models[kokoro]`, `ai-models[align]`), Chatterbox in a worker process of its own environment,
   Fish Audio Drama 3 in a vLLM-Omni server of its own environment.

| Module | Contents |
|---|---|
| `config` | the config file, `<provider>:<model>` ids, `model_for(task)`, `resolve(model, task)` |
| `routes` | the model routes table: `Route`, `parse`, `table`, `markdown`, `command` (Model routes) |
| `models` | the Pydantic-AI provider of each kind; `chat_model`, `agent`, `embedder` |
| `images` | `image_generator`, `MaskedOpenAIImageModel` |
| `system1` | `system1_model`, `decide` |
| `speech` | `speak`, `voices`, `check`, `fetch`, `model_of`, `model_of_kind`; `Traits` and `TRAITS` (what each kind's speech models take) |
| `kokoro` | `speak`, `voices` of a `kokoro` provider (Local speech and alignment) |
| `chatterbox` | `speak` of a `chatterbox` provider through `chatterbox_worker.py` (Local speech and alignment) |
| `align` | `aligner`: an `Aligner` of a `torchaudio` provider (Local speech and alignment) |
| `weights` | the weights directory of a provider (`dir`), `ensure_file` |
| `espeak` | the espeak-ng data path for Kokoro |
| `music` | `compose` |
| `video` | `animate`, `aanimate`, `present`, `apresent`; `frame_count`, `frame_size`, `clip_size`, `bucket` |
| `omni` | `aspeak` of a vLLM-Omni server (Speech models of vLLM-Omni) |
| `local` | `DiffusersImageModel`, `DiffusersMusicModel`, `animate` and `present` (video), the pipeline cache, the lock, memory check and cap, what holds the memory (Local model memory) |
| `tls` | the TLS context of remote clients |
| `errors` | `AIModelsError`, `ConfigError`, `explained` |

## Config

The config is the settings file of `plugin_settings` (`docs/plugin_settings.md`): `$SKILLS_CONFIG`, else
`<config dir>/plugins/data/config.yaml`, validated against its schema at load. `config.load()` returns the typed
`Config` of `plugin_settings.load_config()`, so the skills and the package use one file and one loader; a missing
file, or the message of `ConfigFileError`, is a `ConfigError`. `config.use(path)` sets another file for the process
(the tests use it). The template is `assets/config.example.yaml` of `setup:settings`, which creates the user's file.

The schema checks every key at load: the required keys of each provider kind and model class, and every
`tasks.<task>` against the kinds and diffusers role the task takes (`Config.task_error`, `TASK_KINDS`,
`TASK_ROLES`; docs/plugin_settings.md). `config.resolve` applies the same check to a model a caller names, so the
modules below do not check a provider's kind again. The functions of `config` look entries up and raise
`ConfigError` naming the YAML path to add:

| Function | Returns |
|---|---|
| `split_id(model_id)` | (provider name, model); the first colon splits, so `ollama:d3:4b` is the Ollama tag `d3:4b` |
| `model_for(task)`, `resolve(model, task)` | `tasks.<task>`; `resolve` returns `model` when given, after `Config.task_error` |
| `provider(name)` | the typed provider `providers.<name>` |
| `model_entry(model_id)` | `providers.<p>.models.<m>`, None when the provider has no entry for the model |
| `local_entry(model_id)` | the entry of a model of a local kind; `ConfigError` naming the key when it has none |
| `diffusers_model(model_id, role)` | the entry of a local diffusers model, of the class of `role` (`DiffusersRole`) |
| `image_limits(model_id, required=)` | `providers.<p>.models.<m>.image` (`OpenAIImageLimits` or `DiffusersImageLimits`); None for a kind outside `IMAGE_LIMIT_KINDS` or, unless `required`, a model without limits |

The package reads two sections, `providers` and `tasks`, and `network.extra_ca_cert` (TLS):

- `providers`: name to provider. Every provider has `kind`. `timeout` (seconds, default 600) applies to every
  request of a remote, `chatterbox` or `vllm-omni` provider.
- Keys come only from `api_key` (`RemoteProvider.key()`). The schema requires it for `openrouter`, `azure` and
  `openai` without `base_url`, and for `google` unless `vertex: true` with `credentials`, `project` or `location`;
  `azure` also needs `base_url` and `api_version`. A Vertex provider takes `credentials` (a service-account JSON
  file; without it, Application Default Credentials), `project` and `location`; its predict models (Lyria) still
  need `api_key`. `ollama` and `openai` with a `base_url` need no key and send a placeholder, so no client library
  reads its own environment variable. A 401 or 403 from a provider without `api_key` names
  `providers.<name>.api_key` and the config file.
- `providers.<p>.models`: model name to its attributes. For a remote provider it is optional and holds `image` (the
  limits of an image model of an OpenAI kind), `voice` and `voices` (a speech model) and, for `google`, `predict`
  (Music). A remote provider serves any model id. A provider of a local kind serves only the models listed; the
  `kokoro`, `chatterbox`, `torchaudio` and `vllm-omni` entries are in Local speech and alignment and Speech models of
  vLLM-Omni. A `diffusers` entry has `repo` (a Hugging Face repository, or a folder of a saved pipeline as an
  absolute or `~` path, loaded with no cache lookup), `steps`, `guidance` (optional: without it
  no `guidance_scale` is passed), `args` (optional: more pipeline call arguments, after steps and guidance and
  before the caller's) and `skip` (optional: pipeline components loaded as None), and the keys of its role, which
  make the role. An image model adds `inpaint` (the diffusers pipeline class for an edit with a mask, built over
  the loaded modules with `from_pipe`) and `image`. A music model adds `duration_arg` (required) and `lyrics_arg`,
  the pipeline call argument names for the length in seconds and the lyrics; a model without `lyrics_arg` takes no
  lyrics. It may add `min_crest_db` (`music.min_crest_db`), the crest factor in dB below which music `generate`
  sends the request again (docs/music.md). A video or presenter model adds the keys of the Video section.
- `tasks`: task to model id `<provider name>:<model>`. A caller passes its own id (a `--model` flag) or asks for a
  task and gets `tasks.<task>` (`config.resolve`). The tasks (`plugin_settings.Task`): `chat`, `vision`,
  `system1`, `embed`, `image`, `image_edit`, `image_best`, `image_multi_ref`, `speech`, `align`, `music`, `audio`,
  `video`, `presenter`, `film_critic`. The package has no model defaults.

The image-gen, music and short-video wrappers install the extra when the config has a provider of kind `diffusers`
(`docs/architecture.md`, CLI wrappers).

## Model routes

A model route says which model serves a request of a task. `routes` reads one Markdown table with the columns
`| task | model | when | why |`: the user's `routes.md`, in the directory of the config file (`routes.user_path()`:
`config.path().parent`, so it follows `SKILLS_CONFIG`). No plugin update writes it. setup:settings creates it from
its template `assets/routes.md`, next to `config.example.yaml`, and merges template changes that the user accepts.

`task` is a task of the `tasks` section. `model` is a `<provider>:<model>` id. `when` is `default` (the
recommended default model of the task) or a condition beginning with `only when` (an escalation). `why` gives the
model's strengths and limits (quality, wall time). Lines outside the table are ignored. The first table line is the
header; a wrong header, a row of another width, an empty `task`, `model` or `when`, any other `when`, a second
`default` row of a task, and a model that is not `<provider>:<model>` are each a `ConfigError` naming the file and
line.

`table(tasks)` returns, per task in order:

1. The default row. The model in use stays `tasks.<task>` of the config, so the row has that model. The table's
   default row gives the `why` when its model is the same; when it differs, `why` is
   `set in config.yaml; the table recommends <model>: <its why>`. Without a table default row, `why` is
   `set in config.yaml`; without `tasks.<task>`, there is no default row.
2. The escalation rows in file order, without the rows whose model is not configured: the provider is missing from
   `providers`, or, for a provider of kind `diffusers`, the model is missing from its `models`. For the other kinds the provider is enough; whether Ollama has pulled a tag or a cloud provider
   serves a model shows only at the call.

Without the file, `table` returns only the default rows of `tasks.<task>`. No code reads `when`: the agent uses the
default row, and takes a later row only when its condition holds for the request, the first such row. `markdown`
prints the rows as a table. `command(subparsers, tasks)` adds `routes [--task T]` to a skill's CLI; it prints the
table of the skill's tasks and returns 0, with a note on stderr when the file is missing (`missing_message`: the
path, and that setup:settings creates it), or prints the error and returns 1.

The skills with the command and their tasks: image-gen (`image`, `image_edit`, `image_best`, `image_multi_ref`),
music (`music`, `audio`), short-video (`video`, `presenter`), voiceover (`speech`), classify (`system1`, `chat`),
second-opinion (`chat`, `vision`). Each `SKILL.md` has a "Model routes" section with the same rule; the chosen model
goes to the call as `--model`. Skills that load image-gen (infographic, pptx-author, studio, video-effects) route
through image-gen, by the tier they ask for.

The template rows come from wall-time and quality measurements on an NVIDIA GB10 with the `local` models of
`config.example.yaml`. Each template default row names the config template's `tasks.<task>`
(`local:flux2-klein-4b` for `image`, `local:ltx-2.5` for `video`, `local:ace-step-sft` for `music`,
`kokoro:kokoro-v1.0` for `speech`). A user without one of the escalation models has that row dropped.

Sizes and wall times of the template's local models on the GB10 (crest factors of the music models: `docs/music.md`):

| Model | Weights | Wall time |
|---|---|---|
| `flux2-klein-4b` | | about 16 s per 2K image |
| `z-image-turbo` | | about 40 s per image |
| `qwen-image` | about 33 GB | |
| `ace-step-sft` | | about 12 s per 30 s clip |
| `ace-step` (turbo) | | about 2 s per 30 s clip |
| `ltx-video` | about 26 GB | about 1 min per 5 s clip |
| `ltx-2.5` | about 70 GB of the components it loads | |
| `kandinsky-6` | about 81 GB | |
| `kandinsky-s2v` | about 62 GB | |
| `kandinsky-s2v-lite` | about 24 GB | |
| Kokoro 82M (`kokoro`) | about 340 MB | |
| MMS_FA (`torchaudio`) | 1.26 GB | |
| Chatterbox Turbo (`chatterbox`) | about 3 GB | |
| Fish Audio Drama 3 (`vllm-omni`) | about 42 GB | |

A diffusers model downloads 4 to 90 GB of weights to the Hugging Face cache (`huggingface.home`).

## Provider kinds

| Kind | Pydantic-AI provider | Keys |
|---|---|---|
| `ollama` | `OllamaProvider` | `base_url` (default `http://localhost:11434/v1`) |
| `openrouter` | `OpenRouterProvider` | `api_key` |
| `openai` | `OpenAIProvider`; chat goes through Chat Completions (`openai-chat`), which every OpenAI-compatible server has | `base_url`, `api_key` (required without `base_url`) |
| `azure` | `AzureProvider` | `base_url` (the Azure endpoint), `api_version`, `api_key` |
| `google` | `GoogleProvider`, or `GoogleCloudProvider` (Vertex) with `vertex: true` | `api_key`, `base_url`; Vertex: `project`, `location`, `credentials` |
| `diffusers` | none; `local` | none |
| `kokoro` | none; `kokoro` | `dir`; per model `model_url`, `voices_url`, `langs` (Local speech and alignment) |
| `chatterbox` | none; `chatterbox` | `python`, `dir`, `start_timeout`, `timeout`; per model `url`, `files` (Local speech and alignment) |
| `torchaudio` | none; `align` | `dir`; per model `url` (Local speech and alignment) |
| `vllm-omni` | none; `omni` | `python`, `args`, `env`, `start_timeout`, `timeout`; per model `repo`, `deploy`, `memory`, `overhead`, `style` (Speech models of vLLM-Omni) |

What each kind serves (the Kinds column is `TASK_KINDS`, checked at load and by `config.resolve`):

| Task | Through | Kinds |
|---|---|---|
| chat, vision, audio, film_critic | Pydantic-AI `Agent` | `API_KINDS`: `ollama`, `openrouter`, `openai`, `azure`, `google` |
| embed | Pydantic-AI `Embedder` | `API_KINDS` |
| system1 | Pydantic-AI `SystemOneModel` on the provider's `base_url` (Ollama: `/v1/systemone`) | `API_KINDS`, with a `base_url` (an `ollama` provider's default, `OLLAMA_URL`) |
| image, image_edit | Pydantic-AI `OpenAIImageGenerationModel`, `GoogleImageGenerationModel`; `local.DiffusersImageModel` | `ollama`, `openrouter`, `openai`, `azure`, `google`, `diffusers` |
| image mask | `images.MaskedOpenAIImageModel`; the `inpaint` pipeline of a `diffusers` model | OpenAI kinds, `diffusers` |
| speech | `speech.speak`: the OpenAI SDK `audio.speech` of the provider's client, Google `generate_content`, `omni.aspeak`, `kokoro.speak` or `chatterbox.speak` (the last two in a worker thread) | OpenAI kinds, `google`, `vllm-omni`, `kokoro`, `chatterbox` |
| align | `align.aligner` | `torchaudio` |
| music | `music.compose`: Google predict or stream, or `local.DiffusersMusicModel` | `google`, `diffusers` |
| video | `video.animate`: `local.animate` (image to video) | `diffusers` |
| presenter | `video.present`: `local.present` (portrait and speech to video) | `diffusers` |

Remote clients are one `httpx2.AsyncClient` per provider object, with the provider's timeout and the context of
`tls`.

## Pydantic-AI and the adapters

Pydantic-AI covers chat, vision, audio input, structured output, embeddings, image generation and image edits with
reference images, and System-1 models. The package adds no retry policy of its own: the callers rely on
Pydantic-AI's errors (`ModelRateLimitError`, `ModelConnectionError`, `ContentFilterError`, ...) and decide what to
retry. `errors.explained(model_id)` wraps a call and turns three common failures into an `AIModelsError` with the
fix: a 401 or 403 from a provider without `api_key` (Config), an Ollama model that is not pulled (HTTP 404, "run
`ollama pull <model>`") and a provider that does not answer.

The adapters cover what Pydantic-AI has no call for:

- Mask. Pydantic-AI's `OpenAIImageGenerationModel` sends no mask. `MaskedOpenAIImageModel` subclasses it and gives it
  a client whose `images.edit` adds the mask (PNG, transparent where the image may change). A mask without a
  reference image is refused. The `google` kind takes no mask (`ConfigError`).
- Speech. The OpenAI kinds call `audio.speech.create` on the Pydantic-AI provider's OpenAI client, with the style as
  `instructions` and a speed other than 1 (a server may refuse it; Ollama does). `google` calls `generate_content`
  with an AUDIO response and a prebuilt voice, with the style as a text prefix the model does not speak; raw PCM comes
  back as a WAV file at the rate of its MIME type. The `google` kind has no speed setting.
- Music. A model with `predict: true` in the provider's `models` gets a plain `:predict` POST on the provider's `base_url`
  (default Vertex), with `sample_count` inside the instance, where the API honours it; one WAV per sample. Other
  models of the `google` kind stream with
  AUDIO and TEXT parts; length and lyrics go in the prompt, images as parts after it, and the text parts come back
  with the MP3. A server may end the stream with a `[DONE]` line the SDK cannot parse: it is ignored once audio
  arrived, and a stream without audio is tried again, 3 attempts in all. `music.TAKES` lists the options of each model
  kind (`diffusers`, `predict`, `stream`); another option is refused before any request.
- Local models (`local`). `DiffusersImageModel` is a Pydantic-AI `ImageGenerationModel`; `DiffusersMusicModel` gives
  a WAV file; `animate` gives an MP4 (Video). Pipelines load in bfloat16 with `DiffusionPipeline.from_pretrained`,
  or with the class a model's `pipeline` names, from the cached snapshot folder when the Hugging Face cache has
  one (a load by repository id fetches every weight file of each component folder, including shardings the
  pipeline never reads), on CUDA, else MPS, else an error, and stay loaded for the life of the process. `from_pretrained` leaves the weights memory-mapped from the safetensors
  files; `to_device` copies each one to process memory before the move to the GPU, because a host-to-device copy
  from a file mapping is about 100 times slower on a unified-memory GPU (GB10: 87 s against under 2 s for FLUX.2
  klein 4B). Weights go to the Hugging Face cache. torch and diffusers are imported
  only in this module.

## Local model memory

A diffusers pipeline runs in the caller's process and keeps its weights for the life of that process. Skills run
model commands in parallel (parallel tool calls, one subagent per scene), and Ollama keeps a model resident for
5 minutes after its last call. On a unified-memory GPU, allocations past the free memory exhaust system memory and
the machine hangs without an error. `local.pipeline` therefore does four things before a load:

- Lock. The first load of a process takes an exclusive `filelock.FileLock` on `ai-models-local.lock` in the system
  temporary directory (`tempfile.gettempdir()`) and holds it until the process exits; the OS releases it then,
  also after a crash. Every skill environment and plugin shares the file, so one process at a time holds local
  models and the others wait without a time limit, so parallel commands queue behind a render. The holder writes
  its PID to `ai-models-local.pid` beside the lock, and the waiter's stderr line names it, so a stuck holder can be
  found. A process that has loaded a model keeps the lock until it exits, also while it does other work; a load
  that fails while the process has no pipeline releases it. One `threading.RLock` serialises loads within a
  process, so worker threads (`asyncio.to_thread`) share one lock.
- Handover. The OS releases the lock file before the holder has exited, and the holder's device memory comes
  back after that. On a GB10, a waiter that got the lock from a holder of a 60 GB CUDA tensor read 65.5 GB free
  for 0.5 s and 126.9 GB 1 s after, so a 70 GB load right after the handover is refused. A process that waited for the lock
  therefore waits up to `SETTLE_SECONDS` for the PID in the PID file to exit (gone, or a zombie), and a check that
  then fails reads the free memory again every `SETTLE_POLL_SECONDS` for up to `SETTLE_SECONDS`
  (`wait_for_memory`) and sets the cap again from the last reading before the check.
- Check. After `from_pretrained` and before any weight moves to the device, the bytes of every parameter and
  buffer of the pipeline's torch modules (`weight_bytes`) are compared with the device's free memory
  (`free_memory`), read before the load, because a load that converts dtypes holds the weights in process memory
  until the move. Weights over the free memory raise `AIModelsError` (`memory_error`) with the model, both sizes in
  GB and what holds the memory (`memory_holders`, Speech models of vLLM-Omni).
- Cap. On CUDA, `torch.cuda.set_per_process_memory_fraction((free + memory_reserved) / total)` is set before each
  load (`cap_memory`). Growth during a load or call then raises `torch.OutOfMemoryError`, which `out_of_memory`
  turns into the same kind of `AIModelsError`, instead of taking memory other processes need. MPS has its own
  limit (`PYTORCH_MPS_HIGH_WATERMARK_RATIO`).

Free memory: on CUDA `torch.cuda.mem_get_info()`; on MPS `torch.mps.recommended_max_memory()` minus
`torch.mps.driver_allocated_memory()`, at most the system's available memory (`psutil.virtual_memory().available`),
because the driver figure counts only this process. On an integrated CUDA GPU under Linux (`is_integrated` in the
device properties) it is the system's available memory (`MemAvailable` of `/proc/meminfo`): the device allocates system memory and reclaims the page
cache, but `mem_get_info()` reports `MemFree` and counts the page cache as used. On a GB10, after 34 GB of
safetensors files were read, `mem_get_info()` reported 83 GB free and `MemAvailable` 125 GB, and a 102 GB CUDA
allocation succeeded.

## Local speech and alignment

A speech model's entry (`providers.<p>.models.<m>`, any class deriving `Voices`) takes `voice` (its default voice;
else the kind's, `speech.TRAITS`, whose keys are `SPEECH_KINDS`) and `voices` (the list `speech.voices` returns;
without it a `kokoro` model lists its voices and the others their default voice). `speech.SpeechModel` carries the
provider and the entry (None for a remote model without one).
`speech.check` refuses a speed outside the kind's range, instructions a kind does not take, and `params` of a kind
that takes none or that name a field the request is built with (`omni.BUILT_FIELDS`), before any request or model
load; `speak` calls it. `speech.model_of_kind(kind)` is the configured speech model of a provider kind:
`tasks.speech` when its provider has the kind, else the first speech routes row of such a provider, else None
(media:short-video and Studio map the voice `backend` field of an earlier storyboard with it). `aspeak` runs Kokoro and Chatterbox in a
worker thread (`asyncio.to_thread`), so they do not block the event loop; one lock per kind serializes a model load
or a worker request.

The `kokoro`, `chatterbox` and `torchaudio` kinds keep the files of model `<model>` in `<dir>/<model lowercased>/`
(`weights.model_dir`): `dir` of the provider, else the `weights_dir` the caller passes to `speech.speak`,
`speech.voices`, `speech.fetch`, `speech.model_of` or `align.aligner` (`WeightsDir.with_dir`; media:voiceover passes
`voiceover/` of its plugin data directory); without either, a `ConfigError` asks for `dir`. Two
providers with the same `dir` and model share the files. `weights.ensure_file` downloads a missing file to
`<file>.part`, checks its length against Content-Length and renames it, so a failed download leaves no file under the
final name; it uses the TLS context of `tls`. `speech.fetch` downloads the files of a `kokoro` or `chatterbox` model.

- `kokoro`: kokoro-onnx in the caller's process on the CPU (extra `ai-models[kokoro]`), no local-model lock. The
  model entry's (`KokoroModel`) `model_url` and `voices_url` are the ONNX model and the voices file (the kokoro-onnx GitHub release); `langs` maps a voice-name
  prefix to the espeak-ng language it is phonemized with, and a voice of no listed prefix is refused. One model per
  model file stays loaded for the life of the process. The answer is a 24 kHz WAV file; speed 0.5 to 2 (kokoro-onnx's
  limit); no instructions. espeak-ng keeps its data path in a 160-byte buffer and fails on a longer one, so when the
  `espeak-ng-data` path bundled in `espeakng_loader` is 150 characters or longer, `espeak.data_path` passes a copy at
  `<dir>/espeak-ng-data`, else in the temporary directory.
- `chatterbox`: Chatterbox Turbo, zero-shot voice cloning. chatterbox-tts 0.1.7 pins torch and torchaudio 2.6, so it
  runs in its own environment (`python` of the provider; media:voiceover's `setup --chatterbox` builds one from its
  locked uv project `scripts/chatterbox`), in one worker process per model and calling process (`chatterbox_worker.py`, run as
  `python -I chatterbox_worker.py <model dir>`; it imports nothing of `ai_models`). The worker loads the model on the
  CPU, sets `HF_HUB_OFFLINE=1` (the weights are local; `plugin_settings` removed any shell value), and answers JSON request lines on stdin with JSON
  lines on a copy of stdout; its own stdout goes to stderr, which goes to a log file an error quotes. It stops at exit
  (`atexit`, stdin closed, killed after 30 s; the log's directory is removed after a clean exit); when the caller
  dies, its stdin reaches its end and its request loop ends. A thread reads its answers, so a
  wait has a limit: `start_timeout` for the load and `timeout` per answer (seconds, default 600 each, of the
  provider). The model entry's (`ChatterboxModel`) `url` and `files` name the model files (the template: the ModelScope mirror of Resemble AI's repository). A voice is `default` (the built-in
  voice) or the path of a recording longer than 5 s. Under numpy 2, Chatterbox's `norm_loudness` multiplies the
  float32 reference by a float64 gain and returns float64 (NEP 50 promotion), which its mel filter matmul rejects; the
  worker casts the result to float32. The answer is a 24 kHz WAV file with Resemble's Perth watermark; no speed, no
  instructions.
- `torchaudio`: a forced-alignment pipeline of `torchaudio.pipelines` by name (`torchaudio:MMS_FA`), task `align`, in
  the caller's process on the CPU (extra `ai-models[align]`, torchaudio 2.11, the last release with `forced_align`).
  The model entry's (`TorchaudioModel`) `url` is the pipeline's weights file: `weights.ensure_file` downloads it (TLS context of `tls`, so
  `network.extra_ca_cert` applies) into the model directory under its own file name, the name torch.hub looks for, and the
  pipeline loads it from there (`get_model(dl_kwargs={"model_dir": ...})`), so torch.hub downloads nothing. `Aligner.align(samples, rate, tokens)` resamples to the pipeline's
  rate and returns one (start, end) in seconds per token. One aligner per model id stays loaded for the life of the
  process.

## Speech models of vLLM-Omni

Fish Audio Drama 3 runs only through vLLM-Omni (or SGLang-Omni), which pins torch 2.14.0 and transformers below
5.20; the skill environments have torch 2.14.1 and transformers 5.23. It therefore runs in its own environment,
in a separate process. A provider of kind `vllm-omni` names that environment's interpreter (`python`), the server's
`args` and `env`, and the time limits; each model entry (`VllmOmniModel`) names the model (`repo`), its `deploy`
config, `memory`, `overhead` and `style`. One server per model id serves for the life of the process.
`omni.aspeak`:

1. On the first call of the process, makes SIGTERM raise `SystemExit` (`exit_on_sigterm`, so step 5 runs after a
   SIGTERM), takes the local-model lock (`local.hold_lock`, Local model memory) and reads the free memory
   (`local.free_memory`). After waiting for the lock, it reads the free memory until it stops rising
   (`local.wait_for_settled_memory`: a rise under 0.5 GB between readings 0.5 s apart, at most 10 s), while the
   previous holder's memory comes back, and when that is short of the need, reads it again for up to
   `SETTLE_SECONDS` (`local.wait_for_memory`). vLLM 0.32 checks each stage's budget against the same figure: on an
   integrated GPU `MemAvailable` (`MemorySnapshot.measure`), elsewhere `mem_get_info()`. The start needs the
   model's `memory` (GB, the stages' budgets together) plus `overhead` (GB the server takes outside `memory`,
   default `DEFAULT_OVERHEAD_GB`, 22). When less is free and local Ollama models hold the shortfall, it waits for
   Ollama to unload them (`local.wait_for_ollama`, below). When the memory is still short, the start is refused
   before the server runs (`local.memory_error`), with both sizes and what holds the memory
   (`local.memory_holders`):
   - the models of each `ollama` provider whose host is this machine (`localhost` or a loopback address), with the
     time Ollama unloads each (`GET /api/ps`, `expires_at`);
   - the processes holding the most memory of this GPU (`nvidia-smi --query-compute-apps`, filtered by the device's
     `gpu_uuid`) and, on an integrated GPU, whose CPU memory comes from the same pool, the processes with the
     largest resident set; Ollama's runners are left out when its models are listed.

   It unloads nothing. `local.wait_for_ollama` waits only when the models Ollama unloads within
   `OLLAMA_WAIT_SECONDS` (15 min) hold the shortfall: their sizes, or the memory of Ollama's runners on this GPU when
   every loaded model unloads in that time (a runner holds more than its model's size: 58 GB for a 35 GB model). It
   prints a line on stderr, reads the free memory every 5 s and the unload times again (another program's request
   moves them), and stops when the free memory suffices or `SETTLE_SECONDS` after the last unload time.

   `overhead` is the host memory of the API server and the stage processes plus device memory past the stages'
   budgets (CUDA contexts and the CUDA graph pool, see below). On the GB10, Drama 3 with `memory: 70` took 18.7,
   19.6 and 19.9 GB more than `memory` at its peak over a start and two requests (resident sets of the server's processes
   plus their GPU memory, sampled every second: 14.6 to 15.6 GB of host memory and 73.5 to 74.4 GB of GPU memory), and
   `MemAvailable` fell 18.8 and 19.8 GB more than `memory` in two starts with nothing else loading. The default
   adds 2 GB to the largest. On an integrated GPU, past the free memory the kernel's out-of-memory killer acts
   on the whole pool.
2. Writes a deploy overlay that inherits `deploy` (a file of vLLM-Omni's `deploy/` directory, found with the
   environment's `importlib.util.find_spec`, or a path) through vLLM-Omni's `base_config`. The overlay turns off
   the CUDA MPS daemon (`platforms.cuda.cuda_mps: false`) and scales every stage's `gpu_memory_utilization` so
   that their sum is `memory` over the device total (`mem_get_info()[1]`), in the deploy config's proportions
   (Drama 3: 0.78 and 0.1). Without MPS the two stages share one GPU by time-slicing.

   vLLM sizes a stage's KV cache as its budget minus its weights, activation peak, other allocations measured
   on the device during profiling and, by default, an estimate of the CUDA graph pool; a stage with no KV cache
   fails ("No available memory for the cache blocks") after the weights have loaded. Drama 3's first stage needs
   about 46.5 GiB besides its KV cache (37.5 GiB of weights). With a budget of 0.6 of the free memory, read on an
   integrated GPU from `mem_get_info()`, 9 of 31 starts on the GB10 failed, and in every logged start the KV cache
   came out as the first stage's budget minus 46.5 GiB within 1 GiB. 6 of the failures had a first-stage budget
   under 47 GiB, measured while Ollama held models or while the page cache was large; 1 lost 17.7 GiB to the graph
   estimate (below); in 2 the second stage hit a CUDA out-of-memory error as it started, with first-stage budgets
   of 50 and 83 GiB. With `memory: 70` the first stage gets 57.8 GiB and a KV cache of 11.3 to 13.1 GiB.

   Results on the GB10 with `memory: 70`, an `overhead` of 19 to 22 GB and the Ollama wait: of 8 starts with no
   Ollama model loaded at the start (one with 113 GB of page cache), 7 came up and 1 failed at the second stage's
   first CUDA call (step 3). The 7, and the 3 below, ran with the page cache of the model files dropped every 2 s
   during the start, which this code does not do. In one of the 7, another program loaded
   38 GB of Ollama models during the start and `MemAvailable` fell to 5.4 GB. 3 starts began while Ollama held
   models: 2 with 38 GB of another program's models (one with 76 GB of page cache), 1 with a 35 GB model on a
   3 min keep-alive; each waited 3 to 5 min for Ollama to unload them and came up. With the 35 GB model kept for
   20 min, the start was refused in 1 s with the model named.

   On an integrated GPU the server's environment has `VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS=0` unless the
   provider's `env` sets it (`omni.INTEGRATED_ENV`). vLLM-Omni estimates the CUDA graph pool from
   `mem_get_info()` deltas, which on an integrated GPU also move with the page cache and with other processes:
   Drama 3 starts measured 0.2 to 3.3 GiB, and one 17.7 GiB, which left a 56 GiB stage with no KV cache. Without
   the estimate the graph pool is allocated outside the budget and counts in `overhead`.
3. Starts `vllm serve <repo> --omni --deploy-config <overlay>` plus the provider's `args` on a free loopback port,
   with the provider's `env` added to the environment, in its own process group with `PR_SET_PDEATHSIG`, and polls
   `/health` every 2 s until `start_timeout` (default 1800 s). One start failed with a CUDA out-of-memory error at
   the second stage's first CUDA call (`mem_get_info()` in `MemorySnapshot`) while `MemAvailable` stayed at or
   above 57.7 GB, so that error does not come from the overhead; its cause is not known. CUDA allocations reclaim
   the page cache: with 108 GB of cache and 10.5 GB `MemFree`, a 90 GB allocation succeeded.

   When the server exits during the start, its whole log is classified (`omni.start_failure`; the error quotes
   only the last `LOG_TAIL` characters). `StartFailure.KV_CACHE` (no memory for the cache blocks) gives
   `local.memory_error` with the advice to raise `memory`; `StartFailure.OUT_OF_MEMORY` (a CUDA or torch
   out-of-memory error, or vLLM's free memory check) the advice to free memory or lower `memory`. A CUDA
   out-of-memory error at this process's first CUDA calls (`omni.context_out_of_memory`) gives `local.memory_error`
   with the advice to free memory. The start runs in the calling thread, the event loop's, and blocks the loop while the model loads:
   `PR_SET_PDEATHSIG` stops the server when the thread that started it exits, and the loop's thread lives as long
   as the caller.
4. Sends each request asynchronously (`httpx.AsyncClient`) to `POST /v1/audio/speech` (`response_format: wav`; the
   audio comes at the model's rate, since Drama 3 refuses `sample_rate`).
5. Stops the server at exit (`atexit`, `Server.stop`): SIGTERM to the group, a wait of up to 30 s for the main
   process and then up to 30 s for the rest of the group (the stage workers, polled with `killpg(pgid, 0)`), then
   SIGKILL to the group. The kernel sends SIGTERM to the main process when the caller dies (`PR_SET_PDEATHSIG`);
   that signal does not reach the stage workers.

On the GB10 (sm_121), Drama 3 needs three settings, all in config: `--safetensors-load-strategy eager` (the
default memory-mapped load took 18 s per 2.5 GB shard, 4.5 min in all, past vLLM-Omni's 300 s stage start limit;
eager took 34 s), `--stage-init-timeout 1800`, and `VLLM_USE_FLASHINFER_SAMPLER=0` (FlashInfer has no prebuilt
sampling kernel for sm_121 and JIT-compiles it with nvcc, which is not installed). vllm-omni 0.32.0 needs vllm
0.32 (with vllm 0.33 its CLI fails on `vllm.entrypoints.launchers.cli_args`).

The server lives for one command, like a diffusers pipeline. The package does not use the in-process `Omni` class:
it needs the model's prompt layout in the caller's code (vLLM-Omni's TTS adapter builds it for the server, per
architecture).

Voice: `default` (the model's own voice), or a path to a reference recording with its transcript in a `.txt` file
of the same stem, sent as `ref_audio` (a `data:` URI) and `ref_text`. Drama 3 picks a new speaker for each
request without a reference. A fixed `seed` (the request field exists) does not keep it: on the GB10 three
sentences with seed 7 had median F0 184, 146 and 135 Hz, with seed 11 203, 146 and 208 Hz, without a seed 110,
184 and 191 Hz. With `default`, `omni.aspeak` therefore keeps the model's first answer in the process (`first_take`, by model id: WAV and
the text sent) and sends it as `ref_audio`/`ref_text` with every later `default` request; three sentences then
had 138, 138 and 148 Hz and a mean log-mel profile within cosine 0.975 of the first. The first take is kept per
`speaker` (a caller's name for who speaks; None for one voice), so each speaker of a dialogue keeps its own voice.
Instructions go through the model's `style`, a format string with `{instructions}` and `{text}` (Drama 3:
`"[{instructions}] {text}"`, its inline tags); a model without `style` refuses instructions. There is no speed.

The text goes to the server as given, with its inline tags (`Traits.tags`): point tags in square brackets anywhere
and speaker tags `<|speaker:0|>` to `<|speaker:15|>`, which the Drama 3 prompt keeps (the reference is speaker 0).
`params` are more request fields added to the built body (`request_body`; a field it builds itself, `BUILT_FIELDS`,
is refused; `Traits.params`; the OpenAI kinds get them as `extra_body`). vLLM-Omni 0.32's speech request reads `seed`, `max_new_tokens` and `extra_params` (its
`temperature`, `top_p` and `top_k` set the sampling of stage 0) and ignores unknown fields. Its Drama 3 adapter
takes one reference per request (`ref_audio` and `ref_text`, or `ref_audio_codes`); the model card's
`previous_takes` and several references belong to SGLang-Omni's `/v1/tts`.

## Video

`video.animate(image, prompt, *, seconds, model=None, width=None, height=None, aspect=None, seed=None)` returns an MP4 of the
image animated as the prompt says; `aanimate` runs it in a worker thread. The model is `model`, else `tasks.video`.
Only the `diffusers` kind serves video. A video model is a `providers.<p>.models.<name>` entry of a `diffusers`
provider of the video role (`DiffusersVideoModel`) with these keys besides `repo`, `steps` and `guidance`, all
required; the schema names each missing one at load, and `config.resolve` refuses a model of another kind or role:

| Key | Meaning |
|---|---|
| `pipeline` | the diffusers class to load; needed because `DiffusionPipeline.from_pretrained` returns the class of the repository's `model_index.json`, which can be text to video |
| `fps` | frames per second of the clip, passed to the encoder |
| `size_multiple` | width and height are rounded to the nearest multiple of it, at least the multiple |
| `frame_step` | the frame count is the smallest `frame_step * k + 1` (k >= 1) that covers `seconds * fps` |
| `width`, `height` | size when the caller gives none; with `aspect` (width / height), reshaped to that ratio at the same pixel count (`video.clip_size`) |
| `max_frames` | the longest clip; a longer request is cut to it |

The frame count is cut to `max_frames`, rounded down to the `frame_step * k + 1` form.

The image is cropped to the clip's aspect ratio and scaled to its size (`ImageOps.fit`). The frames are encoded with
diffusers' `encode_video` (PyAV, H.264). A pipeline whose output has `audio` (LTX-2 generates a sound track with the
frames) gets it muxed in as an AAC stereo stream at the rate `local.audio_rate` reads from the pipeline: its vocoder
config's `output_sampling_rate`, else `sampling_rate`, else the pipeline's `audio_sample_rate` (Kandinsky 6), else its
`sample_rate`. The track may be (channels, samples) or (samples,) per video, a tensor or a NumPy array
(`local.waveform`). A pipeline without `audio`
gives a clip without an audio stream. The caller decides what to do with the track (media:short-video mixes it under
the narration as ambience). The `diffusers` extra installs `av` for the encoder; some image-to-video pipelines also
need it to re-encode their conditioning image.

`video.present(image, speech, *, model=None, aspect=None, prompt=None, seed=None)` returns an MP4 of the person in
the image speaking `speech` (an audio file), as long as the speech, with the speech muxed in as AAC at the file's
sample rate; `apresent` runs it in a worker thread. The model is `model`, else `tasks.presenter`, a
`providers.<p>.models.<name>` entry of a `diffusers` provider with optional `steps`, `guidance`, `args` and `skip`,
and these keys, all required (`DiffusersPresenterModel`; checked at load as for video):

| Key | Meaning |
|---|---|
| `pipeline` | the diffusers class to load, a `DiffusionPipeline` or a `ModularPipeline` class |
| `fps` | frames per second of the clip |
| `buckets` | the frame sizes the model makes, a list of `[width, height]`; the clip takes the one nearest `aspect` on a log scale (`video.bucket`), default the image's aspect |
| `audio_rate` | the sample rate the model takes the speech at; the speech goes to the model mono at this rate |
| `output` | the pipeline output that holds the videos (a modular pipeline's `output=` argument) |

PyAV decodes and resamples the speech (`local.read_audio`). The image is cropped to the bucket (`ImageOps.fit`,
biased upward to keep the head, `local.presenter_still`) and passed with its `width` and `height`; `prompt`, when given, replaces the pipeline's default prompt.

`local.pipeline` loads a `ModularPipeline` class (`modular_model_index.json`, Kandinsky S2V) with `from_pretrained`
then `load_components(dtype=bfloat16)` of every component outside `skip`, under the same lock, memory check of the
loaded components' weights and CUDA cap as a `DiffusionPipeline`. diffusers 0.43 is the first release with the
Kandinsky S2V modular pipeline.

The models, their repositories and these keys are in `config.yaml`; `config.example.yaml` has a real model and a
minimal test model. The presenter test (`tests/integration/ai_models/test_video.py`) uses
`kandinskylab/tiny-kandinsky-s2v-distilled-modular-pipe` (32 MB, random weights, the diffusers test fixture); its text
RoPE has 128 positions, so its config passes a short `prompt` in `args`.

## TLS

A machine behind a TLS-intercepting proxy can set `network.ca_bundle` (`SSL_CERT_FILE`) to the proxy CA alone, which replaces the public
root bundle and breaks verification of public endpoints. `tls` therefore starts from certifi's roots and adds the
extra CA `network.extra_ca_cert` (`tls.ca_cert()`, `docs/plugin_settings.md`). The default
verify flags stay on, `VERIFY_X509_STRICT` included.

`PYDANTIC_AI_NO_BANNER` is set on import unless already set, because the skills' output is read by programs.
