# Building from a Blank Canvas

Build slides **without** a branded template: start from a blank deck and place native shapes (boxes, ovals, textboxes, connectors, pictures) at exact inch coordinates. Use this for diagrams, custom layouts, and anything the template layouts don't cover. Everything produced is a **real, editable PowerPoint object** — shapes and pictures you can select and move in PowerPoint, never a flattened slide image.

For branded, placeholder-based decks copy slides from a template deck with `select-slides` and fill its placeholders instead (see `SKILL.md`). The two modes compose: you can `add-text`/`add-table` onto a blank deck too, and check the result with `export-slides` or `visual-preview`. To place a picture on a blank deck, use the `image` shape type below — `add-images` targets an existing PICTURE placeholder, which a blank deck doesn't have.

## 1. Create a blank deck (`new-deck`)

```bash
pptx.sh new-deck <output.pptx> [--slides N] [--size 16:9|4:3]
```

Produces a plain white deck (default python-pptx template, Calibri) with `N` blank slides — a canvas for `add-shapes`.

- `--slides N` — number of blank slides (default `1`, must be ≥ 1)
- `--size` — `16:9` → 13.333 × 7.5 in (default), or `4:3` → 10.0 × 7.5 in

## 2. Draw shapes (`add-shapes`)

```bash
pptx.sh add-shapes <input.pptx> <shape-data.json> <output.pptx>
```

Draws free native shapes (and file-backed pictures) onto existing slides. Reads a JSON file whose top-level keys are `slide-N` (0-based), each mapping to a **list** of shape specs. All coordinates are in **inches**.

### Shape types

| `type`         | Built with                         | Coordinates                       |
|----------------|------------------------------------|-----------------------------------|
| `rect`         | rectangle autoshape                | `left, top, width, height`        |
| `rounded_rect` | rounded rectangle autoshape        | `left, top, width, height` + `radius` |
| `oval`         | ellipse autoshape                  | `left, top, width, height`        |
| `textbox`      | text box                           | `left, top, width, height`        |
| `line`         | straight connector                 | `x1, y1, x2, y2`                  |
| `image`        | picture from a PNG/JPG file        | `path, left, top, width` + optional `height` |
| `chip_row`     | packed row of rounded_rect pills   | `left, top` + `chips` (positions computed) |
| `icon_label`   | picture + label as one unit        | `path, left, top` + icon/label (label positioned) |

`chip_row` and `icon_label` are **computed-layout** sugar: they expand into the same native
shapes above, but derive positions from the *actual rendered size* of the text (`chip_row`)
or the source image (`icon_label`) so you don't hand-compute chip widths or icon offsets.
See [their sections below](#chip-row-computed-pill-row).

### Styling keys (rects / ovals / textboxes)

- `fill` — hex string (`"#FFFFFF"`) for a solid fill; `"none"` or omitted → no fill. (Never leaves the default theme blue.)
- `line` — border object `{"color": "#RRGGBB", "weight": <pt>, "dash": "solid"|"dash"|...}`; `"none"` or omitted → no border. Dash names map to `MSO_LINE_DASH_STYLE`.
- `radius` — rounded-rect corner radius as a fraction (0–0.5) of the shorter side (default `0.08`).
- `shadow` — `false` (default) draws no shadow; `true` keeps the inherited shadow.
- `text` — see below.

### Text object

```json
"text": {
  "vertical_alignment": "TOP"|"MIDDLE"|"BOTTOM",
  "wrap": true,
  "margins": {"left": 0.12, "right": 0.12, "top": 0.06, "bottom": 0.06},
  "paragraphs": [
    {"text": "Title", "bold": true, "font_size": 14, "color": "#1B1B4B", "alignment": "CENTER"},
    {"text": "subtitle", "font_size": 10.5, "color": "#8A8A90", "alignment": "CENTER"}
  ]
}
```

Each paragraph accepts the same run properties as `add-text` (`text`, `bold`, `italic`, `font_size`, `font_name`, `color`, `alignment`, ...). `font_name` defaults to **Calibri**. Shapes do not auto-resize to their text (autofit is off), so size the shape to fit.

### Lines and arrows

A `line` uses `x1,y1 → x2,y2` and takes an optional `line` object (same `{color, weight, dash}` shape) and an optional arrowhead:

- `"arrow": "end"` — arrowhead at the end point (`x2,y2`)
- `"arrow": "start"` — arrowhead at the start point (`x1,y1`)
- `"arrow": "both"` — both ends

### Image object

Places a real, editable PowerPoint picture from a file (PNG/JPG) at explicit coordinates — not a flattened slide. Works on a blank slide with zero placeholders, and composes with native shapes in draw order (list a background `rect` before the `image`, or the `image` before a small logo drawn on top).

```json
{"type": "image", "path": "assets/logo.png", "left": 11.5, "top": 0.3, "width": 1.4}
```

- `path` — source file path (PNG/JPG), required. Missing files fail validation before anything is written.
- `left`, `top`, `width` — position and width in inches, all required.
- `height` — optional; when omitted the aspect ratio is preserved from the source image. Give it only to stretch/fit deliberately.

### chip row (computed pill row)

Expands into a left-to-right row of rounded-rectangle **pill** shapes. Each chip's width is
the **rendered width of its own text** (measured with the same font engine `add-text` uses)
plus equal horizontal padding — so every chip fits its text tightly with the *same* padding,
never a character-count guess. Chips pack left-to-right by `gap`; with `max_width` set, a chip
that would overflow the row wraps to a new row `row_gap` below. This is sugar over placing N
`rounded_rect`s by hand — same fill/border/text conventions, no new visual primitive.

```json
{"type": "chip_row", "left": 0.66, "top": 2.0,
 "chips": [
   {"text": "Postgres"},
   {"text": "S3 bucket", "fill": "#6AD0DC", "text_color": "#FFFFFF"},
   {"text": "Kafka"}
 ],
 "fill": "#EEF6F8", "text_color": "#1B1B4B",
 "font_name": "Calibri", "font_size": 11, "bold": false,
 "height": 0.34, "radius": 0.5, "padding": 0.14, "gap": 0.12,
 "max_width": 12.0, "row_gap": 0.12,
 "line": {"color": "#D5E6EA", "weight": 0.75}}
```

- `chips` — required, non-empty list. Each item needs `text`; `fill` and `text_color` are
  optional per-chip overrides of the row defaults.
- Row defaults: `fill`, `text_color`, `font_name` (Calibri), `font_size` (11), `bold` (false).
- `height` (0.34), `radius` (0.5 = full pill, fraction of the shorter side), `padding` (0.14,
  each side of the text), `gap` (0.12, between chips).
- `max_width` (optional) — wrap to a new row when a chip would exceed it; `row_gap` (0.12) is
  the vertical gap between wrapped rows. A lone chip wider than `max_width` still lands (never
  wrapped off the row start).
- `line` (optional, row-level) — border applied to every chip, same `{color, weight, dash}`
  shape as other shapes. `shadow` (optional) applies to all chips.

### icon label (icon + auto-positioned label)

Places an icon image and a text label as one unit. The icon's on-slide width is **derived
from the source file's own pixel aspect ratio** scaled to the target height (`width =
icon_height × src_px_w / src_px_h`) — so the icon never distorts, even if its source crop is
later tightened. The label's left edge is the icon's *computed right edge* plus `gap`, never a
fixed constant, so the label spacing adapts to each icon's real width.

```json
{"type": "icon_label", "path": "assets/database.png", "left": 0.66, "top": 2.4,
 "icon_height": 0.4, "height": 0.5, "gap": 0.15, "valign": "MIDDLE",
 "label": "Primary data store", "font_name": "Calibri", "font_size": 14, "bold": true, "color": "#1B1B4B"}
```

- `path` — icon file (PNG/JPG), required; missing files fail validation. `left`, `top` required.
- `icon_height` — target icon height in inches. Icon **width is derived, not an input.** If
  omitted, falls back to `height`. (Give at least one of `icon_height`/`height`.)
- `height` — row height (defaults to `icon_height`); the icon and label are vertically aligned
  within it per `valign` (`TOP`/`MIDDLE`/`BOTTOM`, default `MIDDLE`).
- `gap` (0.12) — space between the icon's right edge and the label's left edge.
- Label — either convenience keys (`label` string plus `font_name`/`font_size`/`bold`/`color`/
  `wrap`) or a full `text` object (same `paragraphs` schema as other shapes) for multi-line or
  mixed runs. `label_width` sets the label box width; omitted, it's the natural single-line
  width of the text.

### Validation

- Top-level keys must be `slide-N` within the deck's slide range.
- Duplicate JSON keys are rejected.
- Unknown `type` or missing required coordinates fail with a clear error listing the valid types / missing keys.
- On success, prints the number of shapes added per slide and the output path.

## 3. Set speaker notes (`add-notes`)

```bash
pptx.sh add-notes <input.pptx> <notes-data.json> <output.pptx>
```

Sets the speaker-notes text for one or more slides. Reads a JSON file whose top-level keys are `slide-N` (0-based), each mapping to a **plain-text string**. Use `"\n"` inside the string to split the notes into separate paragraphs.

Works on any deck — a blank canvas from `new-deck` or a branded template deck. It only touches each slide's notes page; visible slide content (shapes, placeholders, text, images) is left exactly as-is.

```json
{
  "slide-0": "Say this out loud but keep it off the slide.\nSecond talking point for slide 0.",
  "slide-2": "One-liner note for slide 2 only."
}
```

Slides not listed in the JSON keep whatever notes they already had (or none, if they had none).

### Validation

- Top-level keys must be `slide-N` within the deck's slide range.
- Duplicate JSON keys are rejected.
- A non-string value fails with a clear error naming the offending slide and the type it got instead of a string.
- On success, prints which slides had notes set and the output path.

### Reading notes back

```bash
pptx.sh get <file.pptx> slide-0/notes
```

`get` (normally `slide-N/shape-N` for shape text) also accepts `slide-N/notes` to print a slide's speaker notes to stdout — prints nothing if the slide has no notes set.

## Worked example — a three-card diagram

`shapes.json`:

```json
{
  "slide-0": [
    {"type": "textbox", "left": 0.66, "top": 0.44, "width": 11.0, "height": 0.6,
     "text": {"paragraphs": [{"text": "Headline", "bold": true, "font_size": 24, "color": "#1B1B4B"}]}},

    {"type": "rounded_rect", "left": 0.66, "top": 2.0, "width": 3.7, "height": 1.4,
     "fill": "#FFFFFF", "line": {"color": "#E0E0E5", "weight": 1.0, "dash": "solid"}, "radius": 0.08,
     "text": {"vertical_alignment": "MIDDLE", "wrap": true,
       "margins": {"left": 0.12, "right": 0.12, "top": 0.06, "bottom": 0.06},
       "paragraphs": [
         {"text": "CoWork", "bold": true, "font_size": 14, "color": "#1B1B4B", "alignment": "CENTER"},
         {"text": "general knowledge work", "font_size": 10.5, "color": "#8A8A90", "alignment": "CENTER"}
       ]}},

    {"type": "rounded_rect", "left": 0.66, "top": 4.6, "width": 12.0, "height": 1.0,
     "fill": "#FFFFFF", "line": {"color": "#6AD0DC", "weight": 1.5, "dash": "solid"}, "radius": 0.12,
     "text": {"vertical_alignment": "MIDDLE",
       "paragraphs": [{"text": "Shared platform layer", "bold": true, "font_size": 13, "color": "#1B1B4B", "alignment": "CENTER"}]}},

    {"type": "line", "x1": 2.5, "y1": 3.4, "x2": 2.5, "y2": 4.6,
     "line": {"color": "#C8C8CE", "weight": 1.0}, "arrow": "end"}
  ]
}
```

```bash
pptx.sh new-deck deck.pptx --slides 1 --size 16:9
pptx.sh add-shapes deck.pptx shapes.json final.pptx
pptx.sh export-slides final.pptx render/ --dpi 110   # eyeball the result
```
