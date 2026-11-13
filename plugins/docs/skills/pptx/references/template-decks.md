# Filling a template deck

A template deck is any `.pptx` whose slides carry the layouts and placeholders to reuse. `pptx.sh` below is `${CLAUDE_SKILL_DIR}/scripts/pptx.sh`. Slide indices are 0-based everywhere; JSON keys are `slide-N` and `shape-N`. The one exception is the file names of `extract-shapes` directory mode (`slide_N.shapes.json`, N 1-based; see step 2).

## 1. Describe the template and select slides

```bash
pptx.sh inspect-template template.pptx template.json
pptx.sh visual-preview template.pptx template-thumbnails
pptx.sh select-slides template.pptx working.pptx 1,3,7,4
```

A template with layouts and no example slides (`inspect-template` lists no slides) is filled from its layouts instead: `inspect-master` lists the layouts and their placeholders under `slide_layouts`, and `add-slide` adds one new slide per layout name, in order, to the template's own file as input and a new working deck as output.

```bash
pptx.sh inspect-master template.pptx layouts.json
pptx.sh add-slide template.pptx working.pptx "Title Slide,Title and Content,Two Content"
```

`template.json` lists each slide's `layout_name` and shapes (`placeholder_type` TITLE, BODY, OBJECT, PICTURE; position and size in inches; `default_font_size`; image shapes have `content_type: "image"`). `select-slides` copies the listed template slides into a new deck in that order; a repeated index duplicates the slide.

## 2. Extract the working deck's shapes

```bash
pptx.sh extract-shapes working.pptx extracted_shapes_data.json
pptx.sh show-shapes extracted_shapes_data.json
```

`extract-shapes` writes every shape that holds text, every empty TITLE, CENTER_TITLE, SUBTITLE, BODY and OBJECT placeholder (and every table), keyed `slide-N/shape-N`, ordered top to bottom and left to right, with placeholder type, position and size. SLIDE_NUMBER placeholders and digit-only footers are left out. `--slide N` extracts one slide; an output path ending in `/`, or an existing directory, writes one `slide_N.shapes.json` per slide, with N 1-based (`slide-0` goes to `slide_1.shapes.json`); `--issues-only` keeps only shapes with detected problems. `show-shapes` prints one line per shape (type, position, size, text preview) and flags text overflow, off-slide shapes and overlaps.

## 3. Write the replacement text (`add-text`)

```bash
pptx.sh add-text working.pptx replacement-text.json output.pptx
```

`replacement-text.json` maps `slide-N` to `shape-N` entries taken from `extracted_shapes_data.json`. A shape or slide key that is not in the extracted data is an error, and duplicate keys in the JSON are rejected. `add-text` clears the text of every extracted shape; a shape keeps text only when its entry has `paragraphs`.

```json
{
  "slide-0": {
    "shape-0": {"paragraphs": [{"text": "Key statement", "bold": true}]}
  },
  "slide-1": {
    "shape-0": {"paragraphs": [{"text": "Slide title"}]},
    "shape-1": {
      "paragraphs": [
        {"text": "First point", "bullet": true, "level": 0},
        {"text": "Detail under the first point", "bullet": true, "level": 1},
        {"text": "Second point", "bullet": true, "level": 0}
      ]
    }
  }
}
```

Paragraph keys: `text`, `bullet` (true for a bullet; no typed bullet characters), `level` (indent level, 0 first), `alignment` (`LEFT`, `CENTER`, `RIGHT`, `JUSTIFY`; a bullet is left-aligned unless `alignment` is given), `bold`, `italic`, `underline`, `strikethrough`, `font_size` (points), `font_name`, `color` (`#RRGGBB`), `theme_color`, `all_caps`, `small_caps`, `superscript`, `subscript`, `char_spacing`, `line_spacing`, `space_before`, `space_after`.

Shape-level keys next to `paragraphs`: `fill_type`, `fill_color`, `fill_theme_color`, `border_visible`, `border_color`, `border_theme_color`, `border_weight_pt`, `border_dash`, `word_wrap`, `autofit`, `text_margin_top`, `text_margin_left`, `text_margin_bottom`, `text_margin_right` (inches), `vertical_alignment` (`TOP`, `MIDDLE`, `BOTTOM`).

Rules:

- Leave out image shapes and DATE/SLIDE_NUMBER placeholders.
- Empty paragraphs used as spacers take vertical space and push long text into overflow.

Overflow: `add-text` measures each shape before writing. A paragraph without `font_size` starts at the size it inherits from the layout and master, and gets no explicit size unless the shape needs a reduction. When the text does not fit, it lowers the size of every paragraph in that shape by the same amount, in 2 pt steps, and stops at the first step that fits or when the smallest paragraph reaches 12 pt. A shape whose smallest paragraph is 12 pt or less fails at once if it overflows. A given `font_size` is the largest size used. The output lists each shape it shrank. If the text still overflows when the loop stops, the command writes nothing, prints the shape's height, the overflow and the share of text to cut, and exits with an error; shorten the text or use a larger placeholder.

## 4. Add tables (`add-table`)

```bash
pptx.sh add-table output.pptx table-data.json output-with-tables.pptx
```

Top-level keys are `slide-N`. Each value is one table definition, or a list of them for several tables on one slide.

Table definition:

- `rows` (required, non-empty): row objects, each with `cells` (list of cell values), optional `header: true` and optional `style`. The column count is the longest row's cell count.
- `position`: `{"left", "top", "width", "height"}` in inches. Missing keys default to 0.5, 1.5, 9.0, 5.0.
- `placeholder_index`: place the table at the position and size of the placeholder with this `idx` (used when `position` is absent). An empty placeholder is replaced by the table; one that holds text stays under it.
- `column_widths`: widths in inches, one per column.
- `row_heights`: heights in inches, one per row; `null` keeps a row's height.
- `merges`: list of `{"start_row", "start_col", "end_row", "end_col"}`.
- `style`: defaults for every cell: `font_size`, `font_name`, `bold`, `italic`, `color`, `background_color`, `alignment`, `cell_margin_in`.
- `borders`: `{"none": true}` removes all borders; otherwise `outer`, `inner_h`, `inner_v`, each `{"color": "#RRGGBB", "weight_pt": 1.0, "dash": "solid"}`.

Cell value: a string, or an object with `text` and any of `font_size`, `bold`, `italic`, `font_name`, `color`, `background_color`, `alignment` (`LEFT`, `CENTER`, `RIGHT`, `JUSTIFY`), `vertical_anchor` (`TOP`, `MIDDLE`, `BOTTOM`), `cell_margin_in` (inches, a number for all sides or `{"top", "bottom", "left", "right"}`).

A header row defaults to background `#1F4E79`, white text and bold. Precedence: cell, then row `style`, then table `style`, then header defaults.

```json
{
  "slide-1": {
    "rows": [
      {"header": true, "cells": ["Metric", "Q1", "Q2", "Q3"]},
      {"cells": ["Revenue", "$2.5M", "$3.1M", {"text": "$3.6M", "bold": true, "background_color": "#E2EFDA"}]},
      {"cells": ["Growth", "8%", "12%", "15%"]}
    ],
    "column_widths": [2.5, 2.0, 2.0, 2.0],
    "position": {"left": 1.0, "top": 1.8, "width": 8.5, "height": 4.0}
  }
}
```

## 5. Add images (`add-images`)

```bash
pptx.sh add-images output.pptx final.pptx 0 images/hero.png --type PICTURE
pptx.sh add-images final.pptx final.pptx 2 images/a.png,images/b.png --type OBJECT
```

Arguments: input, output, 0-based slide index, one image path or comma-separated paths. `--type` is `PICTURE` (default), `OBJECT` or `MEDIA`. With one image, `--index N` picks the Nth placeholder of that type on the slide (default 0). With several images, they fill the placeholders of that type in order; images beyond the placeholder count are reported and left out. The picture takes the placeholder's position and size, so an image whose aspect ratio matches the placeholder is not distorted. Native charts from given data use `add-chart` (see `SKILL.md`).

In an `edit` spec the operation is `{"action": "add-images", "slide": 2, "images": ["images/a.png", "images/b.png"], "type": "OBJECT", "index": 0}`: `slide` (required, 0-based), `images` (a list or a comma-separated string), `type` (default `PICTURE`) and `index` (default 0) mean the same as the command's arguments.

## 6. Add speaker notes (`add-notes`)

```bash
pptx.sh add-notes final.pptx notes-data.json final.pptx
```

Top-level keys are `slide-N`, each a plain-text string; `"\n"` splits it into note paragraphs. Slides not listed keep their notes. Notes never change slide content. Full rules: [blank-canvas.md](blank-canvas.md#3-set-speaker-notes-add-notes).

```json
{
  "slide-0": "Explanation that does not fit on the slide.\nSecond talking point.",
  "slide-3": "Mention the Q3 caveat."
}
```

`pptx.sh get final.pptx slide-0/notes` reads a slide's notes back.

## 7. Check the deck

```bash
pptx.sh validate final.pptx
```

`validate` reports text overflow and overlaps, every text placeholder with no text (any placeholder type other than PICTURE, OBJECT, CHART, MEDIA and SLIDE_IMAGE), and PICTURE/OBJECT/CHART/MEDIA/SLIDE_IMAGE placeholders that are still empty (exit code 2 when it finds any). Every slide whose layout has a visual placeholder needs its image, chart or table before the deck is finished.

Steps 3 to 6 can run as one atomic `edit` call (see `SKILL.md`).
