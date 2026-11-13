# 4. Native build

`slides.md` plus `outline.md` become a deck. Every file operation here is done by the
`docs:pptx` skill, loaded with the Skill tool; each step names the operation and its inputs
and outputs, and `docs:pptx`'s `SKILL.md` gives the command. The input is the template
`<presentation.pptx>` of the deck's brand (see "The template" in `SKILL.md`).

## Build order is fixed

```
1. edit            presentation.pptx → <name>.pptx    (one spec:
                   delete example slides → add-slide → text → figures → notes)
2. export-slides   from the deliverable, --dpi 150     (read the images back)
```

The order inside the spec is not a preference:

- **Example slides go first.** If `<presentation.json>` lists example slides, a
  `delete-slide` of all of them (indices `0` to `n-1`) is the first operation, so the deck
  holds only the new slides. The `neutral` template has none; skip it.
- **`add-slide` before text.** It adds one slide per name of `template_mapping`, in order,
  so deck `slide-0` is the first name and every downstream key is a deck position.
- **`add-text` clears the text of every text shape in the deck** before applying its JSON. It
  runs before any figure, and its JSON carries every piece of text on every slide.
- **A figure replaces its placeholder with a shape**, which shifts every `shape-N` after it
  in `extract-shapes` output. Text applied afterwards would address the wrong shapes.
- **Notes last**: they touch nothing on the slide.

Always write the spec against `shape-N` from the slot map in
[03-layout-mapping.md](03-layout-mapping.md) (or the slot map in `outline.md` for another
brand's template), never against numbers read off a deck that already has a figure in it.

## Step 1a: `template_mapping` → `add-slide`

`template_mapping = ["Title Slide", "Title and Content", "Two Content", "Title and Content", "Section Header"]`
becomes the operation:

```json
{"action": "add-slide", "layouts": ["Title Slide", "Title and Content", "Two Content",
                                    "Title and Content", "Section Header"]}
```

The deck's slides are then `slide-0` to `slide-4` in that order. Layouts, theme and master
come from the template.

## Step 1b: `slides.md` → the text

Mechanical translation, one slide at a time. For each `## Slide K` in `slides.md`:

1. Look up its layout's line in the slot map. `layout: Two Content` →
   `title=shape-0, col1.body=shape-1, col2.body=shape-2`.
2. For every role the slide fills with text, emit `"shape-N": {"paragraphs": [...]}` under
   the deck slide key `slide-<K-1>`.
3. A `-` list becomes one paragraph per item with `"bullet": true, "level": 0`. Plain lines
   become paragraphs with no `bullet` key. A column heading (`colN.head`) on a layout without
   a heading slot becomes the first paragraph of `colN.body`, with `"bold": true`.
4. Leave out fonts, sizes and colours. The template supplies them, and `add-text` shrinks the
   font where text would overflow (floor 12 pt; below that it fails and the content has to get
   shorter).

Slide 2 of the worked example in
[02-slide-content.md](02-slide-content.md#worked-example-a-full-slidesmd), which is
`Title and Content` at deck position 1:

```json
{
  "slide-1": {
    "shape-0": {"paragraphs": [{"text": "Three reasons to decide this year"}]},
    "shape-1": {"paragraphs": [
      {"text": "Demand: evening study seats are full four nights a week", "bullet": true, "level": 0},
      {"text": "Budget: next year's staffing plan closes in September", "bullet": true, "level": 0},
      {"text": "Lease: two branches renew their building lease in 2027", "bullet": true, "level": 0}
    ]}
  }
}
```

Rules:

- **Each entry in `paragraphs` is one paragraph and one run.** A line has no mixed
  formatting: `{"text": "Lead-in", "bold": true}` followed by `{"text": " and the rest"}`
  renders as **two lines**. Where that matters, write the bold part as a short standalone
  lead-in line and the rest as its own paragraph.
- **Do not use `"alignment"` together with `"bullet"`.**
- **Do not use empty strings as spacers.** They take vertical room and push real text into an
  overflow shrink.
- **Skip DATE, FOOTER and SLIDE_NUMBER placeholders.** The template handles them.
- A text slot left out of the JSON stays **empty**: `add-text` cleared it. An empty slot
  shows no text in the rendered deck and is listed by `validate`.

## Figures

Three kinds, each filling an `OBJECT` slot. Nothing else fills one, and nothing in the
template path generates an image; see the rules in `SKILL.md`.

`add-chart` and `add-images` address a slide's `OBJECT` placeholders by `index` in document
order, and that index counts every `OBJECT` placeholder of the slide, filled with text or
not. On `neutral`, `Title and Content` has one (`index` 0) and `Two Content` has two
(`col1.body` is `index` 0, `col2.body` is `index` 1). Put no text in a slot that gets a
figure. For another brand's template, render and check which slot a figure landed in.

### Native chart

```json
{"chart_type": 51,
 "data": {"categories": ["2024", "2025", "2026"],
          "series": [{"name": "Minutes per case", "values": [22, 31, 44]}],
          "x_axis_title": "Year", "y_axis_title": "Minutes"}}
```

`chart_type` is `51` for clustered column or `5` for pie. Those are the only two. Pie
percentages must be pre-computed: the labels show the values supplied.

**A single-series chart renders the series name as its chart title**, with or without
`title`. Name the series as a heading (`Minutes per case`, not `series1`), and do not repeat
it in the slide title. A `title` key overrides it.

A Chart.js-shaped `{type, data: {labels, datasets}}` payload is rejected.

### Native table

Keyed by deck slide. `placeholder_index` is the placeholder **idx** from the slot map (the
number after the colon in `OBJECT:1`), not the `shape-N`. The header colours come from the
brand (see [03-layout-mapping.md](03-layout-mapping.md#theme)).

```json
{"slide-3": {
  "rows": [
    {"header": true, "style": {"background_color": "#1B1B4B", "color": "#FFFFFF"},
     "cells": ["Metric", "Trial"]},
    {"cells": ["Evening visits per week, trial branches", "2x"]},
    {"cells": ["Evening visits per week, control branches", "1.1x"]},
    {"cells": ["Evening visitors who answered the exit survey", "85%"]}
  ],
  "placeholder_index": 1,
  "column_widths": [8.0, 4.0]
}}
```

The table takes the placeholder's position and size and replaces it, because `add-text`
left it empty. Put no text in a slot that gets a table.

### Image

Only a file the user supplied.

```json
{"action": "add-images", "slide": 2, "images": ["<name>/figures/hero.png"],
 "type": "OBJECT", "index": 1}
```

A PICTURE placeholder of a brand template takes `"type": "PICTURE"`, also only with a
supplied image.

## Step 1c: one `edit` spec

`edit` stages every operation in a temporary directory and writes the output only after all
of them succeed, so a failure at operation 4 of 6 leaves no half-written deck.

```json
{"operations": [
  {"action": "add-slide", "layouts": ["Title Slide", "Title and Content", "Two Content",
                                      "Title and Content", "Section Header"]},

  {"action": "add-text", "data": {
     "slide-0": {"shape-0": {"paragraphs": [
                   {"text": "Evening visits doubled where branches stayed open late"}]},
                 "shape-1": {"paragraphs": [{"text": "City council, 4 Jun 2026"}]}},
     "slide-1": {"shape-0": {"paragraphs": [{"text": "Three reasons to decide this year"}]},
                 "shape-1": {"paragraphs": [
                    {"text": "Demand: evening study seats are full four nights a week", "bullet": true, "level": 0},
                    {"text": "Budget: next year's staffing plan closes in September", "bullet": true, "level": 0},
                    {"text": "Lease: two branches renew their building lease in 2027", "bullet": true, "level": 0}]}},
     "slide-2": {"shape-0": {"paragraphs": [
                   {"text": "Evening visits rose at every trial branch"}]},
                 "shape-1": {"paragraphs": [
                    {"text": "Three branches open until 21:00", "bullet": true, "level": 0},
                    {"text": "Two branches as controls", "bullet": true, "level": 0}]}},
     "slide-3": {"shape-0": {"paragraphs": [{"text": "Where the trial landed"}]}},
     "slide-4": {"shape-0": {"paragraphs": [{"text": "Decision needed this quarter"}]},
                 "shape-1": {"paragraphs": [{"text": "Extend late opening to all five branches"}]}}}},

  {"action": "add-chart", "slide": 2, "index": 1, "data": {
     "chart_type": 51,
     "data": {"categories": ["Sep", "Nov", "Jan", "Mar"],
              "series": [{"name": "Evening visits per week", "values": [410, 620, 700, 830]}],
              "x_axis_title": "Month", "y_axis_title": "Visits"}}},

  {"action": "add-table", "data": {"slide-3": {"rows": [], "placeholder_index": 1}}},

  {"action": "add-notes", "data": {
     "slide-0": "Open on the result, not the schedule.",
     "slide-1": "Lease dates are public. Seat counts: trial report, table 4.",
     "slide-2": "Source: daily door counts 2025-09 to 2026-03. The December dip is the holiday closure.",
     "slide-3": "85% is the exit survey response rate, not a satisfaction score.",
     "slide-4": "Cost detail and staffing plan are in the appendix."}}
]}
```

The `add-table` `rows` here stand for the table of the previous section. Ask `docs:pptx` to
apply `<name>/edit-spec.json` to `<presentation.pptx>` as one atomic `edit`, writing
`<name>.pptx`. The template file is only read.

The `add-slide`, `add-text`, `add-table`, `add-images`, `add-chart` and `add-notes` JSON
formats are the ones `docs:pptx` documents for those operations.

### If `edit` is unavailable

Same operations, same order, as separate `docs:pptx` calls, each writing a new file so a
failure is recoverable:

1. `add-slide`: `<presentation.pptx>` → `<name>/s1.pptx`, the layout names of
   `template_mapping`
2. `add-text`: `<name>/s1.pptx` + `<name>/text.json` → `<name>/s2.pptx`
3. `add-chart`: `<name>/s2.pptx` → `<name>/s3.pptx`, slide 2, OBJECT index 1, spec
   `<name>/figures/chart.json`
4. `add-table`: `<name>/s3.pptx` + `<name>/tables.json` → `<name>/s4.pptx`
5. `add-notes`: `<name>/s4.pptx` + `<name>/notes.json` → `<name>.pptx`

## Step 2: verify

Ask `docs:pptx` for four checks on `<name>.pptx`:

1. `export-slides` at 150 dpi into `<name>/renders/`
2. `extract-shapes --issues-only` into `<name>/issues.json`
3. `extract-text` of the whole deck
4. `validate`

- **Export from the deliverable file at its real path**, not a working copy. A stale
  intermediate can differ from what got saved.
- **Read the rendered images back.** A zero exit code does not show that the deck is right.
- `--issues-only` takes an output path. On a clean deck it writes nothing and prints
  `No issues discovered`. It flags text overflowing its frame, shapes off the slide, overlaps
  and hand-typed bullet characters.
- `validate` exits 2 when it finds a problem. Act on every entry: an empty text placeholder
  is a slot the spec left out, an unfilled visual placeholder is an `OBJECT` slot with no
  text and no figure. An entry for a slot the content does not use means the layout is
  wrong for the slide: pick another layout, or fill the slot.
- `extract-text` is the cheap check that every slot got what `slides.md` said.
- **Second opinion** (on by default; skip when the user asks to): load `ai:second-opinion`
  with the Skill tool and ask it to review the PNGs in `<name>/renders/` with `slides.md` and
  these criteria as the brief: every slot holds the text `slides.md` gives it, no text
  overflows or is cut off, no shapes overlap or leave the slide, no empty placeholder shows.
  Verify each finding against the render before acting on it; drop the ones that do not hold
  and tell the user which were dropped. When second-opinion reports no review model, skip the
  review and tell the user.

Expect one round of fixes on a first build, usually text that had to shrink. Fix it in
`slides.md`, regenerate the spec, and run step 1 again; do not hand-edit the `.pptx`.

## Next: [05-consistency-pass.md](05-consistency-pass.md)
