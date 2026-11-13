# ai_models

`lib/ai_models` (distribution `ai-models`) makes every model call of the skills (`docs/architecture.md`, One home
per concern). It has three parts:

1. Pydantic-AI: chat, vision, audio input, embeddings, image generation, image edits with reference images and
   System-1 models. The package reads the config and builds the Pydantic-AI object (`Agent`, `Embedder`,
   `ImageGenerator`, `SystemOneModel`); the call itself is Pydantic-AI's.
2. Adapters for what Pydantic-AI lacks: speech, music and image masks. One function per task, one branch per
   provider kind.
3. Local models with `diffusers`, in the caller's process: an image model and a music model. The extra
   `ai-models[diffusers]` installs torch and diffusers, so only the skills that need it carry them.

| Module | Contents |
|---|---|
| `config` | the config file, `<provider>:<model>` ids, `model_for(task)`, `resolve(model, task)` |
| `models` | the Pydantic-AI provider of each kind; `chat_model`, `agent`, `embedder` |
| `images` | `image_generator`, `MaskedOpenAIImageModel` |
| `system1` | `system1_model`, `decide` |
| `speech` | `speak` |
| `music` | `compose` |
| `local` | `DiffusersImageModel`, `DiffusersMusicModel` |
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
  `image_edit`, `speech`, `music`, `audio`. The package has no model defaults.
- `diffusers`: name to local model: `repo` (a Hugging Face repository), `steps`, `guidance`, and `inpaint` (the
  diffusers pipeline class for an edit with a mask, built over the loaded modules with `from_pipe`). A model id
  `<diffusers provider>:<name>` names it.

The image-gen and music wrappers install the extra when the config has a provider of kind `diffusers`
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

What each kind serves:

| Task | Through | Kinds |
|---|---|---|
| chat, vision, audio | Pydantic-AI `Agent` | all but `diffusers` |
| embed | Pydantic-AI `Embedder` | all but `diffusers` |
| system1 | Pydantic-AI `SystemOneModel` on the provider's `base_url` (Ollama: `/v1/systemone`) | any with a `base_url` |
| image, image_edit | Pydantic-AI `OpenAIImageGenerationModel`, `GoogleImageGenerationModel`; `local.DiffusersImageModel` | `ollama`, `openrouter`, `openai`, `azure`, `google`, `diffusers` |
| image mask | `images.MaskedOpenAIImageModel`; the `inpaint` pipeline of a `diffusers` model | OpenAI kinds, `diffusers` |
| speech | `speech.speak`: the OpenAI SDK `audio.speech` of the provider's client, or Gemini TTS | OpenAI kinds, `google` |
| music | `music.compose`: Lyria, or `local.DiffusersMusicModel` (ACE-Step) | `google`, `diffusers` |

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
  back as a WAV file at the rate of its MIME type. Gemini TTS has no speed setting.
- Music. `lyria-002` is a plain `:predict` POST on the provider's `base_url` (default Vertex), with `sample_count`
  inside the instance, where the API honours it; one 30 s WAV per sample. Other Lyria models (Lyria 3) stream with
  AUDIO and TEXT parts; length and lyrics go in the prompt, images as parts after it, and the text parts come back
  with the MP3. A server may end the stream with a `[DONE]` line the SDK cannot parse: it is ignored once audio
  arrived, and a stream without audio is tried again, up to 3 times. `music.TAKES` lists the options of each model
  kind (`diffusers`, `predict`, `stream`); another option is refused before any request.
- Local models (`local`). `DiffusersImageModel` is a Pydantic-AI `ImageGenerationModel`; `DiffusersMusicModel` gives
  a WAV file. Pipelines load in bfloat16 with `DiffusionPipeline.from_pretrained`, on CUDA, else MPS, else an error,
  and stay loaded for the life of the process. Weights go to the Hugging Face cache. torch and diffusers are imported
  only in this module.

## TLS

A machine behind a TLS-intercepting proxy can set `SSL_CERT_FILE` to the proxy CA alone, which replaces the public
root bundle and breaks verification of public endpoints. `tls` therefore starts from certifi's roots and adds the
extra CA of `plugin_settings.ca` (`EXTRA_CA_CERT`, then `NODE_EXTRA_CA_CERTS`, `docs/plugin_settings.md`). The default
verify flags stay on, `VERIFY_X509_STRICT` included.

`PYDANTIC_AI_NO_BANNER` is set on import unless already set, because the skills' output is read by programs.
