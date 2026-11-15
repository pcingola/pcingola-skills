# architecture

The tests named here are in `tests/unit/plugin/test_manifest.py` (`uv run --group dev pytest tests/unit/plugin`). How a single skill
works is in `docs/<skill>.md` where one exists.

## Plugin isolation

A skill reads nothing outside its plugin directory except its plugin data directory, the settings file, the user's
model routes file `routes.md` in the settings file's directory, a brand folder reported by `brand:brand` (read in
place) and files another skill wrote as its output. It reads no repo-root path, no repo-root `data/` and no file of
another plugin. The user's `routes.md` sits beside the settings file for the same reason the settings file sits
outside every plugin: a plugin update or uninstall leaves it in place, and every plugin finds it through one path
rule (`plugin_settings.config_file`). The default routes ship inside `lib/ai_models`, which every skill that calls a
model installs, so no skill reads them from another plugin.

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

A caller's `allowed-tools` lists `Skill` and only its own wrapper rules. A skill that loads another skill has it in
its own plugin or in a plugin listed in its `plugin.json` `dependencies`, because installing a plugin also installs
its dependencies and a load of a skill outside them fails in an install without that plugin.

Tests: `test_no_reference_to_other_skill_code`, `test_plugin_skill_references`, `test_skill_loading_listed`,
`test_allowed_tools_no_other_skill_wrappers`, `test_plugin_json`.

## One home per concern

Each concern has one location, and every other skill reaches it through that location:

- Shared Python code: the packages in the repo-root `lib/` (see Shared packages).
- Every model call: `lib/ai_models`, on Pydantic-AI (`docs/ai_models.md`). TLS and the providers' clients are set up
  there once. No module of a plugin project that depends on `ai-models` imports google-genai or the OpenAI SDK
  (`test_model_calls_only_through_ai_models`).
- Settings: one file, `config.yaml` (`$SKILLS_CONFIG`, else `<config dir>/plugins/data/config.yaml`). It holds the
  providers with their keys, the model of each task, the local `diffusers` models and, under `settings`, every other
  setting. A skill has no model setting and no model default in code; it asks `ai_models` for a task (`chat`,
  `vision`, `system1`, `image`, `image_edit`, `speech`, `music`, `audio`) or passes the user's `--model`.
- Reading the settings file and the plugin data directory: `lib/plugin_settings`. `ai_models` reads the file through
  it.
- Model routes, the table of which model serves which kind of request: `ai_models.routes`, with the defaults in
  `lib/ai_models/ai_models/routes.md` and the user's rows in `routes.md` beside the settings file
  (`docs/ai_models.md`, Model routes). Each skill that calls a model prints the table with its `routes` command.
- Brands (logos, colours, fonts, guidelines, PowerPoint templates): `brand:brand`. Callers get a brand folder
  from it, locate each file through its `brand.yaml` key and read it in place without keeping a copy.
- Visual styles: `brand:style`. A brand's `styles` key restricts the styles a branded image may use.
- Installation and settings documentation, including the settings error messages: `setup:settings`. The
  missing-setting and invalid-setting errors name that skill.
- The template of the settings file, with every setting any skill reads and placeholder values:
  `plugins/setup/skills/settings/assets/config.example.yaml`. `setup:settings` creates the user's file from it.
- Maintainer documentation: `docs/`.

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
`config.yaml`: a setting is `settings.<KEY>` of the file, else the variable of the process environment
(`docs/plugin_settings.md`). The settings that libraries and child processes read from the environment (proxies,
`SSL_CERT_FILE`, `NODE_EXTRA_CA_CERTS`, `HF_HOME`, `HF_TOKEN`) are exported there by `Plugin.load`.

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
`skills/` and `/scripts`, `/` as `-`. The path is kept short for espeak-ng, used by voiceover's kokoro backend
(`docs/voiceover.md`).

A wrapper can source no file outside its plugin, so each plugin with wrappers carries its own copy of `uv_env.sh`.
Tests: `test_every_plugin_with_wrappers_has_uv_env`, `test_uv_env_copies_identical`, `test_uv_env_data_dir` (runs
`plugin_env` under `set -eu -o pipefail`, as the wrappers do, and compares its data directory with the one
`plugin_settings` resolves).

## CLI wrappers

Each skill with a CLI tool has its own uv project and environment, so its dependencies do not constrain another skill's.
The wrapper unsets `VIRTUAL_ENV`, so a parent venv cannot replace the project's environment. The image-gen and music wrappers add `--extra local` (torch and diffusers, through
`ai-models[diffusers]`) when `config.yaml` (`SKILLS_CONFIG`, else `<config dir>/plugins/data/config.yaml`) has a
provider of kind `diffusers`, so a user without local models does not install torch. The repo-root `pyproject.toml`
is used by the plugin and library test suites.
`SKILL.md` calls the wrapper as `${CLAUDE_SKILL_DIR}/scripts/<skill>.sh`, and `allowed-tools` pre-approves only that
wrapper: `Bash(${CLAUDE_SKILL_DIR}/scripts/<skill>.sh:*)`, and in most skills also the relative form
`Bash(scripts/<skill>.sh:*)` (`_own_wrapper_rule` accepts both). No `allowed-tools` entry starts with `Bash(*`, which
would pre-approve any command ending in the wrapper path (`test_allowed_tools_no_unanchored_bash_rules`).

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
contains `TRIGGER when:` (`test_skill_frontmatter`, `test_skills_found`). Material the agent needs only for some tasks
is in the skill's `references/`, loaded on demand.

`SKILL.md` and `references/` are read from an installed plugin, where `docs/`, `CLAUDE.md` and the repository root do
not exist. They therefore never point to `docs/` or to a repo-root file; no test checks this. `docs/` is for
maintainers of this repository: how the code works and why, where the code does not show it.

## Tests

All tests run in one environment, the repo-root project's `dev` group, from the repository root
(`scripts/tests.sh unit|integration|all`, commands in `CLAUDE.md`). The group installs the `lib/` packages as editable
path dependencies (`ai-models` with its `diffusers` extra), so every test sees the working tree's `lib/`, and the
dependencies of every skill project. Its pytest `pythonpath` lists each skill's `scripts/` and the studio server. A
dependency added to a skill project is also added to the root `dev` group, so the suites never need a second
environment. Manim alone runs in its own environment, as a subprocess, for users and tests alike.

Tests call the real code and the real dependency. No test imports a mock library, patches, uses the `monkeypatch` or
`mocker` fixture, uses a fake or stub server, writes the process environment, or skips (`skip`, `skipif`, `xfail`,
`importorskip`, `SkipTest`). The reasons: a mock tests the test's idea of the dependency, not the dependency; an environment write leaks
into other tests; a skipped test reports nothing and hides a missing prerequisite.

A test that needs a setting runs the real code in a child process whose environment it states in full
(`tests/subproc.py`: `child_env`, `run_python`, `py_value`). `tests/settings_env.py` (`isolated`) points `HOME`,
`CLAUDE_CONFIG_DIR` and `CLAUDE_PLUGIN_DATA` of that child at a temporary directory with no settings file, since the
settings file overrides the process environment. It keeps uv's cache, Python installs and configuration and git's
global configuration. A test that needs a setting, a provider or a model writes a real `config.yaml` in a temporary
directory (`write_config`) and passes its path to the child in `SKILLS_CONFIG`; an in-process test of `ai_models`
names it with `config.use`. A test that needs a
key, a model, a GPU or a tool fails with a message naming what is missing (`tests/prereq.py`: `requires`). Model
tests run against real targets: Ollama with small models, real Hugging Face `diffusers` models at small size and few steps, Kokoro for speech,
and the cloud providers when their keys are set. A pipeline whose smallest real checkpoint is too large for a test
(Kandinsky S2V: 23.9 GB) is tested on the random-weight checkpoint its authors publish for that pipeline class; such a
test checks the code path (loading, call, output format), not the output.
