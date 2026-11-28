# model_server

`lib/model_server` (distribution `model-server`) is an OpenAI-compatible HTTP server. It runs the models of the local
providers of its `config.yaml` (kinds `diffusers`, `fish`, `kokoro`, `chatterbox`, `torchaudio`) in its own process
with the `lib/ai_models` code, and forwards every other request to an Ollama server. One model runs at a time, and
an in-process model stays loaded between requests. The reason it exists is in
[architecture.md](architecture.md#local-models-in-process).

Run it with `python -m model_server` in an environment that has `model-server` with the extras of its models
(`diffusers`, `kokoro`, `chatterbox`, `align`; a `fish` provider also needs fish-speech, Linux and CUDA only). It
reads the settings file of `plugin_settings` (`SKILLS_CONFIG`, else `<config dir>/plugins/data/config.yaml`), exports
its environment settings (`plugin_settings.export`) and listens on `model_server.host` and `model_server.port`.

## Files

| File | Content |
|---|---|
| `__main__.py` | `python -m model_server`: uvicorn on `host` and `port` |
| `app.py` | `create_app(settings)`: the FastAPI app, its routers, its error bodies, start and stop |
| `server.py` | `Server`: settings, scheduler, residency, Ollama client, video jobs; `running(ref)` |
| `model_ref.py` | `ModelRef`: the routing of a request's `model` |
| `model_role.py`, `route.py` | `ModelRole` (image, music, video, presenter, speech, align), `Route` (local, ollama) |
| `scheduler.py`, `lease.py` | `Scheduler`: one model at a time, one FIFO queue; `Lease`: one admitted request |
| `residency.py` | `Residency`: keep-alive, room in memory before a load |
| `ollama.py`, `ollama_resident.py` | `Ollama`: forwarding, `/api/ps`, `/api/tags`, unload |
| `catalog.py` | the local models as `openai.types.Model` |
| `routes_images.py`, `routes_audio.py`, `routes_videos.py`, `routes_models.py`, `routes_ollama.py` | the endpoints |
| `music_create_params.py`, `alignment.py` | the request type of music and the answer type of alignments |
| `video_job.py`, `video_jobs.py` | `VideoJob` (shown as `openai.types.Video`), `VideoJobs` |
| `forms.py`, `requests.py`, `server_error.py` | request parsing, `ServerError` and its JSON body |
| `references.py` | `References`: the reference recordings of speech requests, as files |
| `client.py` | `model-client`: the command-line client of a server at a URL |

## Routing

A request names its model in the `model` field (JSON body or multipart field; the path of
`GET /v1/models/{id}`). A model id is `<provider>:<model>`, split at the first colon:

- When `<provider>` is a provider of a local kind in the server's config, the request runs in process. `<model>`
  must be an entry of that provider's `models`, else the answer is 404 `model_not_found`. Example:
  `local:flux2-klein-4b`, `kokoro:kokoro-v1.0`, `torchaudio:MMS_FA`.
- Any other id goes to Ollama unchanged. An Ollama tag is written as Ollama names it: `gemma3:270m`, its colon
  included. A provider of kind `ollama` in the server's config is not a local kind, so `ollama:gemma3:270m` is
  forwarded as `ollama:gemma3:270m`, which Ollama does not know.
- A local provider's name hides the Ollama models whose name before the colon is the same.

A client with a provider of kind `openai` whose `base_url` is the server's `/v1` writes the server's model id after
its own provider name: `server:local:flux2-klein-4b`, `server:gemma3:270m`. Its client library sends the part after
the first colon. `lib/ai_models` serves every task from such a provider and reads the model attributes it needs from
`GET /v1/models/{id}` ([ai_models.md](ai_models.md#model-server)).

Each endpoint of a local model takes models of its roles only (`ModelRole`, from the entry: a diffusers entry's
role, speech for `fish`, `kokoro` and `chatterbox`, align for `torchaudio`); another model is a 400
`model_not_supported`. The config file is read at each request (`plugin_settings.load_config`, cached per file
version), as `ai_models` reads it.

## Endpoints

Every path is under the server's base URL. The `openai` SDK reaches the ones it has a call for with
`openai.OpenAI(base_url="<server>/v1", api_key="<any>")`; for the others a client posts with
`client.post(path, ...)` or any HTTP client.

| Method and path | Request | Answer | SDK call |
|---|---|---|---|
| `POST /v1/images/generations` | JSON, `ImageGenerateParams` | `ImagesResponse` | `images.generate` |
| `POST /v1/images/edits` | multipart, `ImageEditParams` | `ImagesResponse` | `images.edit` |
| `POST /v1/audio/speech` | JSON, `SpeechCreateParams` | `audio/wav` | `audio.speech.create` |
| `POST /v1/audio/music` | JSON, `MusicCreateParams` | `audio/wav` | none |
| `POST /v1/audio/alignments` | multipart: `model`, `file`, `text` | `Alignment` (JSON) | none |
| `POST /v1/videos` | multipart, `VideoCreateParams` plus `audio`, `aspect`, `seed` | `Video` | `videos.create` (no `audio`) |
| `GET /v1/videos/{id}` | | `Video` | `videos.retrieve` |
| `GET /v1/videos/{id}/content` | `variant=video` | `video/mp4` | `videos.download_content` |
| `GET /v1/models` | | `{"object": "list", "data": [Model]}` | `models.list` |
| `GET /v1/models/{id}` | | `Model` | `models.retrieve` |
| any other `/v1/*`, `/api/*` | as Ollama takes it | Ollama's answer, streamed | `chat.completions.create`, `embeddings.create`, ... |

The request and answer types are those of `openai.types` (`openai.types.image_generate_params`,
`openai.types.image_edit_params`, `openai.types.audio.SpeechCreateParams`, `openai.types.VideoCreateParams`,
`openai.types.ImagesResponse`, `openai.types.Video`, `openai.types.Model`). A JSON body is validated against its
params type; a wrong field is a 400 naming it in `param`. Music and alignments have no OpenAI type; their types,
`MusicCreateParams` (a TypedDict) and `Alignment` (a Pydantic model), are in this package in the same style.

### Images

`POST /v1/images/generations`, JSON:

| Field | Value |
|---|---|
| `model` | a local image model (required) |
| `prompt` | the prompt (required) |
| `size` | `WxH`: the width and height; unset or `auto`: the pipeline's default |
| `n` | the number of images, from one pipeline call (`num_images_per_prompt`), default 1 |
| `response_format` | `b64_json` or unset; `url` is a 400 |
| `output_format` | `png` or unset; others are a 400 |
| any other field | a pipeline call argument (`seed` becomes a torch generator on the pipeline's device; others go to the pipeline as they are) |

The other `ImageGenerateParams` fields (`quality`, `background`, `style`, `moderation`, ...) are accepted and
ignored. The `openai` SDK sends the extra fields with `extra_body={"seed": 1}`.

`POST /v1/images/edits`, multipart: `model`, `prompt`, `image` (one file) or `image[]` (several files, the SDK's form
for a list), `mask` (optional PNG of the first image's size, transparent where the image is repainted), `size`, `n`,
and more pipeline arguments as text fields (a field that parses as JSON is sent as that value: `seed=3` is the
integer 3). With a mask, the first image goes to the model's `inpaint` pipeline and the others are its
`image_reference`; without one, every image goes to the pipeline as `image`.

The answer of both:

```json
{"created": 1790000000, "data": [{"b64_json": "<PNG, base64>"}], "output_format": "png", "size": "512x512"}
```

`size` is present when the request set one.

### Speech

`POST /v1/audio/speech`, JSON `SpeechCreateParams`: `model` (a local speech model), `input` (the text), `voice` (a
string or `{"id": ...}`, required by the params type), `instructions` (fish models with `style`), `speed`
(kokoro: 0.5 to 2), `response_format` (`wav` or unset; others are a 400), and two fields outside the params type:
`speaker` (who speaks, for a fish model, which keeps one voice per speaker) and `reference_audio` (the recording a
chatterbox model clones). Another field is a 400 naming it. The answer is a 16-bit mono WAV file,
`Content-Type: audio/wav` (kokoro and chatterbox 24 kHz, fish 44.1 kHz).

`reference_audio` is `{"data": "<base64 audio>", "format": "wav"}`, the shape of the `input_audio` of OpenAI chat
messages; `format` is `wav`, `mp3` (OpenAI's formats) or `flac`, the formats Chatterbox's reader takes. The recording
must be longer than 5 s, else the answer is a 400 `model_error`. `voice` is then the recording's name and is not
read. A model that does not clone (fish, kokoro) answers a 400 on `reference_audio`. The field is in the request
because the OpenAI flow of custom voices (`POST /v1/audio/voices`, then `voice: {"id": ...}`) keeps state on the
server between requests and requires a consent recording; one request carries everything, at the cost of sending
the recording (about 1 MB of base64 for 15 s at 24 kHz) with each sentence. The server writes each recording once,
to a file named by the SHA-256 of its bytes in a temporary directory (`References`, the last 16 recordings, removed
at shutdown), so the requests of one voice name one file and Chatterbox conditions on it once. With the `openai`
SDK: `client.audio.speech.create(model=..., input=..., voice="narrator", response_format="wav",
extra_body={"reference_audio": {"data": b64, "format": "wav"}})`. Without `reference_audio`, a chatterbox voice other
than `default` is the path of a recording on the server's machine.

### Music

`POST /v1/audio/music`, JSON `MusicCreateParams`:

| Field | Value |
|---|---|
| `model` | a local music model (required) |
| `prompt` | the description of the track (required) |
| `seconds` | the length (a number); unset: the pipeline's own length |
| `lyrics` | the lyrics; only a model with `lyrics_arg` takes them (else 400) |
| `seed` | an integer |
| `response_format` | `wav` or unset |

Another field is a 400 naming it. The answer is a 16-bit WAV file at the pipeline's sample rate, with the pipeline's
channels, `Content-Type: audio/wav`. The call is synchronous and lasts as long as the generation, so a client sets a
long timeout. With the `openai` SDK: `client.post("/audio/music", body={...}, cast_to=httpx2.Response).content`
(`openai` 3 is built on `httpx2`; its response class is the one `cast_to` takes for a raw body).

### Alignments

`POST /v1/audio/alignments`, multipart:

| Field | Value |
|---|---|
| `model` | a `torchaudio` model (required) |
| `file` | the recording, any format FFmpeg reads (decoded with PyAV, mixed to mono, resampled to the aligner's rate) |
| `text` | the aligner's tokens separated by whitespace (required); for `MMS_FA`, lowercase letters `a-z` and `'` |

A token the aligner cannot take is a 400 on `text`. The answer (`Alignment`):

```json
{"object": "audio.alignment", "model": "torchaudio:MMS_FA", "text": "the heart pumps", "duration": 1.62,
 "words": [{"word": "the", "start": 0.12, "end": 0.24}, {"word": "heart", "start": 0.3, "end": 0.61},
           {"word": "pumps", "start": 0.7, "end": 1.1}]}
```

`words` has one entry per token of `text`, in order (`openai.types.audio.TranscriptionWord`: `word`, `start`, `end`
in seconds from the start of the recording); `duration` is the recording's length in seconds. Normalising written
words to tokens (numbers to words, punctuation removed) is the client's work: media:voiceover's `normalize_word` does
it.

### Videos

`POST /v1/videos`, multipart (`openai.types.VideoCreateParams` plus three fields):

| Field | Video model | Presenter model |
|---|---|---|
| `model` | required | required |
| `prompt` | required | optional: replaces the model's default prompt; empty or unset: the default |
| `input_reference` | the image to animate (file, required) | the portrait (file, required) |
| `seconds` | the clip's length, a number as text (default 4); cut to the model's `max_frames` | not used: the clip is as long as `audio` |
| `size` | `WxH`: width and height, rounded to `size_multiple`; unset: the model's `width` and `height` | `WxH`: its ratio is the `aspect` when `aspect` is unset |
| `aspect` | width / height: reshapes the size to that ratio at the same pixel count | width / height: the bucket nearest it; unset: the portrait's |
| `audio` | not used | the narration (file, required), any format FFmpeg reads; also the clip's sound track |
| `seed` | an integer | an integer |

Another field is a 400 naming it. The `openai` SDK's `videos.create` sends `model`, `prompt`, `input_reference`,
`seconds` and `size`, and extra text fields with `extra_body`; it sends no second file, so a presenter request posts
the multipart body itself:

```python
from openai.types import Video

client.post("/videos", cast_to=Video, body={"model": "local:kandinsky-s2v", "prompt": "", "aspect": 1.0},
            files=[("input_reference", ("face.png", png, "image/png")), ("audio", ("say.wav", wav, "audio/wav"))],
            options={"headers": {"Content-Type": "multipart/form-data"}})
```

The answer is the job as `openai.types.Video`, with `status: "queued"`, and the clip's planned length and size:

```json
{"id": "video_<hex>", "object": "video", "model": "local:ltx-video", "prompt": "waves", "status": "queued",
 "progress": 0, "created_at": 1790000000, "completed_at": null, "expires_at": null, "error": null,
 "seconds": "0.375", "size": "768x512", "remixed_from_video_id": null}
```

`seconds` is the clip's length as text: for a video model the frame count (`frame_step * k + 1` covering the
requested seconds, at most `max_frames`) over `fps`; for a presenter the narration's length. `size` is `WxH` of the
frames. Both may differ from OpenAI's own values, so a client reads them as strings.

The job runs when the scheduler admits it (`status: "in_progress"`). `GET /v1/videos/{id}` answers the job; at its end
`status` is `completed` (`progress` 100) or `failed` with `error: {"code", "message"}` (`code`: `model_error` for an
error of `ai_models`, `insufficient_memory`, `server_error`). `completed_at` and `expires_at` are set then: the job
and its file are dropped `model_server.video_ttl` seconds after it ends, and a later lookup is a 404
`video_not_found`. `GET /v1/videos/{id}/content` answers the MP4 (`video/mp4`: H.264, with an AAC track when the
model makes one or for a presenter) once the job is `completed`, else a 409 `video_not_ready`; a `variant` other than
`video` is a 400. A client polls the job, then downloads (`client.videos.retrieve`, `client.videos.download_content`).

### Models

`GET /v1/models` answers `{"object": "list", "data": [...]}`: every model of every local provider of the config, then
the `data` of Ollama's `GET /v1/models` (none when Ollama does not answer). A local model is an `openai.types.Model`
with three more fields:

```json
{"id": "local:ltx-video", "object": "model", "created": 0, "owned_by": "local", "kind": "diffusers", "role": "video",
 "entry": {"repo": "Lightricks/LTX-Video-0.9.5", "pipeline": "LTXImageToVideoPipeline", "steps": 30,
           "guidance": 3.0, "args": {}, "skip": [], "memory": null, "fps": 24, "size_multiple": 32,
           "frame_step": 8, "width": 768, "height": 512, "max_frames": 121}}
```

`kind` is the provider kind, `role` the `ModelRole`, and `entry` the model's entry of the config with every key and
default, as JSON: a video model's `fps`, `size_multiple`, `frame_step`, `width`, `height`, `max_frames`; a presenter's
`fps`, `buckets` (a list of `[width, height]`), `audio_rate`; an image model's `inpaint` and `image` limits
(`max_edge`, `min_edge`); a music model's `duration_arg`, `lyrics_arg`, `min_crest_db`; a speech model's `voice`,
`voices` (and a kokoro model's `langs`); every model's `memory`. The SDK keeps these fields
(`client.models.retrieve(id).entry`). `GET /v1/models/{id}` answers one local model's object, and Ollama's answer for
another id. The object of one speech model also has `voices`, the names `ai_models.speech.voices` gives: the
entry's `voices`, else a Kokoro model's voices of the `langs` prefixes, read from its voices file (downloaded when
missing; the model is not loaded), else the default voice. The list of `GET /v1/models` has no `voices`.

### Ollama

Every other path under `/v1/` and `/api/` goes to Ollama at `model_server.ollama_url`, unchanged: method, path, query,
body and headers except the hop headers (`Host`, `Content-Length`, `Transfer-Encoding`, `Connection`, `Keep-Alive`,
`Content-Encoding`). The answer is streamed back as Ollama sends it, so a streamed chat (server-sent events) and
`/v1/systemone` pass through as they are. A request whose JSON body has a `model` runs as one request to that model in
the scheduler, and its slot ends when the answer ends; one without (`GET /api/tags`, `GET /api/ps`) goes at once. A
local model id on one of these paths is a 404 `model_not_supported`. When Ollama does not answer, the answer is a 502
`ollama_unreachable`.

## Errors

Every error is an OpenAI-style JSON body, which the `openai` SDK raises as `openai.APIStatusError` with `code` and
`param`:

```json
{"error": {"message": "...", "type": "invalid_request_error", "param": "size", "code": null}}
```

| Status | `type` | When |
|---|---|---|
| 400 | `invalid_request_error` | a field is missing or wrong (`param` names it); a model of another role (`code` `model_not_supported`); an `AIModelsError` of the model call (`code` `model_error`: a voice the model lacks, a speed out of range, a failed pipeline call); a Pydantic-AI `UserError` |
| 404 | `not_found_error` | a model a local provider lacks (`model_not_found`); an unknown or expired video (`video_not_found`); a local model on an Ollama path |
| 409 | `invalid_request_error` | the content of a video that is not completed (`video_not_ready`) |
| 500 | `server_error` | any other exception; an invalid config file |
| 502 | `upstream_error` | Ollama does not answer (`ollama_unreachable`) |
| 507 | `insufficient_memory_error` | a model that does not fit in memory (`insufficient_memory`, Memory below), or `ai_models.LocalMemoryError` of a load |

Ollama's own errors pass through as Ollama answers them.

## Scheduling

One model runs at a time (`Scheduler`). A request asks for a slot of its model. It starts at once when no request
runs, or when the running requests are of its model, that model runs requests in parallel, and no request waits.
Otherwise it waits in one FIFO queue. When the last running request ends, the head of the queue starts, with every
request behind it of the same model while that model runs in parallel. A request for the running model that arrives
while another model waits queues behind that model, so a stream of requests to one model does not hold back the
others.

Parallel models: every Ollama model (Ollama serves parallel requests; ai:classify sends 4 at once) and the
`torchaudio` aligner, which holds no state between calls. Diffusers pipelines, fish (`fish._lock`), kokoro (espeak-ng
is not thread-safe) and chatterbox (the loaded model holds the conditioning of one voice) run one request at a time.
A video job holds its slot while it runs, so a video waits for the requests before it and the requests behind it
wait for the video. A client that goes away while its request waits leaves the queue.

The in-process calls run in worker threads (`asyncio.to_thread`, as `ai_models` runs them), so the event loop keeps
serving polls, listings and Ollama streams while a model runs.

## Keep-alive

An in-process model stays loaded `model_server.keep_alive` seconds (default 300, as Ollama's default) after its last
request ends, so a repeated request skips the load (Fish Audio Drama 3 takes about 4 minutes to load). A sweep every
second unloads the idle models past that time with `ai_models.local.unload_model`; with `keep_alive` 0 a model unloads
when its last request ends. A model in use is never unloaded. At shutdown the server unloads every model
(`ai_models.local.unload`). Ollama keeps its models by its own `keep_alive`.

`ai_models.local.unload_model(model_id, weights_dir)` drops one model: each module that keeps loaded models registers
a function (`local.on_unload_model`) that drops the entries of that model from its cache (the diffusers pipelines of
the model's `repo`, shared with any other model of the same `repo`; the fish model, whose first takes stay; the kokoro
and chatterbox models of the model's weights directory; the aligner). It then collects garbage and empties the CUDA
allocator cache.

## Memory

Before the first request of an in-process model that is not loaded (`Residency.begin`), the server compares the
model's `memory` (GB at its peak, optional in every local model entry) with the free memory: the GPU's for `diffusers`
and `fish` (`ai_models.local.free_memory`; on a unified-memory GPU, the system's available memory), the system's
available memory for `kokoro`, `chatterbox` and `torchaudio`.

- A model larger than the total memory (CUDA's device memory, MPS's recommended maximum, else the system's memory) is
  refused at once with a 507.
- While the free memory is short, the server unloads the idle in-process models, least recently used first, then the
  models Ollama holds (`GET /api/ps`, then `POST /api/generate` with `{"model": <name>, "keep_alive": 0}`, which
  unloads embedding models too). After each unload it reads the free memory every 0.5 s until it suffices, stops
  growing for 2 s, or 10 s pass.
- When it is still short, the request is refused with a 507 that names the model's `memory` and the free GB.
- A GPU model without `memory` first unloads every idle in-process GPU model; then the load's own check applies
  (`ai_models.local.check_memory`: the pipeline's weights against the free memory).
- Before a request to an Ollama model that Ollama does not hold, the server unloads idle in-process models while the
  free memory is below the model's size in `GET /api/tags`. Ollama manages its own models.

The load itself checks again (`ai_models.local.check_free`, the check the fish load has always had, now applied to
every model whose entry sets `memory`), so a model that another process took the memory from fails with
`LocalMemoryError`, a 507.

## Local-model lock

The first diffusers or fish load of the server takes the exclusive file lock `ai-models-local.lock` in the system
temporary directory (`ai_models.local.hold_lock`, [ai_models.md](ai_models.md#local-model-memory)), and the server
holds it while any diffusers or fish model is loaded. `unload_model` releases it when the last of them unloads.
kokoro, chatterbox and torchaudio take no lock.

The consequence: on the server's machine, a skill command that loads a diffusers or fish model in its own process
waits for the lock while the server holds such a model, up to `keep_alive` seconds after the server's last request
to it, without a limit unless `local_models.lock_wait` sets one. A skill command that holds the lock makes the
server's next diffusers or fish load wait the same way, and every request queued behind it waits too. A machine that
runs the server sends its skills' local models to the server (a provider of kind `openai` with the server's
`base_url`) instead of running them in the skills' processes.

## Settings

The section `model_server` of `config.yaml` (`plugin_settings.ModelServerSettings`), read at start:

| Key | Default | Meaning |
|---|---|---|
| `host` | `127.0.0.1` | the address the server listens on; `0.0.0.0` serves the network, without authentication |
| `port` | `8000` | the port, 1 to 65535 |
| `keep_alive` | `300` | seconds an in-process model stays loaded after its last request; 0 unloads it after each request |
| `ollama_url` | `http://127.0.0.1:11434` | the Ollama server of the other models, without `/v1` |
| `timeout` | `600` | seconds a request forwarded to Ollama may take (connect: 10 s) |
| `video_ttl` | `3600` | seconds a finished video job and its MP4 are kept |
| `weights_dir` | unset | the weights directory of a `kokoro`, `chatterbox` or `torchaudio` provider without `dir`; unset, such a provider needs `dir` |

The server's models are the local providers of the same file. Each model entry of a local kind takes `memory`
(optional, GB at its peak; `fish` defaults to 44). Users find the keys in `setup:settings` and
`plugins/setup/skills/settings/assets/config.example.yaml`.

## Command-line client

`model_server.client` is a client of a server at a URL, run as `model-client` (the console script of the package) or
`python -m model_server.client`. In the server's environment it is `.venv/bin/model-client`; in this repository,
`uv run --project lib/model_server model-client ...`.

```
model-client [--url URL] models [ID]
model-client [--url URL] status VIDEO_ID
model-client [--url URL] video --model ID --image FILE --prompt TEXT [--seconds S] [--aspect A] [--size WxH] [--seed N] [-o OUT]
model-client [--url URL] image --model ID --prompt TEXT [--size WxH] [--seed N] [-o OUT]
model-client [--url URL] speech --model ID --text TEXT [--voice V] [-o OUT]
```

| Command | Endpoint | Prints |
|---|---|---|
| `models` | `GET /v1/models` | one id per line |
| `models ID` | `GET /v1/models/{id}` | a local model's `kind`, `role`, `entry` (and `voices`) as YAML; Ollama's object for another id |
| `status VIDEO_ID` | `GET /v1/videos/{id}` | `<id> <status> <progress>%`, with the error of a failed job |
| `video` | `POST /v1/videos`, then `GET /v1/videos/{id}` every 0.5 s, then `GET /v1/videos/{id}/content` | the job's status at creation and at each change, then the MP4's path and the wall time |
| `image` | `POST /v1/images/generations` | the PNG's path and the wall time |
| `speech` | `POST /v1/audio/speech` | the WAV file's path and the wall time |

- `--url` is the server's `/v1` base URL. Default: `http://localhost:<model_server.port>/v1`, the port from the
  settings file (8000 without one).
- Model ids are the server's, as `models` lists them: `local:ltx-2.5`, `kokoro:kokoro-v1.0`, an Ollama tag.
- `speech` without `--voice` sends the model's default voice: its entry's `voice`, else the first of its `voices`.
- Output: `-o OUT`, else the current directory, as `<model id with ':' and '/' as '_'>_<YYYYmmdd-HHMMSS>.<ext>`
  (`local_flux2-klein-4b_20261128-101500.png`). An existing file is an error, checked before the request and again
  at the write; the client never overwrites.
- An error (an error answer as `HTTP <status> <code>: <message>`, a failed video job, a server that does not answer)
  is one line on stderr and exit code 1.
- Each command's core function (`models`, `model`, `status`, `video`, `image`, `speech`, `output_path`, `save`)
  returns its result and raises `ClientError`; `main` prints, writes and sets the exit code. The calls are the
  `openai` SDK's on a client with `base_url` the URL, outside `ai_models`
  ([architecture.md](architecture.md#standard-paths-for-model-calls)). Timeout: 900 s per request, no retries.

## Tests

Unit tests (`tests/unit/model_server/`) cover the routing (`ModelRef` on tests/config.yaml), the scheduler with no
model, request parsing, error bodies, video jobs and the model list. Integration tests
(`tests/integration/model_server/`) start the real app on uvicorn on a free port in a thread of the test process with
tests/config.yaml, and call every endpoint with the tiny models through the `openai` SDK where it has the call (httpx
for music and alignments): images and edits (klein-tiny), video jobs (ltx-tiny with a seed, ltx2-tiny, s2v-tiny), speech
(kokoro, chatterbox with and without `reference_audio`, fish), music (ace-step-tiny), alignment (MMS_FA), Ollama chat, streamed chat, embeddings,
`/v1/systemone`, `/api/tags` and the model list, keep-alive, the lock, the memory refusal and the unload of idle GPU
models. The fish test needs CUDA. `tests/integration/model_server_client/test_cli.py` calls the core functions of
`model-client` against the same in-process server: the model list and one entry, a video job and a failed one, an
image, speech in the default and another voice, the default output name and the refusal to overwrite.

The suite `tests/server/` tests a deployed server over the network: `scripts/tests.sh server --server-url <url>`,
`<url>` the server's `/v1` base URL. It calls each endpoint through the `ai_models` functions with a client config
(`tests/server/config.yaml`, its provider `server` of kind `openai` at `<url>`) and checks the model list and each
model's object, chat (plain and streamed), embeddings, System-1, audio input, images and edits with a mask, speech
(Kokoro in another voice, Chatterbox with `reference_audio`, Fish with `speaker`), alignments, music, the video and
presenter jobs, the error answers, requests to several models at once and parallel requests to one model, and
Ollama's `/api/ps`. The server keeps no listing of its loaded in-process models, so their keep-alive is not tested
there. The suite passes when the server's config holds:

- the providers of `tests/config.yaml` other than `ollama`, each renamed `tiny_<provider>` (`tiny_local`,
  `tiny_kokoro`, `tiny_chatterbox`, `tiny_fish`, `tiny_torchaudio`) with its models' entries as written there, the
  `kokoro`, `chatterbox` and `torchaudio` providers with their `dir`, and the tiny Fish and ACE-Step folders built on
  the server's machine (`tests/tiny_fish.py`, `tests/tiny_ace_step.py`);
- the Ollama models of the tasks of `tests/server/config.yaml` pulled on the server's Ollama (`gemma3:270m`,
  `laya:421m-english-bf16`, `all-minilm:22m`, `lfm3-audio:2b-q4_K_M`).

The Fish test needs CUDA on the server's machine.
