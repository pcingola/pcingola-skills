# ai_models

`lib/ai_models` (distribution `ai-models`) makes every model call of the skills (`docs/architecture.md`, One home
per concern). It has three parts:

1. Pydantic-AI: chat, vision, audio input, embeddings, image generation, image edits with reference images and
   System-1 models. The package reads the config and builds the Pydantic-AI object (`Agent`, `Embedder`,
   `ImageGenerator`, `SystemOneModel`); the call itself is Pydantic-AI's.
2. Adapters for what Pydantic-AI lacks: speech, music, video and image masks. One function per task, one branch per
   provider kind.
3. Local models with `diffusers`, in the caller's process: image, music and image-to-video models. The extra
   `ai-models[diffusers]` installs torch and diffusers, so only the skills that need it carry them.

| Module | Contents |
|---|---|
| `config` | the config file, `<provider>:<model>` ids, `model_for(task)`, `resolve(model, task)` |
| `models` | the Pydantic-AI provider of each kind; `chat_model`, `agent`, `embedder` |
| `images` | `image_generator`, `MaskedOpenAIImageModel` |
| `system1` | `system1_model`, `decide` |
| `speech` | `speak` |
| `music` | `compose` |
| `video` | `animate`, `aanimate`; `frame_count`, `frame_size`, `clip_size` |
| `omni` | `speak` of a vLLM-Omni server (Speech models of vLLM-Omni) |
| `local` | `DiffusersImageModel`, `DiffusersMusicModel`, `animate` (video), the pipeline cache, the lock, memory check and cap (Local model memory) |
| `tls` | the TLS context of remote clients |
| `errors` | `AIModelsError`, `ConfigError`, `explained` |

## Config

The config is the settings file of `plugin_settings` (`docs/plugin_settings.md`): `$SKILLS_CONFIG`, else
`<config dir>/plugins/data/config.yaml`. `config.path` and `config.load` read it through `plugin_settings`
(`config_file`, `read_config`), so the skills and the package use one file and one loader. `config.use(path)` sets
another file for the process (the tests use it). The template is `assets/config.example.yaml` of `setup:settings`,
which creates the user's file. A missing or malformed file, a missing task, a provider without `kind` and an empty
key are each a `ConfigError` whose message names the fix.

The package reads three sections; the fourth, `settings`, belongs to `plugin_settings`:

- `providers`: name to settings. Every provider has `kind`. A provider that needs a key holds it in `api_key`;
  `config.api_key` returns None for an entry without `api_key` and raises `ConfigError` for an empty one. `timeout`
  (seconds, default 600) applies to every request of that provider.
- `models`: task to model id. A model id is `<provider name>:<model>`; the first colon splits it, so
  `ollama:d3:4b` is the Ollama tag `d3:4b`. A caller passes its own id (a `--model` flag) or asks for a task and gets
  `models.<task>` (`config.resolve`). The tasks the skills use: `chat`, `vision`, `system1`, `image`,
  `image_edit`, `image_best`, `image_multi_ref`, `speech`, `music`, `audio`, `video`, `film_critic`. The package has no model defaults.
- `diffusers`: name to local model: `repo` (a Hugging Face repository), `steps`, `guidance` (optional: without it
  no `guidance_scale` is passed), `inpaint` (the diffusers pipeline class for an edit with a mask, built over the
  loaded modules with `from_pipe`), `args` (optional: more pipeline call arguments, after steps and guidance and
  before the caller's) and `skip` (optional: pipeline components loaded as None). A music model adds `duration_arg`
  and `lyrics_arg`, the pipeline call argument names for the length in seconds and the lyrics; a model without one
  does not take that option. A model id
  `<diffusers provider>:<name>` names it. A video model adds the keys of the Video section.

The image-gen, music and short-video wrappers install the extra when the config has a provider of kind `diffusers`
(`docs/architecture.md`, CLI wrappers).

## Provider kinds

| Kind | Pydantic-AI provider | Keys |
|---|---|---|
| `ollama` | `OllamaProvider` | `base_url` (default `http://localhost:11434/v1`) |
| `openrouter` | `OpenRouterProvider` | `api_key` |
| `openai` | `OpenAIProvider`; chat goes through Chat Completions (`openai-chat`), which every OpenAI-compatible server has | `base_url`, `api_key` |
| `azure` | `AzureProvider` | `base_url` (the Azure endpoint), `api_version`, `api_key` |
| `google` | `GoogleProvider`, or `GoogleCloudProvider` (Vertex) with `vertex: true` | `api_key`, `base_url` |
| `diffusers` | none; `local` | none |
| `vllm-omni` | none; `omni` | `python`, `repo`, `deploy`, `memory_share`, `style`, `args`, `env`, `start_timeout` (Speech models of vLLM-Omni) |

What each kind serves:

| Task | Through | Kinds |
|---|---|---|
| chat, vision, audio | Pydantic-AI `Agent` | all but `diffusers` |
| embed | Pydantic-AI `Embedder` | all but `diffusers` |
| system1 | Pydantic-AI `SystemOneModel` on the provider's `base_url` (Ollama: `/v1/systemone`) | any with a `base_url` |
| image, image_edit | Pydantic-AI `OpenAIImageGenerationModel`, `GoogleImageGenerationModel`; `local.DiffusersImageModel` | `ollama`, `openrouter`, `openai`, `azure`, `google`, `diffusers` |
| image mask | `images.MaskedOpenAIImageModel`; the `inpaint` pipeline of a `diffusers` model | OpenAI kinds, `diffusers` |
| speech | `speech.speak`: the OpenAI SDK `audio.speech` of the provider's client, Google `generate_content`, or `omni.speak` | OpenAI kinds, `google`, `vllm-omni` |
| music | `music.compose`: Google predict or stream, or `local.DiffusersMusicModel` | `google`, `diffusers` |
| video | `video.animate`: `local.animate` (image to video) | `diffusers` |

Remote clients are one `httpx2.AsyncClient` per provider object, with the provider's timeout and the context of
`tls`.

## Pydantic-AI and the adapters

Pydantic-AI covers chat, vision, audio input, structured output, embeddings, image generation and image edits with
reference images, and System-1 models. The package adds no retry policy of its own: the callers rely on
Pydantic-AI's errors (`ModelRateLimitError`, `ModelConnectionError`, `ContentFilterError`, ...) and decide what to
retry. `errors.explained(model_id)` wraps a call and turns two common failures into an `AIModelsError` with the fix:
an Ollama model that is not pulled (HTTP 404, "run `ollama pull <model>`") and a provider that does not answer.

The adapters cover what Pydantic-AI has no call for:

- Mask. Pydantic-AI's `OpenAIImageGenerationModel` sends no mask. `MaskedOpenAIImageModel` subclasses it and gives it
  a client whose `images.edit` adds the mask (PNG, transparent where the image may change). A mask without a
  reference image is refused. The `google` kind takes no mask (`ConfigError`).
- Speech. The OpenAI kinds call `audio.speech.create` on the Pydantic-AI provider's OpenAI client, with the style as
  `instructions` and a speed other than 1 (a server may refuse it; Ollama does). `google` calls `generate_content`
  with an AUDIO response and a prebuilt voice, with the style as a text prefix the model does not speak; raw PCM comes
  back as a WAV file at the rate of its MIME type. The `google` kind has no speed setting.
- Music. A model listed in the provider's `predict_models` gets a plain `:predict` POST on the provider's `base_url`
  (default Vertex), with `sample_count` inside the instance, where the API honours it; one WAV per sample. Other
  models of the `google` kind stream with
  AUDIO and TEXT parts; length and lyrics go in the prompt, images as parts after it, and the text parts come back
  with the MP3. A server may end the stream with a `[DONE]` line the SDK cannot parse: it is ignored once audio
  arrived, and a stream without audio is tried again, up to 3 times. `music.TAKES` lists the options of each model
  kind (`diffusers`, `predict`, `stream`); another option is refused before any request.
- Local models (`local`). `DiffusersImageModel` is a Pydantic-AI `ImageGenerationModel`; `DiffusersMusicModel` gives
  a WAV file; `animate` gives an MP4 (Video). Pipelines load in bfloat16 with `DiffusionPipeline.from_pretrained`,
  or with the class a model's `pipeline` names, on CUDA, else MPS, else an error,
  and stay loaded for the life of the process. `from_pretrained` leaves the weights memory-mapped from the safetensors
  files; `to_device` copies each one to process memory before the move to the GPU, because a host-to-device copy
  from a file mapping is about 100 times slower on a unified-memory GPU (GB10: 87 s against under 2 s for FLUX.2
  klein 4B). Weights go to the Hugging Face cache. torch and diffusers are imported
  only in this module.

## Local model memory

A diffusers pipeline runs in the caller's process and keeps its weights for the life of that process. Skills run
model commands in parallel (parallel tool calls, one subagent per scene), and Ollama keeps a model resident for
5 minutes after its last call. On a unified-memory GPU, allocations past the free memory exhaust system memory and
the machine hangs without an error. `local.pipeline` therefore does three things before a load:

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
  (`wait_for_memory`) and resets the cap before it raises.
- Check. After `from_pretrained` and before any weight moves to the device, the bytes of every parameter and
  buffer of the pipeline's torch modules (`weight_bytes`) are compared with the device's free memory
  (`free_memory`), read before the load, because a load that converts dtypes holds the weights in process memory
  until the move. Weights over the free memory raise `AIModelsError` with the model, both sizes in GB and the
  models resident in each `ollama` provider of the config (`GET /api/ps`).
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

## Speech models of vLLM-Omni

Fish Audio Drama 3 runs only through vLLM-Omni (or SGLang-Omni), which pins torch 2.14.0 and transformers below
5.20; the skill environments have torch 2.14.1 and transformers 5.23. It therefore runs in its own environment,
in a separate process. A provider of kind `vllm-omni` names that environment's interpreter (`python`) and the
model (`repo`). `omni.speak`:

1. On the first call of the process, makes SIGTERM raise `SystemExit` (`exit_on_sigterm`, so step 5 runs after a
   SIGTERM), takes the local-model lock (`local.hold_lock`, Local model memory) and reads the free memory
   (`local.free_memory`). After waiting for the lock, it reads the free memory until it stops rising
   (`local.wait_for_settled_memory`: a rise under 0.5 GB between readings 0.5 s apart, at most 10 s), while the
   previous holder's memory comes back. On an integrated GPU the free memory is at most
   `torch.cuda.mem_get_info()[0]` (`vllm_free_memory`), because vLLM checks its share against that figure at start.
2. Writes a deploy overlay that inherits `deploy` (a file of vLLM-Omni's `deploy/` directory, found with the
   environment's `importlib.util.find_spec`, or a path) through vLLM-Omni's `base_config`. The overlay turns off
   the CUDA MPS daemon (`platforms.cuda.cuda_mps: false`) and scales every stage's `gpu_memory_utilization` so
   that their sum is `memory_share` times the free memory over the device total, in the deploy config's
   proportions (Drama 3: 0.78 and 0.1). Without MPS the two stages share one GPU by time-slicing.
3. Starts `vllm serve <repo> --omni --deploy-config <overlay>` plus the provider's `args` on a free loopback port,
   with the provider's `env` added to the environment, in its own process group with `PR_SET_PDEATHSIG`, and polls
   `/health` until `start_timeout` (default 1800 s).
4. Sends each request to `POST /v1/audio/speech` (`response_format: wav`; the audio comes at the model's rate,
   since Drama 3 refuses `sample_rate`).
5. Stops the server at exit (`atexit`, `Server.stop`): SIGTERM to the group, a wait of up to 30 s for the main
   process and then up to 30 s for the rest of the group (the stage workers, polled with `killpg(pgid, 0)`), then
   SIGKILL to the group. The kernel sends SIGTERM to the main process when the caller dies (`PR_SET_PDEATHSIG`);
   that signal does not reach the stage workers.

On the GB10 (sm_121), Drama 3 needs three settings, all in config: `--safetensors-load-strategy eager` (the
default memory-mapped load took 18 s per 2.5 GB shard, 4.5 min in all, past vLLM-Omni's 300 s stage start limit;
eager took 34 s), `--stage-init-timeout 1800`, and `VLLM_USE_FLASHINFER_SAMPLER=0` (FlashInfer has no prebuilt
sampling kernel for sm_121 and JIT-compiles it with nvcc, which is not installed). vllm-omni 0.32.0 needs vllm
0.32 (with vllm 0.33 its CLI fails on `vllm.entrypoints.launchers.cli_args`).

The server lives for one command, like a diffusers pipeline. The in-process `Omni` class was not used: it needs
the model's prompt layout in our code (vLLM-Omni's TTS adapter builds it for the server, per architecture).

Voice: `default` (the model's own voice), or a path to a reference recording with its transcript in a `.txt` file
of the same stem, sent as `ref_audio` (a `data:` URI) and `ref_text`. Instructions go through the provider's
`style`, a format string with `{instructions}` and `{text}` (Drama 3: `"[{instructions}] {text}"`, its inline
tags); a provider without `style` refuses instructions. There is no speed.

## Video

`video.animate(image, prompt, *, seconds, model=None, width=None, height=None, aspect=None, seed=None)` returns an MP4 of the
image animated as the prompt says; `aanimate` runs it in a worker thread. The model is `model`, else `models.video`.
Only the `diffusers` kind serves video. A video model is a `diffusers.<name>` entry with these keys besides `repo`,
`steps` and `guidance`, all required (`video.video_spec` raises a `ConfigError` that names each missing key):

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
sample rate; `apresent` runs it in a worker thread. The model is `model`, else `models.presenter`, a `diffusers.<name>`
entry with optional `steps`, `guidance`, `args` and `skip`, and these keys, all required (`video.presenter_spec`):

| Key | Meaning |
|---|---|
| `pipeline` | the diffusers class to load, a `DiffusionPipeline` or a `ModularPipeline` class |
| `fps` | frames per second of the clip |
| `buckets` | the frame sizes the model makes, a list of `[width, height]`; the clip takes the one nearest `aspect` on a log scale (`video.bucket`), default the image's aspect |
| `audio_rate` | the sample rate the model takes the speech at; the speech goes to the model mono at this rate |
| `output` | the pipeline output that holds the videos (a modular pipeline's `output=` argument) |

PyAV decodes and resamples the speech (`local.read_audio`). The image is cropped to the bucket (`ImageOps.fit`) and
passed with its `width` and `height`; `prompt`, when given, replaces the pipeline's default prompt.

`local.pipeline` loads a `ModularPipeline` class (`modular_model_index.json`, Kandinsky S2V) with `from_pretrained`
then `load_components(dtype=bfloat16)` of every component outside `skip`, under the same lock, memory check of the
loaded components' weights and CUDA cap as a `DiffusionPipeline`. diffusers 0.43 is the first release with the
Kandinsky S2V modular pipeline.

The models, their repositories and these keys are in `config.yaml`; `config.example.yaml` has a real model and a
minimal test model. The presenter test (`tests/integration/ai_models/test_video.py`) uses
`kandinskylab/tiny-kandinsky-s2v-distilled-modular-pipe` (32 MB, random weights, the diffusers test fixture); its text
RoPE has 128 positions, so its config passes a short `prompt` in `args`.

## TLS

A machine behind a TLS-intercepting proxy can set `SSL_CERT_FILE` to the proxy CA alone, which replaces the public
root bundle and breaks verification of public endpoints. `tls` therefore starts from certifi's roots and adds the
extra CA of `plugin_settings.ca` (`EXTRA_CA_CERT`, then `NODE_EXTRA_CA_CERTS`, `docs/plugin_settings.md`). The default
verify flags stay on, `VERIFY_X509_STRICT` included.

`PYDANTIC_AI_NO_BANNER` is set on import unless already set, because the skills' output is read by programs.
