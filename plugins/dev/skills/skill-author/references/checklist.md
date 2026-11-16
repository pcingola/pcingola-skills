# Review Checklist

Run every applicable item. Items marked *(CLI)* apply only to skills with scripts.

## How to run a review

- Read the actual files first: `SKILL.md`, every file under `references/`, and any document the skill names as its source of truth. Do not assume content.
- Report findings and wait. Apply fixes only when asked, and only the ones asked for. A review that rewrites files as it goes cannot itself be reviewed.
- Every finding cites `file:line` and is verifiable against something outside the sentence it appears in.
- A reviewed skill returns zero findings. If nothing clears the bar, say so and stop. Zero is the expected result on a mature skill, not a sign the review was skipped.
- Output one table, nothing else. No summary of the skill, no note on what it does well.

  | # | file:line | check | what breaks | fix |

---

## A. Frontmatter

- A1. `name` is present, matches `^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$`, and matches the parent directory name
- A2. `description` is present, quoted, single-line, ≤250 chars. Verify: `echo -n '<desc>' | wc -c`
- A3. Description starts with a third-person verb ("Extracts…", not "Use this…")
- A4. Description contains `TRIGGER when:` with concrete user phrases or file extensions
- A4b. `TRIGGER when:` is front-loaded — the full trigger list sits within the 250-char window, not buried behind a long capability sentence. If the capability sentence runs past ~120 chars, triggers will be truncated and the skill won't match
- A5. `allowed-tools` (if present): every script path exists and is executable; both `scripts/` and `${CLAUDE_SKILL_DIR}/scripts/` paths included for own scripts
- A6. If the SKILL.md body or a `references/` file names another skill (`<plugin>:<skill>`), `allowed-tools` lists `Skill` and that skill is in the skill's own plugin or in a plugin listed in its `dependencies`. `allowed-tools` lists no other skill's wrapper rule, and no file in the skill names another skill's wrapper, script path, `references/` file or a path from its own directory into another skill (`../<x>/`): the caller loads the skill and states the task
- A7. If the skill shells out to system packages or external tools (e.g. LibreOffice, Poppler), they're declared in the `compatibility` field with install hints

## B. Directory structure

- B1. `SKILL.md` exists at skill root
- B2. No stray files at root that don't belong (see `references/structure.md`)
- B3. No committed secrets (`config.yaml`, API keys). Code loads settings with `plugin_settings` (`Plugin.of(__file__).load()`, which validates the whole `config.yaml` and exits naming the YAML path of each problem) and reads them as typed attributes of the returned config or of `plugin_settings.config()`, for example `config().studio.dir` (never from `os.environ`: `config.yaml` is the only source of a setting). A new setting is a field of its section's class in the `plugin_settings` schema, where its type, default and validators check it, and is documented in the `assets/config.example.yaml` of the settings skill of the setup plugin
- B4. All files referenced in SKILL.md body exist on disk
- B5. *(CLI)* `scripts/` dir with `<name>.sh`, `pyproject.toml`, and `<name>_tool/` package

## C. SKILL.md body

- C1. ≤500 lines / ~5000 tokens
- C2. Agent-facing only — no implementation details or architecture (push to `docs/<skill>.md`)
- C3. Has step-by-step instructions for primary workflow
- C4. Documents command syntax if skill has scripts
- C5. Documents outputs — where files are written, what format
- C6. Calls out non-obvious behavior
- C7. References are one level deep — SKILL.md → `references/topic.md`, no nested chains (e.g. `references/a.md` linking to `references/b.md` linking to `references/c.md`)

## D. Shell wrapper *(CLI)*

- D1. Exists at `scripts/<name>.sh` and is executable
- D2. Follows repo boilerplate (`#!/bin/bash -eu`, `set -o pipefail`, `SCRIPT_DIR`, `unset VIRTUAL_ENV`, `PYTHONPATH`, `source .../lib/uv_env.sh` + `plugin_env "$SCRIPT_DIR"`, `exec uv run --project`, `python -m <pkg>_tool "$@"`)
- D3. Runs without import errors: `<wrapper> --help` exits 0

## E. Python package *(CLI)*

- E1. `scripts/pyproject.toml` with `requires-python = ">=3.11"`
- E2. Package is `scripts/<name>_tool/` with `__init__.py`, `__main__.py`, argparse dispatch

## F. Tests *(CLI)*

- F1. Tests live at `tests/{unit,integration}/<name>/` (hyphens in `<name>` become underscores), run with pytest (`unittest.TestCase` classes are collected too), and pass with `uv run --group dev pytest tests/unit/<name>` from the repository root; `scripts/pyproject.toml` has a `dev` dependency group with `pytest`
- F2. Every dependency of the skill's `scripts/pyproject.toml` is also in the root `dev` group, and the skill's `scripts/` is in the pytest `pythonpath` of the root `pyproject.toml`
- F3. Script logic: import module functions directly and test with real inputs and the real dependency. No mocks, `patch`, `monkeypatch`, fakes or stub servers, no skipped tests, no write to `os.environ`; a test that needs a setting writes a `config.yaml` and runs the code in a child process with an explicit environment whose `SKILLS_CONFIG` names that file, and a missing key, model or tool fails the test with a message
- F4. Test data lives under `tests/data/`
- F5. Integration tests at `tests/integration/<name>/` (same naming as F1) exercise the skill's CLI end-to-end
- F6. Skills that call external services or models test against the real service: small local models (Ollama, tiny `diffusers` pipelines) where they exist, cloud providers when their key is set; a missing key or model fails the test with a message naming it

## G. Repo cross-references

- G1. Skill follows the conventions of the repository it is in, as its `CLAUDE.md` and the documents that file points to state them (applies to all skills, CLI or not)
- G2. Skill listed wherever that repository lists its skills (for example plugin tables in `CLAUDE.md` and `README.md`), under the plugin that holds it

## H. Content consistency

A–G cover structure. These cover the skill's own prose: whether it is internally consistent and states each rule once.

- H1. Broken reference. Beyond B4 (files exist): a named section, table row, rule number, tool, or external object the skill depends on (a folder, endpoint, or path) that does not exist. Verify it exists rather than assuming
- H2. Contradiction. Two places state incompatible things. Quote both
- H3. Undefined case. A workflow branch, input, or state with no defined handling
- H4. Unimplementable instruction. The body requires something the frontmatter's `allowed-tools` does not permit
- H5. Duplicated rule. The same instruction stated normatively in two places. Name the file that owns it; the other points to it instead of restating it

**Not findings.** Wording, tone, heading style, section order, length, stub phrasing, and how much a rule is explained. Do not rewrite a sentence into an equivalent one. Prose you would have phrased differently is not a defect, and neither is a decision you would have made another way.

H5 is the only check on redundancy. "This rule is stated in two files" is a finding. "This could be tighter" never is.
