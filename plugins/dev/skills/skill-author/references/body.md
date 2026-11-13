# SKILL.md Body

The body follows the YAML frontmatter. Budget: ≤500 lines / ~5000 tokens. Move heavy content to `references/`.

Start with an H1 matching the skill's display name (e.g. `# Image Gen`).

## Structure

1. **Introduction** — one paragraph: what the skill does, when to use it.
2. **Instructions** — numbered steps for the primary workflow. Multiple modes get separate subsections.
3. **CLI reference** (if applicable) — commands grouped by category, each with syntax and key flags.
4. **Rules** — bullet list of constraints the agent must follow.

## Progressive disclosure

Skills load in three tiers:

1. **Metadata** (~100 tokens): `name` + `description` only, loaded at startup for every skill. This is the only matching surface.
2. **SKILL.md body** (<5000 tokens): loaded once the skill activates.
3. **Resources** (on demand): `references/`, `scripts/` and `assets/` files loaded only when the agent reads them.

Design the body as the always-loaded middle tier. Anything long, rarely-needed, or only useful during a specific sub-task belongs in a reference file the body links to — not inline.

Keep references one level deep: `SKILL.md` → `references/topic.md`. Don't chain (`references/a.md` → `references/b.md` → `references/c.md`). Flatten instead.

## Principles

- Agent-facing only — no implementation details or architecture (those go in `docs/<skill>.md`).
- Document outputs — where files are written, what format.
- Call out non-obvious behavior (e.g., "batch correction is OFF by default").
- File links relative to the skill root: `references/topic.md`. Commands the agent runs use `${CLAUDE_SKILL_DIR}/scripts/<name>.sh`; a bare `scripts/<name>.sh` resolves against the user's working directory and fails in an installed plugin.
- Another skill is loaded with the Skill tool and given a task (input, wanted result, output location), never called through its wrapper, script path or references (see `references/structure.md`).
- Every referenced file must exist on disk.
