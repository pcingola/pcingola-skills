---
name: pptx
description: "Runs raw .pptx operations: inspect a template or master, fill placeholders, add shapes and fitted text, check overflow, copy slides, export slide images. TRIGGER when: media:pptx-author or a user asks for one of these on a .pptx."
allowed-tools: Bash(scripts/pptx.sh:*) Bash(${CLAUDE_SKILL_DIR}/scripts/pptx.sh:*)
compatibility: "Requires LibreOffice and Poppler (pdftoppm) for the visual-preview and export-slides commands. macOS: brew install libreoffice poppler. Linux: apt-get install libreoffice poppler-utils."
---

# PPTX Skill

Raw operations on `.pptx` files. The `pptx-author` skill of the media plugin calls these commands to build and check its decks. The agent calls them directly when a user asks for one of these operations on a `.pptx` file. A request to design a new deck goes to a deck authoring skill.

- **Template decks**: `inspect-template` and `inspect-master` describe the slides and layouts, `select-slides` copies the chosen slides into a working deck, `add-slide` adds new slides from the layouts by name (for a template with layouts and no example slides), `extract-shapes` lists their shapes, `add-text`/`add-table`/`add-chart`/`add-images` or `edit` fill them. See [references/template-decks.md](references/template-decks.md) for the procedure and the JSON formats.
- **Free-form slides**: `new-deck` makes a blank canvas and `add-shapes` places native shapes and pictures at inch coordinates, with measured text. See [references/blank-canvas.md](references/blank-canvas.md).
- **Speaker notes**: `add-notes` sets per-slide notes text on any deck. See [references/blank-canvas.md](references/blank-canvas.md#3-set-speaker-notes-add-notes).

## Inspecting a deck

Commands run as `${CLAUDE_SKILL_DIR}/scripts/pptx.sh <command> [args]`.

- `inspect-master <file> <out.json>`: Shapes of every slide master (`slide_masters`) and layout (`slide_layouts`, with `non_placeholder_shapes` counts): position, text, fonts, fill, rotation. Shapes are flagged `possible_confidentiality_tag` (a `!` or "confidential"), `template_artifact` ("example", "template", "click to edit"), `rotated_shape` and `off_canvas` (outside a 13.33" x 7.5" canvas). Master shapes are often off-canvas and invisible in rendered slides.
- `visual-preview <file> [prefix] [--cols 3-6] [--outline-text]`: Thumbnail-grid JPEGs of all slides. The second argument is an output file prefix, not a directory. `--outline-text` outlines text placeholders in red. Requires LibreOffice and Poppler.
- `list-images <file>`: Embedded images per slide.
- `extract-images <file> -o <dir> [--min-bytes N] [--min-pixels WxH]`: Write embedded images at their stored resolution into `<dir>`; skips images under 2048 bytes or 50x50 px by default.

## Native charts (`add-chart`)

`add-chart <in.pptx> <out.pptx> <slide> <chart-data.json> [--index N]`: Replace an OBJECT placeholder with a **native, editable chart**: a real chart object carrying its data table, not a picture of one. `--index` picks which OBJECT placeholder on that slide (default 0).

```json
{"chart_type": 51,
 "data": {"categories": ["Q1", "Q2"],
          "series": [{"name": "Revenue", "values": [10, 20]}],
          "x_axis_title": "Quarter", "y_axis_title": "USD m", "title": "Revenue by quarter"}}
```

`chart_type` is `51` (clustered column) or `5` (pie). Pie labels show the values you supply, so percentages must be pre-computed.

## Several operations in one call (`edit`)

`edit <in.pptx> <out.pptx> <spec>`: Apply a list of operations in order. `spec` is a path, `@path`, or an inline JSON string.

```json
{"operations": [
  {"action": "copy-slide", "source": "deck.pptx", "source_indices": [4], "position": 1},
  {"action": "add-text", "data": {"slide-1": {"shape-0": {"paragraphs": [{"text": "Title"}]}}}},
  {"action": "add-chart", "slide": 1, "index": 0, "data": {"chart_type": 51, "data": {}}},
  {"action": "add-images", "slide": 2, "images": ["a.png", "b.png"], "type": "OBJECT"},
  {"action": "add-notes", "slide": 1, "data": "Talk track"}
]}
```

Every action name is a command name: `add-text`, `add-table`, `add-notes`, `add-chart`, `add-images`, `add-slide`, `copy-slide`, `delete-slide`. Each takes that command's arguments as JSON keys; `data` is the command's usual `slide-N`-keyed payload, or a bare payload next to a `slide` index. `delete-slide` takes `indices`; `add-slide` takes `layouts` (a list of layout names) and an optional `position`.

`edit` is **atomic**: the output is written only after every operation succeeds, so a failure at step 7 of 9 leaves no half-written deck. Prefer it over a chain of separate calls for anything past two steps.

`add-slide <in.pptx> <out.pptx> <layout names> [--position N]` adds one new slide per comma-separated layout name of the deck's own layouts, at a 0-based position or appended. The new slides have the layout's placeholders, empty; `extract-shapes` lists their empty TITLE, CENTER_TITLE, SUBTITLE, BODY and OBJECT placeholders, so `add-text` fills them. The layout names and their placeholders are in the `slide_layouts` of `inspect-master`. An unknown name is an error that lists the deck's layouts.

`copy-slide <source> <target> <out> <indices> [--position N]` inserts at a 0-based position in the target (several slides keep their source order); without `--position` the slides are appended.

## Checking a finished deck (`validate`)

`validate <file> [out.json]`: One JSON report: `text_issues` (overflow, off-slide, overlap, hand-typed bullets; same detection as `extract-shapes --issues-only`), `empty_text_placeholders` (title/body placeholders with no text) and `unfilled_visual_placeholders` (PICTURE/OBJECT/CHART/MEDIA placeholders still empty; an OBJECT placeholder holding text counts as filled). Exit code `0` clean, `2` problems found, `1` error. Writes to stdout without `out.json`.

## Extracting all text as a flat dump (`extract-text`)

`extract-text <file> [-o out.txt] [--slide N] [--json]`: Dump every non-empty paragraph as one line: slide number, layout name, shape label, and the text. No formatting metadata, no border declarations, no fill colors.

Typical output: **about 50 to 200 lines** for a full deck vs **4000+ lines** from `extract-shapes`. Small enough that the output never hits a read-truncation limit, so text-quality checks (trailing periods, broken cross-references, stale template values) see every paragraph including footnotes buried at the bottom of large tables.

```
S01  Title Slide  DATE@1.20",6.50"       March 2026
S04  Blank        TEXT@0.50",7.10"       See the appendix for details.
S04  Blank        TABLE[5,1]@0.30",0.40" Quarterly summary
```

Options:
- `--slide N`: restrict to a single slide (0-based index)
- `--json`: emit a JSON array (`[{"slide":N,"layout":"...","shape":"...","text":"..."}]`) instead of plain text
- `-o <file>`: write to file instead of stdout

Use this as the first step for any text-content check. Only reach for `extract-shapes` when you need position, font, color, or border data.

## Exporting individual slide images (`export-slides`)

`export-slides <file> <output_dir/> [--dpi 150] [--format png|jpg]`: Render each slide as a separate image file.

Writes `slide_01.png`, `slide_02.png`, ... into the output directory (created if needed). Uses LibreOffice + pdftoppm internally (same requirements as `visual-preview`).

Options:
- `--dpi`: render resolution (default: 150)
- `--format`: `png` (default) or `jpg`

Use this when you need to inspect or annotate individual slides at image level, or pass a specific slide to a vision model.
