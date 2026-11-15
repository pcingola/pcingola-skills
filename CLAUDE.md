# CLAUDE.md

This repository is a Claude Code marketplace, `pcingola-skills` (`.claude-plugin/marketplace.json`), of Agent Skills ([agentskills.io](https://agentskills.io)). Each plugin lives in `plugins/<plugin>/` with its manifest in `.claude-plugin/plugin.json` and its skills in `skills/<skill>/`. Installed, a skill loads as `<plugin>:<skill>` (install ID `<plugin>@pcingola-skills`). The shared Python packages are in `lib/`: `lib/plugin_settings` (data directory and the settings file `config.yaml`) and `lib/ai_models` (every model call, through Pydantic-AI, with the providers and the model of each task in `config.yaml`).

| Plugin | Skills | `dependencies` |
|---|---|---|
| docs | pptx, revealjs-slideshow | brand, setup |
| media | html-animation, image-gen, infographic, music, pptx-author, short-video, video-effects, voiceover | ai, brand, docs, setup |
| dev | plan, skill-author | setup |
| brand | brand, style | setup |
| ai | classify, second-opinion | setup |
| studio | images, videos | brand, media, setup |
| setup | settings | none |

## Rules

Each rule and its reason are in `docs/architecture.md`, with the test that enforces it where one exists.

- A skill reads nothing outside its own plugin directory except its plugin data directory, the settings file, the user's model routes file `routes.md` beside the settings file, a brand folder from `brand:brand`, the user's input and output files and files another skill wrote as output ([Plugin isolation](docs/architecture.md#plugin-isolation)).
- A skill needing another skill loads it with the Skill tool by `<plugin>:<skill>` and states the task in prose; no file names another skill's wrapper, script, `references/` file or a path into it, and no skill's Python imports another skill ([Loading another skill](docs/architecture.md#loading-another-skill)).
- A skill loads only skills of its own plugin or of a plugin in its `dependencies` ([Loading another skill](docs/architecture.md#loading-another-skill)).
- `allowed-tools` lists `Skill` when the skill loads another, and no `Bash` entry, bare `Bash` included, other than its own wrapper rules `Bash(${CLAUDE_SKILL_DIR}/scripts/<skill>.sh:*)` and `Bash(scripts/<skill>.sh:*)`; an exception needs an entry with a reason in `BASH_RULE_ALLOWLIST` of `tests/unit/plugin/test_manifest.py` ([Loading another skill](docs/architecture.md#loading-another-skill)).
- A skill's code does deterministic work; the agent does the judgement and loads other skills ([Agent judgement, code mechanics](docs/architecture.md#agent-judgement-code-mechanics)).
- Shared Python code lives once in `lib/`; plugin projects depend on it as uv git sources on branch `main`. `main` is never force-pushed, and branches are merged into it with merge commits ([Shared packages](docs/architecture.md#shared-packages)).
- A change to `lib/` reaches the skills after it is pushed to `main` and their projects are relocked (`uv lock --upgrade-package ai-models` in each `scripts/`); the changed `uv.lock` files are committed ([Shared packages](docs/architecture.md#shared-packages)).
- Every model call goes through `lib/ai_models`. The providers, their keys (`api_key`) and the model of each task are in `config.yaml` (`<config dir>/plugins/data/config.yaml`), never in code or in a setting ([One home per concern](docs/architecture.md#one-home-per-concern)).
- Brands are only in `brand:brand` and visual styles only in `brand:style`; callers read brand files in place by their `brand.yaml` key and keep no copy ([One home per concern](docs/architecture.md#one-home-per-concern)).
- One settings file, `config.yaml`; there are no `.env` files. Settings are read with `plugin_settings` (`get`, `require`, `invalid`), never from `os.environ` directly. A new setting goes under `settings` in `plugins/setup/skills/settings/assets/config.example.yaml`; one that a library or child process reads from the environment also goes into `ENV_KEYS` of `plugin_settings`; a required one is also documented in `setup:settings` ([Plugin data directory and settings](docs/architecture.md#plugin-data-directory-and-settings)).
- Data kept across runs defaults to the plugin data directory ([Data outside the plugin](docs/architecture.md#data-outside-the-plugin)).
- Nothing generated lives under `plugins/`; environments, `node_modules` and bytecode go under the plugin data directory through `plugins/<plugin>/lib/uv_env.sh`, one byte-identical copy per plugin with wrappers ([Environments outside plugins/](docs/architecture.md#environments-outside-plugins)).
- A CLI skill has `scripts/<skill>.sh`, its own `scripts/pyproject.toml` and a package `<skill>_tool` with hyphens as underscores (image-gen: `image_gen_tool`); `SKILL.md` calls `${CLAUDE_SKILL_DIR}/scripts/<skill>.sh` ([CLI wrappers](docs/architecture.md#cli-wrappers)).
- `plugin.json` has no `version` field ([Installation and versions](docs/architecture.md#installation-and-versions)).
- `SKILL.md` and `references/` never point to `docs/`, `CLAUDE.md` or another repo-root file ([Agent-facing and maintainer documentation](docs/architecture.md#agent-facing-and-maintainer-documentation)).
- A `SKILL.md` description is quoted on one line, at most 250 characters, in the third person, with `TRIGGER when:` fully visible; `name` equals the directory. `dev:skill-author` has the full rules ([Agent-facing and maintainer documentation](docs/architecture.md#agent-facing-and-maintainer-documentation)).
- A new plugin, or a change of a plugin's skills or `dependencies`, is made in its `plugin.json`, `.claude-plugin/marketplace.json`, `PLUGIN_NAMES` and `DEPENDENCIES` of `tests/unit/plugin/test_manifest.py`, and the plugin tables of this file, `README.md` and `setup:settings`.
- Tests of a skill live in `tests/{unit,integration}/<skill with - as _>/`. A dependency added to a skill project is also added to the root `dev` group, and a new skill's `scripts/` to `pythonpath` in the root `pyproject.toml`.
- Tests call the real code and the real dependency: no mocks, no `patch`, no `monkeypatch`, no fakes or stub servers, no `skip`, `skipif`, `xfail` or `importorskip`, and no write to the process environment. A setting goes to a child process with an explicit environment (`tests/subproc.py`); a missing key, model or tool fails the test with a message (`tests/prereq.py`). ([Tests](docs/architecture.md#tests)).
- `uv run --group dev pytest tests/unit/plugin` checks the manifests, every `SKILL.md` frontmatter, cross-skill references and `allowed-tools`; run it after changing any of them ([Tests](docs/architecture.md#tests)).

## Commands

All tests run in one environment, the root project's `dev` group: `lib/` from this directory and the dependencies of every skill project. Its pytest `pythonpath` lists each skill's `scripts/`.

- All tests: `scripts/tests.sh unit|integration|all`, with pytest arguments after it.
- One suite: `uv run --group dev pytest tests/unit/<suite>`; `<suite>` is the skill name with `-` as `_`.
- One test: the pytest node id, for example `uv run --group dev pytest tests/unit/plugin/test_manifest.py::test_marketplace_json`.
- Manifests with Claude Code: `claude plugin validate .` (marketplace) and `claude plugin validate plugins/<plugin>` (each plugin).
- A skill CLI: `plugins/<plugin>/skills/<skill>/scripts/<skill>.sh <command> [args]`.
- One session with a plugin not installed: `claude --plugin-dir plugins/<plugin>`, one flag per plugin.

## Documentation

Maintainer documentation is in `docs/`: `docs/architecture.md` for the repository rules and their reasons, and `docs/<name>.md` for each skill or `lib/` package that has one. Agent-facing documentation is each skill's `SKILL.md` and `references/`. Installation and settings are in `README.md` and `setup:settings`.
