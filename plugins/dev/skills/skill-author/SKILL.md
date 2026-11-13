---
name: skill-author
description: 'Authors and reviews Agent Skills. Scaffolds new skills, validates existing ones against the spec. TRIGGER when: user says "create a skill", "new skill", "review skill", "check skill", "validate skill", "skill audit".'
---

# Skill Author

Authors new Agent Skills and reviews existing ones against the spec. Use it when creating, fixing, or auditing skills in this repo.

## Scope

This skill covers **structure and content**: it scaffolds skill directories, writes conformant `SKILL.md`/frontmatter/scripts, validates them against a checklist tuned for this repo's conventions, and checks the skill's own prose for broken references, contradictions and duplicated rules.

**Out of scope** — this skill does *not* cover:
- Eval-driven iteration (running the skill against test prompts, grading outputs, A/B comparing versions).
- Quantitative benchmarking or description auto-optimization loops.
- Packaging into installable `.skill` bundles.

Those are behavioral concerns — handle them manually. `skill-author` is self-sufficient for authoring and reviewing the *structure* of a skill.

## When to use

- "Create a new skill for X" in this repo → use `skill-author` to scaffold and validate.
- "Review / audit / check skill Y" → use `skill-author` to run the checklist.
- "Fix the skill so it loads / triggers / validates" → use `skill-author`.
- "Is this skill actually any good when invoked?" or "optimize the description via evals" → that's behavioral tuning; `skill-author` does not do it. Handle manually.

## Author a new skill

1. **Gather requirements** — what the skill does, whether it needs scripts, what triggers it.
2. **Scaffold the directory** — per `references/structure.md`.
3. **Write SKILL.md** — frontmatter per `references/frontmatter.md`, body per `references/body.md`.
4. **If skill has scripts** — shell wrapper, pyproject.toml, Python package per `references/cli.md`.
5. **Validate** — run `references/checklist.md` against the result. Fix failures before reporting done.

## Review an existing skill

1. **Identify target** — a skill name, or "all" for every skill in the repo.
2. **Run the checklist** — load `references/checklist.md`, verify every applicable item (A–H).
3. **Report** — procedure, output format and stop condition are in `references/checklist.md`.
4. **Fix on request** — apply corrections and re-validate.

## Rules

- The Agent Skills spec is at https://agentskills.io/specification. The conventions of the repository the skill is in are in its own convention files (its `CLAUDE.md` and the documents that file points to).
- Always measure description length: `echo -n '<description>' | wc -c`
- For skills with scripts, confirm the wrapper runs: `<wrapper> --help`
