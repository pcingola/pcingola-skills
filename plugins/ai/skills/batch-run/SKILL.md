---
name: batch-run
description: "Runs journal-driven batch Claude jobs: one fresh `claude -p` per item, resumable, with retry. TRIGGER when: user says run a batch job, batch inference, process many files/PDFs with Claude, resumable/unattended batch, or retry failed batch items."
allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/batch-run.sh:*) Bash(scripts/batch-run.sh:*)
metadata:
  version: "0.1.0"
---

# Batch Run

Runs a batch-style Claude job: iterates a list of items, runs one fresh
`claude -p` invocation per item from a prompt template, tracks progress in a
resumable JSON journal on disk, classifies each result as success, transient
failure or fatal failure, and retries failures.

Use it instead of an in-session Workflow or Agent fan-out when the job needs
any of: resume across separate process runs (the journal survives a crash),
a fresh full `claude -p` context per item (its own permissions, no shared
context), selective retry of transient failures, or unattended sequential
runs with an ETA. For quick in-session parallelism the Workflow tool is
enough.

## Define a job

A job has three parts:

1. A journal: a JSON file that lists items and tracks the status of each.
2. A template: a Markdown prompt with `{placeholders}`, rendered once per item.
3. `--var k=v`: values for every non-reserved placeholder in the template.

Reserved placeholders, injected automatically: `{item_path}`, `{item_paths}`,
`{signal_done}`, `{signal_transient}`, `{signal_fatal}`. The template must
end by telling the agent to finish with exactly one line:

```
{signal_done}: <payload>            # success
{signal_transient}: <reason>        # network or timeout, safe to retry
{signal_fatal}: <reason>            # corrupt or unreadable, skip
```

The full protocol and a worked example are in `references/prompt-contract.md`.

## Workflow

```bash
# 1. Populate the journal (glob scan, or add explicit paths)
${CLAUDE_SKILL_DIR}/scripts/batch-run.sh scan jobs/extract.json 'data/pdfs/*.pdf'

# 2. Run all pending items through the template
${CLAUDE_SKILL_DIR}/scripts/batch-run.sh run  jobs/extract.json template.md --var out_dir=results

# 3. Inspect
${CLAUDE_SKILL_DIR}/scripts/batch-run.sh list jobs/extract.json -v

# 4. Retry failures, then run again (resume is automatic)
${CLAUDE_SKILL_DIR}/scripts/batch-run.sh retry jobs/extract.json
${CLAUDE_SKILL_DIR}/scripts/batch-run.sh run   jobs/extract.json template.md --var out_dir=results
```

## Command reference

| Command | Purpose |
|---|---|
| `scan <journal> <glob>...` | Add files matching the globs as pending entries. `--cwd DIR` sets the base dir. |
| `add <journal> <path>...` | Add specific paths, one entry each. |
| `list <journal> [-v]` | Show items and status; `-v` shows the full error history. |
| `done <journal> <n>` | Mark item `n` (1-based) done. |
| `error <journal> <n> --reason TEXT [--fatal]` | Mark item `n` failed (transient, or fatal with `--fatal`). |
| `retry <journal> [--all]` | Reset transient failures to pending; `--all` also resets fatal ones. |
| `run <journal> <template.md> [flags]` | Run pending items through the template. |

`run` flags:
- `--var k=v` (repeatable): a template variable.
- `--cwd DIR`: working dir of the `claude` subprocess (default: current dir).
- `--settings S`: passed as `claude --settings S` (omitted by default).
- `--runs-dir DIR`: where per-item stream-json logs and `batch-run.log` go (default: `./batch-runs`).

## Outputs

- The journal JSON is updated in place after each item, with an atomic write.
- Per-item Claude stream-json logs and `batch-run.log` go under `--runs-dir`
  (default `./batch-runs`). Live progress (agent text, tool calls, the
  `── RESULT ──` block) prints to the terminal as each item runs.

## Rules

- Resume is automatic. Rerunning the same `run` command starts at the first
  item still pending. Journal writes are atomic, so a crash mid-run is safe.
- One signal line is required. A response with no `{signal_done}:`,
  `{signal_transient}:` or `{signal_fatal}:` line counts as
  `error_transient`, and the item runs again after `retry` and `run`.
- A `--var` mismatch fails fast. A placeholder with no reserved value and no
  `--var` stops the run with a message before Claude starts.
- Runs are unattended and use `--dangerously-skip-permissions`, so the batch
  never blocks on a permission prompt. Run only templates and data you trust.
