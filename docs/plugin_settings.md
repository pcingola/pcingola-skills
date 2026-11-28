# plugin_settings

`lib/plugin_settings` reads and validates the settings file `config.yaml` of every skill, exports the settings that
libraries read from the process environment, and resolves each plugin's data directory. The sections and keys are
documented for users in the `setup:settings` skill; the template is
`plugins/setup/skills/settings/assets/config.example.yaml`.

## Files

| File | Content |
|---|---|
| `paths.py` | `config_dir`, `config_file`, `use`, `display` (home shown as `~`), `CONFIG_ENV` |
| `loader.py` | `load_config`, `config`, `error`, `exit_code`, `ConfigFileError`, `SETUP_LINE`, the error formatter |
| `env_export.py` | `EnvVar`, `ENV_EXPORTS`, `CLEARED_PREFIXES`, `CLEARED_KEYS`, `export` |
| `old_keys.py` | `OLD_SECTIONS`, `OLD_SETTINGS`, `OLD_PROVIDER_KEYS`, `OLD_KIND_KEYS`, `OLD_KINDS`, `old_key_errors` |
| `plugin.py` | `Plugin`: name, directory, data directory, `load` |
| `schema/` | the Pydantic classes of the file; `__init__` re-exports them |

## The settings file

One file for all plugins: the file set by `use(path)`, else `$SKILLS_CONFIG`, else `<config
dir>/plugins/data/config.yaml`, where `<config dir>` is `$CLAUDE_CONFIG_DIR`, else `~/.claude`. These variables
locate the file, so they are read from the process environment and never set by it.

The sections, each a class in `schema/`:

| Section | Class | Content |
|---|---|---|
| `providers` | `Provider` (`schema/providers/`), one class per `kind`, discriminated on `kind` | endpoints, keys, local servers; `models`, the attributes of each model |
| `tasks` | `dict[Task, ModelId]` | the model id `<provider>:<model>` of each task; the first colon splits it |
| `network` | `Network` | proxies, `extra_ca_cert`, `ca_bundle` |
| `huggingface` | `HuggingFace` | `home`, `token` |
| `local_models` | `LocalModels` | `lock_wait`: the seconds a process waits for another process that holds the local models (`ai_models.local.hold_lock`) before it fails naming that process; unset, no limit |
| `brand` | `BrandSettings` | `path`, a list of directories |
| `studio` | `StudioSettings` | `dir` (absolute or `~`), `author` (a list of names) |
| `voiceover` | `VoiceoverSettings` | `voices_dir` |
| `second_opinion` | `SecondOpinionSettings` | `codex`: review with the Codex CLI when no `--model` is given |
| `model_server` | `ModelServerSettings` | `host`, `port`, `keep_alive`, `ollama_url`, `timeout`, `video_ttl`, `weights_dir` of the model server (`docs/model_server.md`, Settings) |
| `model_client` | `ModelClientSettings` | `provider`: the default server of `model-client`, a provider of kind `openai` with a `base_url` (`docs/model_server.md`, Command-line client) |

Every class derives from `Strict` (`extra="forbid"`, frozen), so an unknown section or key fails with its path. A
key that is empty or holds only comments parses as null; `Strict` gives it its default when that default is a
section, mapping or list (an emptied section, `models:` map or list), and a null model entry is an empty one
(`Catalogue`). A null `tasks.<task>` is an error (`ModelId`). Field types are in `schema/fields.py`: paths have `~`
expanded (`UserPath`, `AbsolutePath` for `studio.dir`); `network.extra_ca_cert` and `network.ca_bundle` must name
existing files (`ExistingFile`); URLs are validated by pydantic's URL types and kept as written (`HttpUrl` for
endpoints and weight files, `ProxyUrl` with `PROXY_SCHEMES` for proxies); `api_key` and `huggingface.token` are
`SecretStr`, and an empty one is an error.

`providers.<p>.models` maps a bare model name (the part after the first colon) to its attributes. A provider holds
what is about where and how its models run; each model's own attributes are on its entry:

| Provider kind | Provider fields | Class of `models.<m>` | Model fields |
|---|---|---|---|
| `ollama`, `openrouter`, `openai`, `azure` | `api_key`, `base_url`, `timeout`; azure `api_version` | `OpenAIModel` | `image` (`OpenAIImageLimits`), `voice`, `voices` |
| `google` | `api_key`, `base_url`, `timeout`, `vertex`, `credentials`, `project`, `location` | `GoogleModel` | `predict` (served by the Vertex `:predict` endpoint), `voice`, `voices` |
| `diffusers` | `test` | `DiffusersEntry`: the class of the entry's role | `repo` (required), the pipeline fields of the role, `memory` |
| `kokoro` | `dir`, `test` | `KokoroModel` | `model_url`, `voices_url`, `langs`, `voice`, `voices`, `memory` |
| `torchaudio` | `dir`, `test` | `TorchaudioModel` | `url`, `memory` |
| `chatterbox` | `dir`, `test` | `ChatterboxModel` | `url`, `files`, `voice`, `voices`, `memory` |
| `fish` | `test` | `FishModel` | `repo` (required: a Hugging Face repository or a local folder, absolute or `~`), `memory` (GB at the peak, default `DRAMA3_PEAK_GB`, 44), `style`, `max_frames`, `voice`, `voices` |

`memory` of every local model entry is `LocalMemory` (`schema/local_memory.py`): the GB the model takes at its peak,
optional, unset by default; `FishModel` declares its own with Drama 3's default. `ai_models.local.check_free` and
the model server read it (`docs/model_server.md`, Memory).

The provider fields shared by several kinds are declared once, in classes the provider classes derive from:
`TimedProvider` (`timeout`), `RemoteProvider` (`api_key`, `base_url`), `OpenAIKindProvider` (`models` of
`OpenAIModel`), `LocalProvider` (`test`, on every local kind: true marks its models as test models, which a model
server lists with `test: true` and `model-client models` hides without `--tests`), `WeightsDir` (`dir`, `with_dir`,
a `LocalProvider`). `Voices` holds
`voice` and `voices` for every model class that may be a speech model. Every provider class has `models`, so
`provider.models.get(model)` needs no check of the kind.

A remote provider serves any model id; its `models` holds attributes only. A model of a kind in `LOCAL_KINDS`
(`diffusers`, `kokoro`, `torchaudio`, `chatterbox`, `fish`) needs an entry.

A `diffusers` entry is one of four classes, one per `DiffusersRole`: `DiffusersImageModel` (`inpaint`, `image`),
`DiffusersMusicModel` (`duration_arg` required, `lyrics_arg`, `min_crest_db`), `DiffusersVideoModel` (`pipeline`,
`fps`, `size_multiple`, `frame_step`, `width`, `height`, `max_frames`, all required, and `text_pipeline`, optional) and `DiffusersPresenterModel`
(`pipeline`, `fps`, `buckets`, `audio_rate`, `output`, all required); all share `repo`, `steps`, `guidance`, `args`
and `skip` (`DiffusersModel`). The YAML has no role key: `diffusers_entry.role_of` reads the role from the keys
(a presenter-only key, then a video-only key or `pipeline`/`fps`, then a music key, else image), and the class of
that role refuses a key of another role and names each missing required key.

`image` limits differ by kind: `OpenAIImageLimits` (`max_edge`, `min_pixels`, `max_pixels`, all required;
`always_sized`, `default_quality` of `Quality`: low, medium, high, auto) and `DiffusersImageLimits` (`max_edge`,
`min_edge`, both required). Both derive from `ImageLimits` (`max_edge`).

The groupings of provider kinds the code branches on are in `schema/provider_kind.py`: `OPENAI_KINDS`, `API_KINDS`,
`LOCAL_KINDS`, `IMAGE_LIMIT_KINDS`, `SPEECH_KINDS`. `schema/task_kinds.py` holds `TASK_KINDS`, the kinds each task
takes, `TASK_ROLES`, the diffusers role of the image, music, video and presenter tasks, and `SERVER_TASKS`, the
tasks (align, music, video, presenter) the kind `openai` serves only from a model server.

`Config.task_error(task, model_id)` says why a model cannot serve a task: its provider is not in `providers`, is of
a kind not in `TASK_KINDS[task]`, is local and has no entry for the model, the entry is a diffusers model of another
role, or a System-1 model's provider, or an `openai` provider of a task of `SERVER_TASKS`, has no `base_url`. After every section validates, `Config` runs it for each
`tasks.<task>`; `ai_models.config.resolve` runs it for a model a caller names (`--model`). Each provider class
checks its own required keys (`setup:settings` lists them).

`Config.server_error(name)` says why provider `name` cannot be a model server's address: it is not in `providers`, is
not of kind `openai`, or has no `base_url`. `Config` runs it for `model_client.provider` after every section validates
(`model_client.provider: provider 'vertex' is of kind google; a model server's provider is of kind openai`), and
`model-client` runs it for its `--provider`.

`Config.provider(name)`, `Config.model_entry(model_id)` and `Config.task_model(task)` return None when absent;
`ai_models.config` turns that into a `ConfigError` (`docs/ai_models.md`).

## Loading

`load_config()` returns the validated `Config`. A missing or empty file gives `Config()`, every default. A file that
is not YAML, not a mapping, or not valid raises `ConfigFileError`. The result is cached per process, keyed by
`(path, st_mtime_ns, st_size)`, so the long-running Studio server sees edits and every other call is a dict lookup.
`use()` clears the cache.

`config()` is `load_config()` that prints `Error: <message>` on stderr and exits 1 on `ConfigFileError`. Skills read
settings as typed attributes, `plugin_settings.config().studio.dir`, never from `os.environ`.

`exit_code(e)` is the exit code of a `SystemExit` as the interpreter sets it: 0 for None, an int code as is, 1 for any
other code, which it prints on stderr. A CLI's `main(argv)` returns it for the `SystemExit` of argparse or of `error`.

## Errors

One message lists every problem, each on its own line as `<YAML path>: <reason>`, and ends with `SETUP_LINE`:

```
Error: ~/.claude/plugins/data/config.yaml is not valid:
  providers.azure.api_version: required for kind azure
  providers.openrouter.api_key: required for kind openrouter
  network.extra_ca_cert: file /path/ca.pem does not exist
  studio.dirr: not a setting
The setup:settings skill describes every key and creates the file.
```

The cross references run only when every section is valid, so their lines (`tasks.music: provider 'vertex' is not
in providers`) appear once the other errors are fixed.

The path comes from Pydantic's `loc`, joined with `.` and list indexes as `[i]`; the tags of the discriminated
unions (the provider kind, the diffusers role) are dropped from it. An unknown key reads `not a setting` (`not a
setting of kind <k>` inside a provider, `not a setting of a video model (kind diffusers)` inside a diffusers
entry), a missing one `required` with the same suffix. Home paths show as `~`.

## Keys of the earlier layout

`Config` runs `old_key_errors` before validation and fails with one line per key of the earlier layout, naming its
new place:

| Earlier key | Error names |
|---|---|
| `models` | `tasks` |
| `diffusers` | `providers.<p>.models.<name>` of the provider of kind `diffusers` |
| `settings` | each key: `IMAGE_GEN_*` to `providers.<p>.models.<m>.image.*`, `BRAND_PATH` to `brand.path`, `STUDIO_DIR` and `AUTHOR_NAME` to `studio.*`, `VOICEOVER_VOICES_DIR` to `voiceover.voices_dir`, proxies, `EXTRA_CA_CERT`, `NODE_EXTRA_CA_CERTS` and `SSL_CERT_FILE` to `network.*`, `HF_HOME` and `HF_TOKEN` to `huggingface.*`; another `VOICEOVER_*` to `tasks.speech`, `tasks.align` and their providers; any other key is `not a setting` |
| `providers.<p>.predict_models` | `providers.<p>.models.<m>.predict: true` |
| `providers.<p>.memory_share` | `providers.<p>.models.<m>.memory` of kind `fish`, in GB |
| `providers.<p>.python`, `start_timeout`, `timeout` of kind `chatterbox` (`OLD_KIND_KEYS`) | removed: Chatterbox runs in the caller's process |
| `providers.<p>.kind` of a removed kind (`OLD_KINDS`) | the kind that replaces it (`fish`), the provider and model keys that kind lacks, and the meaning of `memory` |
| `providers.<p>.<k>` for a model key `<k>` (`MODEL_KEYS`: `model_url`, `voices_url`, `langs`, `url`, `files`, `repo`, `memory`, `style`, `voice`, `voices`) | `providers.<p>.models.<m>.<k>` |

The full texts are `OLD_SECTIONS`, `OLD_SETTINGS`, `OLD_PROVIDER_KEYS`, `OLD_KIND_KEYS` and `OLD_KINDS` in `old_keys.py`.

## Export to the environment

`Plugin.load()` calls `config()` and `export(cfg)`, and returns the `Config`. `export` makes `os.environ` agree with
the file, so a shell variable is never a setting for the skills' code, the libraries it calls or its child processes:

- Each row of `ENV_EXPORTS` (`EnvVar(name, getter, lower)`) sets its variable to the config value, or removes it
  when the value is None or empty. A row with `lower` sets or removes the lower-case name too, since httpx prefers
  `https_proxy` over `HTTPS_PROXY`.
- Every variable whose name starts with one of `CLEARED_PREFIXES` or is one of `CLEARED_KEYS` is removed. The model
  clients of ai_models read keys, endpoints, API versions, projects, credentials, extra headers and CA bundles from
  them, and huggingface_hub a cache, an offline switch and a token that would replace `huggingface.*`; ai_models
  passes each of those from `config.yaml` instead. The names are listed for users in setup:settings `SKILL.md`, the
  one statement of the list outside the code; `tests/unit/plugin_settings/test_settings.py` checks that it names
  every one. The Chatterbox worker sets `HF_HUB_OFFLINE=1` in its own process after the export, since its weights
  are local.

`ENV_EXPORTS`:

| Variable | From | Lower case too | Read there by |
|---|---|---|---|
| `HTTP_PROXY` | `network.http_proxy` | yes | httpx and requests (model calls, weight downloads) |
| `HTTPS_PROXY` | `network.https_proxy` | yes | same |
| `ALL_PROXY` | `network.all_proxy` | yes | same |
| `NO_PROXY` | `network.no_proxy`, joined with `,` | yes | same |
| `SSL_CERT_FILE` | `network.ca_bundle` | no | Python's default `ssl` context (httpx, requests), as the whole trust store |
| `NODE_EXTRA_CA_CERTS` | `network.extra_ca_cert` | no | Node.js child processes (short-video) |
| `HF_HOME` | `huggingface.home` | no | huggingface_hub, the weights of the `diffusers` models |
| `HF_TOKEN` | `huggingface.token` | no | huggingface_hub, gated repositories |

A skill calls `Plugin.load()` at the start of its CLI, before it imports a library that reads one of these
variables at import time (huggingface_hub reads `HF_HOME`). `export()` without an argument calls `config()`.

## Extra CA

A TLS-intercepting proxy re-signs HTTPS traffic with its own root CA. `network.extra_ca_cert` names that CA as a PEM
file. ai_models adds it to certifi's roots (`ai_models.tls.ca_cert()`, `docs/ai_models.md`), and `export` sets
`NODE_EXTRA_CA_CERTS` to it. `network.ca_bundle` is different: as `SSL_CERT_FILE` it replaces the default trust
store of libraries outside ai_models; ai_models does not read it, since its context starts from certifi. The
package ships no CA file.

## Binding to a plugin

A skill calls `Plugin.of(__file__)`, which takes the plugin from the nearest `.claude-plugin/plugin.json` above the
file. The plugin name is read from that manifest, not from the directory, because a cache copy under `<config
dir>/plugins/cache/<marketplace>/<plugin>/<version>` sits in a directory named after the version.

## Data directory

Without `CLAUDE_PLUGIN_DATA`, the data directory is the one Claude Code assigns to the plugin, `<config
dir>/plugins/data/<plugin>-<marketplace>`, with characters other than letters, digits, `_` and `-` replaced by `-`.
The marketplace name has two sources:

- A plugin loaded in place from a directory marketplace has `.claude-plugin/marketplace.json` above it, whose `name`
  is used.
- A cache copy holds only the plugin directory, so no marketplace manifest is above it; the marketplace is the
  directory name in the cache layout.

When neither gives a name, or the plugin manifest has no name, the lookup exits asking for `CLAUDE_PLUGIN_DATA`
instead of guessing a directory Claude Code would not use. `plugin_env` in each plugin's `lib/uv_env.sh` resolves the
same directory in shell (`docs/architecture.md`).
