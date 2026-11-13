# Directory Structure

A skill is a directory containing a `SKILL.md`. In this repo every skill lives under `plugins/<plugin>/skills/<name>/`, where `<plugin>` is one of `ai`, `brand`, `dev`, `docs`, `media`, `setup` and `studio`. Two shapes: knowledge-only (no scripts) and CLI (with scripts).

### Non-CLI skill

```
skill-name/
├── SKILL.md
└── references/          # optional
    └── topic.md
```

A skill that needs another skill loads it with the Skill tool, named `<plugin>:<skill>`, and states the task: the input, the wanted result, where the output goes and any required options in prose ("convert `<src>.pdf` to Markdown in directory mode with CSV table sidecars into `<out>/`"). The loaded skill's `SKILL.md` gives the command and its `allowed-tools` cover its wrapper. A retrieval skill, for example, loads the PDF skill and asks for directory-mode Markdown. This holds for a skill of the same plugin too. A skill that loads another skill has it in its own plugin or in a plugin listed in its `dependencies` (`.claude-plugin/plugin.json`).

No file in a skill directory names another skill's wrapper (`<x>.sh` of skill x), script path, `references/` file or a path from its own directory into another skill (`../<x>/`). Where a caller needs a data format the callee defines, it refers to it by name ("in the JSON format the slides skill documents for adding text"), not by file path. Files another skill wrote as its output (a `content.md`, a `timing.json`) are data and may be read. Every operation a caller asks for is documented in the callee's `SKILL.md` or its references.

### CLI skill

```
skill-name/
├── SKILL.md
├── scripts/
│   ├── skill-name.sh              # shell wrapper (executable)
│   ├── pyproject.toml
│   └── skill_name_tool/           # Python package (underscores + _tool suffix)
│       ├── __init__.py
│       ├── __main__.py
│       ├── skill_name.py          # main module with main() + argparse
│       ├── cmd_*.py               # optional: command group modules
│       └── common.py              # optional: shared utilities
├── references/                    # optional: agent-facing docs loaded on demand
└── assets/                        # optional: templates, images, data files
```

`references/` and `assets/` are progressive-disclosure tier-3 dirs. Convention in this repo:
- `references/`: markdown docs the agent reads when the SKILL.md body links to them (e.g. `references/topic.md`).
- `assets/` — binary templates, images, sample data (pptx templates, fonts, etc.).

## Naming

| Thing | Convention |
|-------|------------|
| Directory | `my-skill` |
| `name` field | matches directory |
| Shell wrapper | `scripts/my-skill.sh` |
| Python package | `my_skill_tool/` (in scripts/) |
| pyproject.toml | `scripts/pyproject.toml` |
| Test dirs | `tests/{unit,integration}/my_skill/` (hyphens become underscores) |
