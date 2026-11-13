# Frontmatter

## `name` (required)

1–64 chars, lowercase alphanumeric + hyphens, no leading/trailing/consecutive hyphens. Must match the parent directory name.

Regex: `^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$`

## `description` (required)

Must be a literal single line — multi-line YAML breaks the parser. Quote the value: `TRIGGER when:` contains `: `, which is invalid in a plain YAML scalar. Use double quotes, or single quotes when the text contains double quotes.

Structure:
1. Capability sentence in third person — "Extracts text from PDFs", not "Use this skill to…"
2. `TRIGGER when:` — concrete user phrases, file extensions, task patterns

**Length limit:** ≤250 chars — the skill list truncates beyond ~250, so anything past that is invisible at match time.

**Front-load triggers:** `TRIGGER when:` must start early enough that the full trigger list fits within 250 chars. A capability sentence that eats 200 chars leaves no room for triggers before truncation — the skill will silently fail to match. Keep the capability sentence tight.

Always measure: `echo -n '<description>' | wc -c`

### Good

```
Analyzes datasets in CSV, TSV, and Excel formats. Generates summary statistics, filters rows, and produces charts. TRIGGER when: user asks to explore, summarize, or visualize tabular data.
```

### Bad

```
Use this skill to analyze data
# first person, no TRIGGER when
```

```
A very powerful and flexible tool that can do many things including reading, writing, converting, transforming, analyzing, summarizing, filtering, grouping, aggregating, pivoting, and producing charts from ... TRIGGER when: user mentions spreadsheet.
# capability sentence eats the 250-char window — TRIGGER when buried past the limit
```

```
Helps with documents
# vague — no TRIGGER, no specifics
```

### Anti-patterns

- **Missing TRIGGER** — capability alone isn't enough; the agent needs matching patterns.
- **Vague triggers** — "when needed" or "when relevant" don't help matching. Use concrete phrases.
- **First/second person** — "I can help you" or "Use this skill to" break system prompt context.
- **Repeating the skill name** — wastes chars; use the space for trigger keywords instead.

## `allowed-tools` (optional)

Space-delimited. Include both path forms for own scripts:

```yaml
allowed-tools: Bash(scripts/<name>.sh:*) Bash(${CLAUDE_SKILL_DIR}/scripts/<name>.sh:*)
```

List no other skill's wrapper. A skill that loads another skill lists `Skill`; the loaded skill's own `allowed-tools` pre-approve its wrapper:

```yaml
allowed-tools: Bash(scripts/<name>.sh:*) Bash(${CLAUDE_SKILL_DIR}/scripts/<name>.sh:*) Skill
```

Any other `Bash(...)` rule, and bare `Bash`, needs an entry with a reason in `BASH_RULE_ALLOWLIST` in `tests/unit/plugin/test_manifest.py`.

## `metadata` (optional)

Arbitrary string-to-string key-value map. Use it for free-form keys like `author`, `version`, `date`.

## Other optional fields

- `license` — license name or reference to bundled file
- `compatibility`: ≤500 chars. Declare runtime/system requirements here: external tools or system packages the skill shells out to (not pip deps), with install hints. Example (a skill that renders slides): `Requires LibreOffice and Poppler (pdftoppm) for visual-preview and export-slides. macOS: brew install libreoffice poppler. Linux: apt-get install libreoffice poppler-utils.`
