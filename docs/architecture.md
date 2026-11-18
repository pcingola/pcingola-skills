# architecture

The tests named here are in `tests/unit/plugin/test_manifest.py` and `tests/unit/plugin/test_tests_rules.py`
(`uv run --group dev pytest tests/unit/plugin`). How a single skill works is in `docs/<skill>.md` where one exists.

## Plugin isolation

A skill reads nothing outside its plugin directory except its plugin data directory, the settings file, the user's
model routes file `routes.md` in the settings file's directory, a brand folder reported by `brand:brand` (read in
place), the user's input and output files and files another skill wrote as its output. It reads no repo-root path, no repo-root `data/` and no file of
another plugin. The user's `routes.md` sits beside the settings file for the same reason the settings file sits
outside every plugin: a plugin update or uninstall leaves it in place, and every plugin finds it through one path
rule (`plugin_settings.config_file`). Its template is an asset of `setup:settings`, which copies it there.

Claude Code reads a plugin installed from a directory marketplace in place, and a plugin installed from a git or
remote marketplace from a copy under `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`. That copy holds the
plugin directory only, so the repository root does not exist next to it, and another plugin's directory has no fixed
location relative to it. A skill that works in place but reads outside its plugin breaks in a cache copy.

Every skill lives in exactly one plugin (`test_skill_in_exactly_one_plugin`), and `plugins/` holds only the plugins
the marketplace lists (`test_no_other_plugin_directories`, `test_marketplace_json`). No file under `plugins/` that git
tracks or would track holds `${CLAUDE_SKILL_DIR}/..` or a relative `../<skill>/` into another skill
(`test_no_sibling_paths`).

## Loading another skill

A skill that needs another skill, of its own plugin or another, loads it with the Skill tool by its `<plugin>:<skill>`
name and states the task in prose: the input, the wanted result, where the output goes and any required options. The
loaded skill's `SKILL.md` gives the command, and its `allowed-tools` pre-approve its wrapper. Every operation a caller
asks for is documented in the callee's `SKILL.md` or its `references/`.

No file in a skill directory names another skill's wrapper, script path or `references/` file. A data format another
skill defines is referred to by name. The reason is the same as for plugin isolation: the other skill's files have no
fixed path from the caller, and the loaded `SKILL.md` is the only interface that holds in every install. No skill's
Python imports another skill.

A caller's `allowed-tools` lists `Skill` and only its own wrapper rules. Any other `Bash` entry, bare `Bash`
included, needs an entry with its reason in `BASH_RULE_ALLOWLIST` of the test file. A skill that loads another skill has it in
its own plugin or in a plugin listed in its `plugin.json` `dependencies`, because installing a plugin also installs
its dependencies and a load of a skill outside them fails in an install without that plugin.

Tests: `test_no_reference_to_other_skill_code`, `test_plugin_skill_references`, `test_skill_loading_listed`,
`test_allowed_tools_no_other_skill_wrappers`, `test_plugin_json`.

## One home per concern

Each concern has one location, and every other skill reaches it through that location:

- Shared Python code: the packages in the repo-root `lib/` (see Shared packages).
- Every model call: `lib/ai_models`, on Pydantic-AI (`docs/ai_models.md`; Standard paths for model calls). TLS and
  the providers' clients are set up there once, and the local models (diffusers, Kokoro, Chatterbox, Fish, the
  torchaudio aligner) are run there. No module of a `<skill>_tool` package of a plugin project that depends on `ai-models` imports
  google-genai, the OpenAI SDK or a model library (`test_model_calls_only_through_ai_models`).
- Settings: one file, `config.yaml` (`$SKILLS_CONFIG`, else `<config dir>/plugins/data/config.yaml`). It holds the
  providers with their keys and the attributes of their models (`providers`), the model of each task (`tasks`), and
  one section per other concern (`network`, `huggingface`, `local_models`, `brand`, `studio`, `voiceover`). A skill has no model
  setting and no model default in code; it asks `ai_models` for a task (the list is in `docs/ai_models.md`, Config)
  or passes the user's `--model`.
- The schema of the settings file, its loader and the plugin data directory: `lib/plugin_settings`. `ai_models`
  reads the file through it.
- Model routes, per task the recommended default model and the escalations from it to another model for some
  requests: `ai_models.routes` reads the user's `routes.md` beside the settings file (`docs/ai_models.md`, Model
  routes); setup:settings creates it from its template `assets/routes.md`. The model in use for a task stays
  `tasks.<task>` of the settings file; a table's default row is a recommendation. Each skill that calls a model
  prints the table with its `routes` command.
- Brands (logos, colours, fonts, guidelines, PowerPoint templates): `brand:brand`. Callers get a brand folder
  from it, locate each file through its `brand.yaml` key and read it in place without keeping a copy.
- Visual styles: `brand:style`. A brand's `styles` key restricts the styles a branded image may use.
- Installation and settings documentation, including the settings error messages: `setup:settings`. The
  missing-setting and invalid-setting errors name that skill.
- The template of the settings file, with every setting any skill reads and placeholder values:
  `plugins/setup/skills/settings/assets/config.example.yaml`. `setup:settings` creates the user's file from it.
- Maintainer documentation: `docs/`.

## Standard paths for model calls

A remote model call goes through Pydantic-AI, and a local LLM runs in Ollama, reached through Pydantic-AI's Ollama
provider. One path per kind of call means one client setup, one error mapping (`errors.explained`) and one set of
tests for every skill. A direct call is an exception, made only where the standard path cannot do the task, and
each one is listed here with its reason:

- Remote speech. Pydantic-AI has no text-to-speech API: its Google model requests only text and image output, and
  its speech support is realtime voice sessions. `ai_models.speech` calls the OpenAI SDK's `audio.speech` on the
  client of the Pydantic-AI provider (kinds `openrouter`, `openai`, `azure`, `ollama`) and Google's
  `generate_content` with audio output (Gemini TTS).
- Remote music. Pydantic-AI has no music API. `ai_models.music` posts to Lyria's `:predict` endpoint over HTTP and
  calls Google's `generate_content_stream` (Gemini music).
- Weight downloads (`ai_models.weights`): a file fetched over HTTP, no model call.
- Ollama's memory query (`ai_models.local`, `GET /api/ps`): which models Ollama holds and when it unloads them, read
  before a local load; no model call. Pydantic-AI has no call for it.

The image edit with a mask (`MaskedOpenAIImageModel`) is a subclass of Pydantic-AI's `OpenAIImageGenerationModel`,
on the standard path. A change of path keeps every capability, and wiring that costs without need is removed.

## Agent judgement, code mechanics

A skill's code does deterministic work: parsing, conversion, storage, rendering, measurement, checks. The agent does
the judgement and loads the other skills. Example: short-video's code never calls another skill and
imports the files that `media:voiceover`, `media:music` and `media:video-effects` wrote when the agent loaded them. A
skill's Python therefore imports no other skill and needs no other skill's environment. No test enforces this
division.

## Shared packages

The shared Python packages have one source each, in `lib/`. `plugins/<plugin>/lib/` holds only `uv_env.sh`
(`test_plugin_lib_holds_only_uv_env`). A plugin project depends on a shared package as a uv git source: `{ git =
"<origin URL>", subdirectory = "lib/<dir>", branch = "main" }`, with no `rev`, `tag` or path source
(`test_lib_sources_follow_main`). A shared package declares no `[tool.uv.sources]` of its own, so a project that
installs `ai-models` also declares the `plugin-settings` source.

uv fetches the packages from the git origin when it builds a skill's environment, so a plugin, in place or as a
cache copy, needs no file outside its directory. The access this needs is in `README.md`: building an environment
needs the same git read access as installing the marketplace from the origin.

Each skill's `uv.lock` records the commit of `main` it resolved. A rewritten `main` would leave those commits
unreachable, so `main` is never force-pushed. Branches are merged into `main` with merge commits.

A change to a shared package reaches the skills only after it is pushed to `main` and each project that depends on
it is relocked (`uv lock --upgrade-package <package>` in the project); the changed `uv.lock` files are then
committed. The library's own tests run against the working tree's `lib/`.

## Plugin data directory and settings

Each plugin has a data directory outside the plugin directory. Every plugin reads its settings from the one file
`config.yaml`, validated as a whole against one schema in `lib/plugin_settings/plugin_settings/schema/`, and reads
a setting as a typed attribute: `plugin_settings.config().studio.dir` (`docs/plugin_settings.md`). The schema knows
every section, so one load checks the whole file and names the YAML path of each misspelt, missing or invalid key;
a section read by two plugins (`brand.path`: brand CLI and Studio catalogue) has one definition. A section of a
plugin that is not installed is optional. A new setting is a field of its section's class in the schema plus its
line in the template, a `lib/` change that reaches the skills by relock (Shared packages).

The skills' code never reads a setting from the process environment, so a setting has one place to look and a
skill behaves the same whatever shell started Claude Code. The variables that locate files are not settings and are
read from the environment: `CLAUDE_CONFIG_DIR` and `CLAUDE_PLUGIN_DATA` (Claude Code), `SKILLS_CONFIG` (the
settings file) and `PLUGIN_ENV_DIR` (set by the wrappers). The settings that libraries and child processes read from
the environment (`network`, `huggingface`) are set there by `Plugin.load` from the file (`ENV_EXPORTS` of
`plugin_settings`), and removed when the file does not set them; it also removes the variables the model client
libraries read for keys, endpoints and headers (`OPENAI_*`, `GOOGLE_API_KEY`, ...).

## Data outside the plugin

Data a skill keeps across runs (catalogs, indexes, model weights, browser profiles, cloned voices) defaults to a
location under the plugin data directory. That directory is outside the plugin directory and every cache copy, so the
data survives plugin updates. What an uninstall deletes is in `README.md`.

## Environments outside plugins/

Nothing generated lives in `plugins/`. Loaded in place, a generated file would sit in the plugin directory; a cache
copy copies the plugin directory with its ignored files, so a generated file would also land in every cache copy.

Each wrapper finds its plugin directory (the nearest directory above it holding `.claude-plugin/plugin.json`), sources
that plugin's `lib/uv_env.sh` and calls `plugin_env` on its uv project. `plugin_env` resolves the plugin data
directory exactly as `plugin_settings` does, returns 1 with an error when the plugin or marketplace name is unknown
and `CLAUDE_PLUGIN_DATA` is unset, and points the uv environment, Python bytecode and other generated files at
`<plugin data dir>/env/<id>/<project>/`. `<id>` is the POSIX `cksum` of the directory holding the plugin directory.
Plugins read in place all resolve to the working tree's `plugins/`, so installed skills and wrappers run by hand share
one set of environments. A cache copy has another parent and gets its own environment; its versions
share a parent, so they share that environment. `<project>` is the uv project's path inside the plugin without
`skills/` and `/scripts`, `/` as `-`. The path is kept short for espeak-ng, used by the Kokoro speech models
of `ai_models` (`docs/ai_models.md`).

A wrapper can source no file outside its plugin, so each plugin with wrappers carries its own copy of `uv_env.sh`.
Tests: `test_every_plugin_with_wrappers_has_uv_env`, `test_uv_env_copies_identical`, `test_uv_env_data_dir` (runs
`plugin_env` under `set -eu -o pipefail`, as the wrappers do, and compares its data directory with the one
`plugin_settings` resolves).

uv takes its settings (`dependency-metadata`, for example) from the nearest `pyproject.toml` with a `[tool.uv]`
table, searching upward from the project directory whatever the working directory. A project without that table
would read the repository root's `[tool.uv]` and write the root's `dependency-metadata` into its `uv.lock`. Every
uv project under `plugins/` therefore has its own `[tool.uv]` table, empty where it needs no setting. `--no-config`
would block the root settings too, but it also drops a project's own `dependency-metadata`, which voiceover needs.
Tests: `test_plugin_projects_have_own_tool_uv`, `test_lock_dependency_metadata_from_own_project`.

## Local models in process

A local model runs in the caller's process, in the environment of the skill that calls it: diffusers pipelines,
Kokoro, Chatterbox Turbo and the torchaudio aligner on the CPU, Fish Audio Drama 3 on an NVIDIA GPU. A separate
environment or server process would need its own install, start, shutdown, timeouts and error handling, so it needs
a tested reason: a pin of the model's package that fails when it is overridden.

A dependency's version pin is tested before an environment is built around it. A package often pins older versions
than it needs. The test installs the package in a scratch environment with its pins overridden to the skill
environment's versions and runs the model. chatterbox-tts 0.1.7 pins torch 2.6, transformers 5.2.0, diffusers 0.29,
numpy 1 and safetensors 0.5.3; fish-speech pins torch 2.8.0, transformers 5.19.0, pydantic 2.9.2 and tokenizers
0.23.2. Both ran on the versions of the voiceover environment and of the root test environment (torch 2.11,
transformers 5.22.2, diffusers 0.43.0), so both run in media:voiceover's environment (`docs/voiceover.md`,
Dependency pins).

Two uv settings apply the overrides in `scripts/pyproject.toml` of media:voiceover:

- `override-dependencies` replaces a requirement of any package (transformers, diffusers, numpy, safetensors,
  protobuf).
- `dependency-metadata` gives the requirement lists of chatterbox-tts and fish-speech with those pins removed, and
  fish-speech's without pyaudio, which it does not use and which needs the portaudio headers. torch and torchaudio
  stay unpinned there.
  torch and torchaudio cannot be overrides there: an override replaces the requirement of the `cpu` and `cuda`
  extras too, and with it the extra's index in `tool.uv.sources`, so the CPU and CUDA builds would no longer be
  selected. The root project has no such extras and overrides torch and torchaudio directly.

## CLI wrappers

Each skill with a CLI tool has its own uv project and environment, so its dependencies do not constrain another skill's.
The project is `scripts/pyproject.toml` with a package `<skill>_tool` (hyphens as underscores), which the wrapper
`scripts/<skill>.sh` runs with `uv run python -m`.
The wrapper unsets `VIRTUAL_ENV`, so a parent venv cannot replace the project's environment. The image-gen, music and
short-video wrappers add `--extra local` (torch and diffusers, through
`ai-models[diffusers]`) when `config.yaml` (`SKILLS_CONFIG`, else `<config dir>/plugins/data/config.yaml`) has a
provider of kind `diffusers`, so a user without local models does not install torch. The repo-root `pyproject.toml`
is used by the plugin and library test suites.
`SKILL.md` calls the wrapper as `${CLAUDE_SKILL_DIR}/scripts/<skill>.sh`, and `allowed-tools` pre-approves only that
wrapper: `Bash(${CLAUDE_SKILL_DIR}/scripts/<skill>.sh:*)`, and in most skills also the relative form
`Bash(scripts/<skill>.sh:*)` (`_own_wrapper_rule` accepts both). No `allowed-tools` entry starts with `Bash(*`, which
would pre-approve any command ending in the wrapper path (`test_allowed_tools_no_unanchored_bash_rules`).

A command of a `<skill>_tool` package has a core function with typed parameters. It returns its result (the data
the command prints, or the paths it writes) and raises an exception on error (`PptxError` in `pptx_tool`). Every
`pptx_tool` command has this split; the skills whose test files `CLI_PROCESS_ALLOWLIST` marks "not converted yet" may
not have it everywhere. The CLI
layer, `main(argv: list[str] | None = None) -> int` and the argument handlers it dispatches to, parses the arguments,
calls the core function, prints the result, and turns the exception into the error message and exit code 1. No core
function prints its result, calls `sys.exit` or reads `sys.argv`, so a test calls it in process (Tests).

## Installation and versions

Installation, in-place loading, the cache copy and updates are in `README.md`. `plugin.json` has no `version` field,
so the version label is the HEAD commit (`test_plugin_json`); `claude plugin validate` warns about the missing field,
and the warning is expected. `claude plugin list --json` shows a plugin read in place as `readFromFolder`; its
`installPath` is the cache copy. `claude plugin marketplace add` with a local path is always a directory source,
untracked and ignored files included, so a marketplace of tracked files only needs a git remote. The repository has no
`.claude/skills` link, so a session in it does not load the skills a second time next to the installed plugins.

## Agent-facing and maintainer documentation

`SKILL.md` holds what the agent needs on every use of the skill. Its frontmatter description is the only text matched
at startup; it is quoted on one line, at most 250 characters because Claude Code truncates longer descriptions, and
contains `TRIGGER when:`; the frontmatter `name` equals the skill directory (`test_skill_frontmatter`,
`test_skills_found`). Material the agent needs only for some tasks
is in the skill's `references/`, loaded on demand.

`SKILL.md` and `references/` are read from an installed plugin, where `docs/`, `CLAUDE.md` and the repository root do
not exist. They therefore never point to `docs/` or to a repo-root file; no test checks this. `docs/` is for
maintainers of this repository: how the code works and why, where the code does not show it.

## Tests

All tests run in one environment, the repo-root project's `dev` group, from the repository root
(`scripts/tests.sh unit|integration|models|all`, commands in `CLAUDE.md`). The group installs the `lib/` packages as
editable path dependencies (`ai-models` with its `diffusers` extra), so every test sees the working tree's `lib/`, and
the dependencies of every skill project, Chatterbox and fish-speech included, with the overrides of media:voiceover
(Local models in process). Its pytest `pythonpath` lists each skill's `scripts/` and the studio server. A dependency
added to a skill project is also added to the root `dev` group, so the suites never need a second environment. Manim
runs in its own environment, as a subprocess, for users and tests alike.

Tests call the real code and the real dependency. No test imports a mock library, patches, uses the `monkeypatch` or
`mocker` fixture, uses a fake or stub server, writes the process environment, or skips (`skip`, `skipif`, `xfail`,
`importorskip`, `SkipTest`). The reasons: a mock tests the test's idea of the dependency, not the dependency; an
environment write leaks into other tests; a skipped test reports nothing and hides a missing prerequisite.

A test calls the code under test in process, except a test that needs a setting (below). It calls a command's core
function (CLI wrappers), or `main(argv)` with `stdout` and `stderr` redirected when its subject is the CLI's
arguments, output or exit code. A test starts a skill's wrapper or CLI as a process only
when the process is its subject: the wrapper and its environment, a lock between processes, or state kept across
commands. Its docstring names that subject. A call through the wrapper adds the wrapper, `uv run` and an interpreter
start (a pptx command: 0.20 s through `pptx.sh`, 0.05 s in process) and tests the wrapper again on every call.
`CLI_PROCESS_ALLOWLIST` of `tests/unit/plugin/test_tests_rules.py` lists each file that starts a wrapper or a
`<skill>_tool` CLI as a process, with its reason; the files of suites not converted yet have the reason "not converted
yet" (`test_cli_process_only_in_allowlisted_files`). Every test under `tests/integration/pptx/` and
`tests/integration/pptx_author/` has a docstring (`test_pptx_tests_have_docstrings`).

A test that needs a setting runs the real code in a child process whose environment it states in full
(`tests/subproc.py`: `child_env`, `run_python`, `py_value`). `tests/settings_env.py` (`isolated`) points `HOME`,
`CLAUDE_CONFIG_DIR` and `CLAUDE_PLUGIN_DATA` of that child at a temporary directory with no settings file, so the
user's settings do not reach the code under test. It keeps uv's cache, Python installs and configuration and git's
global configuration. A test that needs a setting, a provider or a model writes a real `config.yaml` in a temporary
directory (`write_config`) and passes its path to the child in `SKILLS_CONFIG`; an in-process test of `ai_models`
names it with `config.use`. A test that needs a key, a model, a GPU or a tool fails with a message naming what is
missing (`tests/prereq.py`: `requires`).

Models:

- Tests use tiny models: the smallest model that runs the same code path, with random weights where that is what
  exists. Such a test checks the code path (load, call, output format), not the output's quality. Examples: the
  random-weight FLUX.2 klein, LTX-Video, LTX-2 and Kandinsky S2V checkpoints published for those pipeline classes,
  Kokoro's int8 model, Chatterbox Turbo, and ACE-Step and Fish pipelines with random weights that
  `tests/tiny_ace_step.py` and `tests/tiny_fish.py` build into `~/.cache/pcingola-skills-tests/` when missing.
- The models that tests load or call are named in one file, `tests/config.yaml` (`TEST_CONFIG` of
  `tests/settings_env.py`, with `~` expanded), and `tests/models/config.yaml` for the full-size suite. No test reads
  the user's config, except that a `tests/models/` test of a remote model copies the `api_key` and endpoint of the
  user's provider of the same kind into its own temporary config (`models_config`). A unit test that only parses or
  routes a model id, with no load and no call, may keep the id in the config it writes.
- A unit test never calls or loads a model and needs no GPU, Ollama or network.
- An integration test takes seconds. Every test has a timeout, 30 s by default (pytest-timeout, root
  `pyproject.toml`), and every subprocess a test starts has a shorter one, so a hang fails the test with a message.
- A test of a full-size model itself (a new model version, a question about what a model can do) lives in
  `tests/models/`, runs only with `scripts/tests.sh models` and sets its own larger timeout; `unit`, `integration`
  and `all` never collect it (`testpaths`). It exists only where no tiny model tests the same thing: Fish Audio
  Drama 3, and the remote speech and music models, whose code path has no local stand-in.

Local models and their lock: a model loaded in the pytest process would hold the local-model lock
(`ai_models.local.hold_lock`) until pytest exits and block every later child process that loads one. An autouse
fixture of `tests/integration/conftest.py` therefore calls `ai_models.local.unload()` after each test, which drops
every in-process model and releases the lock. `local_models.lock_wait` is the second safety mechanism:
`tests/config.yaml` sets 20 s, below the 25 s subprocess and 30 s test timeouts, and `tests/models/config.yaml` a
value below that suite's subprocess timeouts, so a held lock fails a test with the holder's PID.
