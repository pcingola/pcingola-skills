# Prompt contract

A **job = a `template.md` + a journal + `--var` values**. For each pending journal
item the runner renders the template and pipes it to `claude -p` as one fresh,
full-context invocation.

## Reserved placeholders (auto-injected every invocation)

| Placeholder | Value |
|---|---|
| `{item_path}` | The current item's primary file (`entry.files[0]`). |
| `{item_paths}` | All files on the entry, newline-joined (for cluster items with N files → one invocation). |
| `{signal_done}` | `done` — the success keyword. |
| `{signal_transient}` | `error_transient` — the transient-failure keyword. |
| `{signal_fatal}` | `error_fatal` — the fatal-failure keyword. |

Every other `{placeholder}` in the template **must** be supplied via `--var k=v`
(output dirs, paths, model hints, extra instructions). A missing var fails fast:

```
error: template needs {out_dir}; pass --var out_dir=...
```

The template author owns all domain specifics; the skill is domain-agnostic.

## Terminal signal (required)

The template **must** instruct the agent to end its response with exactly one line:

```
{signal_done}: <payload>            # success — payload is job-specific
{signal_transient}: <reason>        # network/timeout/rate-limit — safe to retry
{signal_fatal}: <reason>            # corrupt/unreadable/malformed — skip, don't retry
```

The colon separates the keyword from the payload. `classify()` scans the agent's
final response **in reverse** and takes the first line that starts with a known
keyword. The text after the colon, stripped, is the payload or the error reason
recorded in the journal. **If no signal line is present, the item is treated as
`error_transient`** (so a crashed/silent run is retried, not silently dropped).

## Worked example

`template.md`:

```markdown
Read the document at {item_path}.
Extract every product name and its price.
Append results to {out_dir}/products.md.

End your response with exactly one line:
{signal_done}: <count of products found>
{signal_transient}: <reason>
{signal_fatal}: <reason>
```

Run it:

```bash
${CLAUDE_SKILL_DIR}/scripts/batch-run.sh scan jobs/extract.json 'data/pdfs/*.pdf'
${CLAUDE_SKILL_DIR}/scripts/batch-run.sh run  jobs/extract.json template.md --var out_dir=results
```

## Cluster items (N files → one invocation)

`JournalEntry.files` is a list. `add`/`scan` create one-file entries; a template
that needs all files of a cluster item uses `{item_paths}` (newline-joined) instead
of `{item_path}`.
