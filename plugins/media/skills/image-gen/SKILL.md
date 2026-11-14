---
name: image-gen
description: "Generates and edits images with the image models of the ai_models config: OpenAI-style, Google or local diffusers models. TRIGGER when: user asks to create, draw, generate, illustrate, or edit an image, icon, logo, banner, diagram, or slide visual."
allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/image-gen.sh:*) Read Skill
metadata:
  author: pcingola
  version: "0.2.0"
---

# Image Generation

Generates and edits images with the models of the settings file
`config.yaml`. `--tier` picks the config task of the model.
`--model <provider>:<model>` names another model of a provider in that file
and replaces the tier's model. Leave `--model` off unless the user names a
model.

## Choosing a tier

| `--tier` | Use for | Task without `--ref` | Task with `--ref` |
|---|---|---|---|
| `fast` (default) | quick drafts, bulk variations, lowest cost | `image` | `image_edit` |
| `best` | best quality, text in the image, transparent background | `image_best` | `image_best` |
| `multi-ref` | combining several reference images, a character or product kept the same across shots | `image_multi_ref` | `image_multi_ref` |

A tier whose task is missing in the config fails with a message naming the
config key (`models.image_best` or `models.image_multi_ref`). Then use
another tier, or ask the user to add the task to the config.

What each provider kind takes:

- Transparent background, `.jpg` and `.webp` output, `--quality`,
  `--background`: OpenAI-style providers (`openai`, `azure`, `openrouter`,
  `ollama`) with a gpt-image model. The other kinds write PNG.
- `--mask`: OpenAI-style providers and local `diffusers` models with an
  `inpaint` pipeline in the config. Google models take none.
- Local `diffusers` models: sizes up to 2048 px on the long edge (`2K` and
  `4K` both give 2048 px). A local edit without `--aspect` and `--size` keeps
  the first `--ref`'s size. They need the skill's `local` extra (torch and
  diffusers, installed when the config has a `diffusers` provider) and a
  CUDA or Apple MPS GPU.

## When the user asks for options

When the user asks for options, alternatives, variations or "a few versions",
generate one image per tier with the same prompt and settings, and name each
file after its tier so the user can compare. Issue one `generate` command per
tier as parallel tool calls in one message. One shell command with `&` and
`wait` is not covered by the pre-approved wrapper rule and asks the user for
permission.

```bash
${CLAUDE_SKILL_DIR}/scripts/image-gen.sh generate --prompt '<prompt>' --out /tmp/<name>_best.png --aspect 3:2 --tier best
${CLAUDE_SKILL_DIR}/scripts/image-gen.sh generate --prompt '<prompt>' --out /tmp/<name>_multi-ref.png --aspect 3:2 --tier multi-ref
${CLAUDE_SKILL_DIR}/scripts/image-gen.sh generate --prompt '<prompt>' --out /tmp/<name>_fast.png --aspect 3:2 --tier fast
```

The models interpret the same prompt differently, so this gives more variety
than `--n` on one model. Leave out a tier whose task the config lacks, and a
tier with the same model as another. If the user wants more options than
there are models, add `--n` to each call. With one model, use `--n`.

## Usage

```bash
${CLAUDE_SKILL_DIR}/scripts/image-gen.sh generate --prompt '<prompt>' --out /tmp/out.png --aspect 16:9
```

**Output location.** By default, write images to the system temporary
directory (`/tmp`), for example `--out /tmp/<name>.png`. Always pass an
absolute `--out` path. Do not use a bare relative path (such as
`images/out.png`). Do not write into the skill directory or the current working
directory: a relative path resolves against the caller's cwd and puts the file
in the wrong place. Write somewhere other than `/tmp` only when the user asks
for a specific destination.

**Always wrap `--prompt` and `--negative` in single quotes.** Single quotes pass
the value literally: no escaping, and double quotes inside the prompt are safe.
Do not use backslash line continuations (`\`); they cause argument parse errors.

## Arguments

| Argument | Required | Default | Description |
|---|---|---|---|
| `--prompt` | Yes | none | Text prompt describing the image |
| `--out` | Yes | none | Absolute output path; default to `/tmp` (e.g. `/tmp/hero.png`) |
| `--negative` | No | `""` | What not to include (folded into the prompt) |
| `--ref` | No | none | Reference image to edit/steer from; repeat for multiple |
| `--mask` | No | none | OpenAI-style and local models: PNG of the first `--ref`'s pixel size, transparent where the image may change |
| `--aspect` | No | `1:1` for gpt-image models, else the model's | `21:9`, `16:9`, `3:2`, `4:3`, `5:4`, `1:1`, `4:5`, `3:4`, `2:3`, `9:16` |
| `--size` | No | `1K` for gpt-image models, else the model's | `1K`, `2K` or `4K` (gpt-image-2 tops out at 3840 px on the long edge, local models at 2048 px) |
| `--n` | No | `1` | Number of images to generate |
| `--tier` | No | `fast` | `fast`, `best`, `multi-ref`: the config task of the model (see "Choosing a tier") |
| `--model` | No | the tier's model | Model id `<provider>:<model>` of the config; replaces the tier's model |
| `--quality` | No | `high` for gpt-image models, else the model's | `low`, `medium`, `high`, `auto`; OpenAI-style models only. Use `low` for drafts |
| `--background` | No | the model's | `auto`, `opaque`, `transparent`; OpenAI-style models only |

## Output

The image is written to `--out`; the saved path is printed to stdout. The
extension sets the format: `.png`, `.jpg`/`.jpeg` or `.webp` with OpenAI-style
models, `.png` only with the others. **Default
the destination to `/tmp`** (e.g. `/tmp/out.png`) unless the user names a
specific location. For `--n > 1`, the CLI inserts an index before the
extension: `/tmp/out.png` gives `/tmp/out_1.png`, `/tmp/out_2.png` and so on.

## Editing / style reference

Pass `--ref path.png` (repeatable) to edit or steer from existing images. This
is the model's image-editing mode. Tier `fast` uses the `image_edit` model,
the other tiers their own task:

```bash
${CLAUDE_SKILL_DIR}/scripts/image-gen.sh generate --prompt 'Make the sky a dramatic sunset' --ref /tmp/photo.png --out /tmp/edited.png --aspect 16:9
```

> Use a single command line. Do not split it with `\` continuations.

To change only part of an image with an OpenAI-style or local model, add `--mask mask.png`: a PNG of the same
pixel size as the first `--ref`, fully transparent where the image may change and opaque elsewhere. The mask guides
the model; it may still redraw the rest of the image slightly, so the prompt names what to change in the masked area
and says to keep the rest. The Google models take no mask; with them, mark the areas on a copy of the
image and pass it as a second `--ref`.

```bash
${CLAUDE_SKILL_DIR}/scripts/image-gen.sh generate --prompt 'Replace the cup in the masked area with a glass of water; keep the rest of the image as it is' --ref /tmp/photo.png --mask /tmp/mask.png --out /tmp/edited.png --aspect 4:3
```

## Examples

**Decorative slide image**:
```bash
${CLAUDE_SKILL_DIR}/scripts/image-gen.sh generate --prompt 'Abstract flowing lines in blue gradient, clean modern style, no text' --out /tmp/hero.png --aspect 16:9
```

**Transparent icon** (a gpt-image model; the Google and local models have no transparent background):
```bash
${CLAUDE_SKILL_DIR}/scripts/image-gen.sh generate --prompt 'Flat lightning bolt icon, navy and teal' --out /tmp/icon.png --tier best --background transparent
```

**Several references** (a product kept the same in a new scene):
```bash
${CLAUDE_SKILL_DIR}/scripts/image-gen.sh generate --prompt 'The bottle from the first image on the table from the second image' --ref /tmp/bottle.png --ref /tmp/table.png --out /tmp/scene.png --tier multi-ref
```

**Fast drafts**:
```bash
${CLAUDE_SKILL_DIR}/scripts/image-gen.sh generate --prompt 'Workshop bench with hand tools, soft morning light' --out /tmp/draft.png --aspect 3:2 --n 4 --quality low
```

**Prompt with double quotes inside**:
```bash
${CLAUDE_SKILL_DIR}/scripts/image-gen.sh generate --prompt 'Title says "Spring Festival 2026" in bold navy blue' --out /tmp/title.png --aspect 16:9
```

## Configuration

The providers, their keys and the model of each task (`image`, `image_edit`,
`image_best`, `image_multi_ref`) are in the `ai_models` config file; local models are its `diffusers` entries.
The skill has no model settings of its own. Behind a TLS-intercepting proxy,
set `EXTRA_CA_CERT` (else `NODE_EXTRA_CA_CERTS` is used) to the proxy root CA
PEM file; it is added to the certifi roots.
