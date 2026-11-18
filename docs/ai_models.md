# ai_models

`lib/ai_models` (distribution `ai-models`) makes every model call of the skills (`docs/architecture.md`, One home
per concern). It has four parts:

1. Pydantic-AI: chat, vision, audio input, embeddings, image generation, image edits with reference images and
   System-1 models. The package reads the config and builds the Pydantic-AI object (`Agent`, `Embedder`,
   `ImageGenerator`, `SystemOneModel`); the call itself is Pydantic-AI's.
2. Adapters for what Pydantic-AI lacks: speech, music, video and image masks. One function per task, one branch per
   provider kind. The remote speech and music calls are the documented exceptions to Pydantic-AI
   (`docs/architecture.md`, Standard paths for model calls).
3. Local models with `diffusers`, in the caller's process: image, music and image-to-video models. The extra
   `ai-models[diffusers]` installs torch and diffusers, so only the skills that need it carry them.
4. Local speech and alignment (Local speech and alignment), in the caller's process: Kokoro, Chatterbox Turbo and
   the torchaudio aligner on the CPU (extras `ai-models[kokoro]`, `ai-models[chatterbox]`, `ai-models[align]`), Fish
   Audio Drama 3 on an NVIDIA GPU through fish-speech (Fish; media:voiceover's `cuda` extra installs it).

| Module | Contents |
|---|---|
| `config` | the config file, `<provider>:<model>` ids, `model_for(task)`, `resolve(model, task)` |
| `routes` | the model routes table: `Route`, `parse`, `table`, `markdown`, `command` (Model routes) |
| `models` | the Pydantic-AI provider of each kind; `chat_model`, `agent`, `embedder` |
| `images` | `image_generator`, `MaskedOpenAIImageModel` |
| `system1` | `system1_model`, `decide` |
| `speech` | `speak`, `voices`, `check`, `fetch`, `model_of`, `model_of_kind`; `Traits` and `TRAITS` (what each kind's speech models take) |
| `kokoro` | `speak`, `voices` of a `kokoro` provider (Local speech and alignment) |
| `chatterbox` | `speak` of a `chatterbox` provider (Local speech and alignment) |
| `cpu` | `performance_threads`: torch's CPU threads on the fast cores (Local speech and alignment) |
| `fish` | `speak` of a `fish` provider; `fish_span` (`split_spans`), `fish_take` (`Take`), `fish_takes` (`Takes`) (Fish) |
| `align` | `aligner`: an `Aligner` of a `torchaudio` provider (Local speech and alignment) |
| `weights` | the weights directory of a provider (`dir`), `ensure_file` |
| `espeak` | the espeak-ng data path for Kokoro |
| `music` | `compose` |
| `video` | `animate`, `aanimate`, `present`, `apresent`; `frame_count`, `frame_size`, `clip_size`, `bucket` |
| `local` | `DiffusersImageModel`, `DiffusersMusicModel`, `animate` and `present` (video), the pipeline cache, the lock, `unload`, memory check and cap, what holds the memory (Local model memory) |
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

The package reads two sections, `providers` and `tasks`, `network.extra_ca_cert` (TLS) and `local_models.lock_wait`
(Local model memory):

- `providers`: name to provider. Every provider has `kind`. `timeout` (seconds, default 600) applies to every
  request of a remote provider.
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
  `kokoro`, `chatterbox` and `torchaudio` entries are in Local speech and alignment, the `fish` entry in Fish. A
  `diffusers` entry has `repo` (a Hugging Face repository, or a folder of a saved pipeline as an
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
| Fish Audio Drama 3 (`fish`) | 39 GB; 44 GB at its peak | load about 4 min; about 5 s of speech in 4 to 9 s |

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
| `chatterbox` | none; `chatterbox` | `dir`; per model `url`, `files` (Local speech and alignment) |
| `torchaudio` | none; `align` | `dir`; per model `url` (Local speech and alignment) |
| `fish` | none; `fish` | none; per model `repo`, `memory`, `style`, `max_frames` (Fish) |

What each kind serves (the Kinds column is `TASK_KINDS`, checked at load and by `config.resolve`):

| Task | Through | Kinds |
|---|---|---|
| chat, vision, audio, film_critic | Pydantic-AI `Agent` | `API_KINDS`: `ollama`, `openrouter`, `openai`, `azure`, `google` |
| embed | Pydantic-AI `Embedder` | `API_KINDS` |
| system1 | Pydantic-AI `SystemOneModel` on the provider's `base_url` (Ollama: `/v1/systemone`) | `API_KINDS`, with a `base_url` (an `ollama` provider's default, `OLLAMA_URL`) |
| image, image_edit | Pydantic-AI `OpenAIImageGenerationModel`, `GoogleImageGenerationModel`; `local.DiffusersImageModel` | `ollama`, `openrouter`, `openai`, `azure`, `google`, `diffusers` |
| image mask | `images.MaskedOpenAIImageModel`; the `inpaint` pipeline of a `diffusers` model | OpenAI kinds, `diffusers` |
| speech | `speech.speak`: the OpenAI SDK `audio.speech` of the provider's client, Google `generate_content`, `fish.speak`, `kokoro.speak` or `chatterbox.speak` (the last three in a worker thread) | OpenAI kinds, `google`, `fish`, `kokoro`, `chatterbox` |
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
- Speech, a documented exception (Pydantic-AI has no text-to-speech API). The OpenAI kinds call `audio.speech.create` on the Pydantic-AI provider's OpenAI client, with the style as
  `instructions` and a speed other than 1 (a server may refuse it; Ollama does). `google` calls `generate_content`
  with an AUDIO response and a prebuilt voice, with the style as a text prefix the model does not speak; raw PCM comes
  back as a WAV file at the rate of its MIME type. The `google` kind has no speed setting.
- Music, a documented exception (Pydantic-AI has no music API). A model with `predict: true` in the provider's `models` gets a plain `:predict` POST on the provider's `base_url`
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
  klein 4B). Weights go to the Hugging Face cache. diffusers is imported only in this module; torch also in
  `fish`, `cpu` and `align`.

## Local model memory

A diffusers pipeline or a Fish model runs in the caller's process and keeps its weights until that process exits or
calls `unload`. Skills run
model commands in parallel (parallel tool calls, one subagent per scene), and Ollama keeps a model resident for
5 minutes after its last call. On a unified-memory GPU, allocations past the free memory exhaust system memory and
the machine hangs without an error. `local.pipeline` therefore does four things before a load (`fish` the same, with
the model's `memory` in place of the weights it counts):

- Lock. The first load of a process takes an exclusive `filelock.FileLock` on `ai-models-local.lock` in the system
  temporary directory (`tempfile.gettempdir()`) and holds it until the process exits; the OS releases it then,
  also after a crash. Every skill environment and plugin shares the file, so one process at a time holds local
  models and parallel commands queue behind a render. The wait has no limit unless `local_models.lock_wait` sets
  one (seconds); past it, `hold_lock` raises `AIModelsError` naming the holder's PID, the lock file and the setting.
  The holder writes its PID to `ai-models-local.pid` beside the lock, and the waiter's stderr line names it, so a
  stuck holder can be found. A process that has loaded a model keeps the lock until it exits or calls `unload`,
  also while it does other work; a load that fails while the process has no model loaded releases it. One
  `threading.RLock` serialises loads within a process, so worker threads (`asyncio.to_thread`) share one lock.
- Unload. `local.unload()` empties every cache registered with `local.on_unload` (an object with `__len__` and
  `clear`: the diffusers pipelines, Kokoro, Chatterbox, Fish and its first takes, the aligners), empties the PID
  file and releases the lock, so a waiting process loads at once without waiting for this one to exit. When the
  process held the lock or a cache held an entry, it also collects garbage and empties the CUDA allocator cache
  when torch is imported; otherwise it returns at once (0.15 s per call saved after torch is imported). The
  integration tests call it after each test.
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
  GB and what holds the memory (`memory_holders`, below).
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

What holds the memory (`memory_holders`), named in every memory error:

- the models of each `ollama` provider whose host is this machine (`localhost` or a loopback address), with the
  time Ollama unloads each (`GET /api/ps`, `expires_at`; a documented exception to Pydantic-AI, which has no call
  for it);
- the processes holding the most memory of this GPU (`nvidia-smi --query-compute-apps`, filtered by the device's
  `gpu_uuid`) and, on an integrated GPU, whose CPU memory comes from the same pool, the processes with the largest
  resident set; Ollama's runners are left out when its models are listed.

A Fish load short of memory first waits for Ollama (`local.wait_for_ollama`). It waits only when the models Ollama
unloads within `OLLAMA_WAIT_SECONDS` (15 min) hold the shortfall: their sizes, or the memory of Ollama's runners on
this GPU when every loaded model unloads in that time (a runner holds more than its model's size: 58 GB for a 35 GB
model). It prints a line on stderr, reads the free memory every 5 s and the unload times again (another program's
request moves them), and stops when the free memory suffices or `SETTLE_SECONDS` after the last unload time. It
unloads nothing.

## Local speech and alignment

A speech model's entry (`providers.<p>.models.<m>`, any class deriving `Voices`) takes `voice` (its default voice;
else the kind's, `speech.TRAITS`, whose keys are `SPEECH_KINDS`) and `voices` (the list `speech.voices` returns;
without it a `kokoro` model lists its voices and the others their default voice). `speech.SpeechModel` carries the
provider and the entry (None for a remote model without one).
`speech.check` refuses a speed outside the kind's range, instructions a kind does not take, and `params` of a kind
that takes none, before any request or model load; `speak` calls it. `speech.model_of_kind(kind)` is the configured speech model of a provider kind:
`tasks.speech` when its provider has the kind, else the first speech routes row of such a provider, else None
(media:short-video and Studio map the voice `backend` field of an earlier storyboard with it). `aspeak` runs Fish,
Kokoro and Chatterbox in a worker thread (`asyncio.to_thread`), so they do not block the event loop; one lock per
kind serializes a model load or a synthesis.

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
- `chatterbox`: Chatterbox Turbo, zero-shot voice cloning, in the caller's process on the CPU (extra
  `ai-models[chatterbox]`: chatterbox-tts 0.1.7 on the versions of the `diffusers` extra, with its pins overridden by
  the installing project, `docs/architecture.md`, Local models in process), no local-model lock. The model entry's
  (`ChatterboxModel`) `url` and `files` name the model files (the template: the ModelScope mirror of Resemble AI's
  repository), loaded with `ChatterboxTurboTTS.from_local(<dir>, "cpu")` once per weights directory. A voice is
  `default` (the built-in voice) or the path of a recording longer than 5 s; the loaded model holds the
  conditioning of one voice and is conditioned again only when the voice changes. Synthesis runs with torch's
  intra-op threads set to the number of fast cores (`cpu.performance_threads`: the cores with the highest
  `cpuinfo_max_freq` in sysfs; unchanged when all cores have one speed or sysfs has no frequencies). On a GB10
  (10 Cortex-X925 and 10 Cortex-A725 cores) a sentence took 2.5 to 4 s with 10 threads and 9.5 s with torch's default
  20, and the load 9 s. Under numpy 2, Chatterbox's `norm_loudness` multiplies the float32 reference by a float64
  gain and returns float64 (NEP 50 promotion), which its mel filter matmul rejects; the result is cast to float32.
  The answer is a 24 kHz WAV file with Resemble's Perth watermark; no speed, no instructions.
- `torchaudio`: a forced-alignment pipeline of `torchaudio.pipelines` by name (`torchaudio:MMS_FA`), task `align`, in
  the caller's process on the CPU (extra `ai-models[align]`, torchaudio 2.11, the last release with `forced_align`).
  The model entry's (`TorchaudioModel`) `url` is the pipeline's weights file: `weights.ensure_file` downloads it (TLS context of `tls`, so
  `network.extra_ca_cert` applies) into the model directory under its own file name, the name torch.hub looks for, and the
  pipeline loads it from there (`get_model(dl_kwargs={"model_dir": ...})`), so torch.hub downloads nothing. `Aligner.align(samples, rate, tokens)` resamples to the pipeline's
  rate and returns one (start, end) in seconds per token. One aligner per model id stays loaded for the life of the
  process.

## Fish

A provider of kind `fish` runs Fish Audio Drama 3 (`fishaudio/drama-3`: a 35B mixture of experts with FP8 experts,
39 GB) through fish-speech (a pinned git commit; PyPI has only 0.1.0) in the caller's process, on an NVIDIA GPU only
(fish-speech has no MPS or CPU path). media:voiceover's `cuda` extra installs fish-speech on Linux. A model entry
(`FishModel`) has `repo` (a Hugging Face repository, downloaded to the Hugging Face cache by `snapshot_download`, or
a local folder), `memory` (GB at the peak, default 44), `style` and `max_frames`.

The first `speak` of a model loads it: `init_model` in bfloat16 without compilation and the checkpoint's codec
(`load_codec_model`), under the local-model lock, after the memory check against `memory` (Local model memory) and
with the CUDA allocator capped. On a GB10 the load took 230 to 242 s (reading 39 GB from disk) and the peak was 44.3
GB. The model stays loaded until the process exits or calls `local.unload`.

`speak` cuts the text before each style tag (`fish_span.split_spans`) and sends each span as one `generate_long`
request, with fish-speech's sampling defaults (temperature 0.7, top-p 0.7, top-k 30). Drama 3 ends a request with
one style tag on its own; with two tags in one request the speech is right and near-silence follows up to the token
cap (18.6 s of audio for about 5 s of speech). A tag with no words before the next tag joins the next span. A
speaker tag (`<|speaker:N|>`) at the start of a span stays in force for the following spans of the same text; a
span without one is speaker 0 to the model (fish-speech's `with_speaker_tag`). `max_frames` caps the
audio frames of one request (about 21.5 per second; unset, fish-speech's default of 1024 per text chunk). The
spans' audio is joined in order into one 16-bit WAV file at the codec's rate, 44.1 kHz. In English, Spanish and
French, and with `[whisper]` or `[laughing]` alone, each request ended on its own, about 5 s of audio in 4 to 9 s.

Voice: `default` only; another voice is refused (`Traits.one_voice`; Chatterbox clones a recorded voice). Drama 3
picks a new speaker for each request without a reference, and a fixed seed does not keep it. So the first span of
each voice in the process is kept as its `Take` (`fish_takes.Takes`): its WAV, its text and its codes. A voice is
keyed by model id, the caller's `speaker` (None is the narrator) and the span's speaker tag number (`Span.speaker_id`,
0 without a tag). Its text and codes are the reference (`prompt_text`, `prompt_tokens`) of every later span of that
voice, so one process has one voice per caller speaker and speaker tag number: the `<|speaker:1|>` spans of the
narrator share one voice in every line, distinct from the narrator's untagged spans and from the `<|speaker:1|>`
spans of the caller speaker `guest`. fish-speech writes the reference as `[Reference 1]` with its transcript's speaker tag
(`<|speaker:0|>` when the transcript has none), so `speak` sends the transcript behind the span's own speaker tag:
the reference then voices the speaker the request names. A reference needs both its transcript and its codes.
media:voiceover writes the first take of each caller speaker's untagged spans as `voice.wav` or
`voice-<speaker>.wav` with its text; the takes of inline speaker tags stay in the process.

A take outlives its process through `Take.save(folder)`, which writes `voice.wav`, `voice.txt` (the text) and
`codes.pt` (`torch.save` of the codes), and `Take.load(folder)`, which reads them back on the CPU (`weights_only`)
and raises `AIModelsError` naming a missing file. A caller that keeps `Takes.keep(model_id, speaker, Take.load(...))`
before the first `speak` of that speaker gets the saved voice for the speaker's untagged and `<|speaker:0|>` spans
(`keep` and `get` take speaker tag number 0 when none is given). `Takes.link(model_id, speaker, folder)` does the
same for a folder that may not exist yet: it loads the folder at once when it exists, else at the first `get` that
finds it; `speak` calls `get` after the model load, with the local-model lock held, so a take that another process
saved while this one waited for the lock seeds the voice. `Take.save` writes into a temporary sibling folder and
renames it, so a folder holds all three files or does not exist; it returns None and keeps the folder when the
target exists already. The codes are those of the checkpoint's codec, so a saved take is a reference only for
checkpoints with the same codec (Drama 3 today). media:voiceover keeps named Fish voices this way in its voices
directory (`docs/voiceover.md`, Fish voices across commands).

Instructions go through the model's `style`, a format string with `{instructions}` and `{text}` (Drama 3:
`"[{instructions}] {text}"`, its inline tags), applied to each span without a style tag of its own; a model without
`style` refuses instructions. There is no speed and there are no request parameters (`Traits.params`).

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
