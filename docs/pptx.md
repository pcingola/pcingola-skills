# pptx

`docs:pptx` is the CLI `pptx.sh`, package `pptx_tool`, on python-pptx and Pillow. It has no settings and no data
directory. `pptx.py` holds the argparse parser and maps each subcommand to `run_<command>` in a `cmd_<command>.py`
module; `extract-text` lives in `cmd_check_text.py`, and `list-images` and `extract-images` in `cmd_extract_media.py`.

## Modules

| Module | Role |
| --- | --- |
| `cmd_extract_shapes.py` | The shape inventory every other command keys on: `ShapeData`, `extract_text`, overflow and overlap detection |
| `measure.py` | Font lookup and text measurement: wrapped line count and single-line width |
| `text_fitting.py` | `TextFitter` (font-size reduction for `add-text`) and the inherited font size of a shape |
| `text_formatters.py` | `ParagraphProcessor` and `ShapeFormatter`: run, paragraph, fill, border and text-frame properties |
| `text_validators.py` | Checks `add-text` data against the inventory; collects formatting warnings after a write |
| `placeholders.py` | Finds OBJECT placeholders (type 7) and removes a shape from the shape tree |
| `cmd_select_slides.py` | Slide removal, duplication and cross-deck cloning, also used by `copy-slide`, `delete-slide`, `add-slide` |
| `common.py` | EMU and point constants, the bundled font path, `CHART_COLORS` |
| `__init__.py` | `find_libreoffice` |
| `exceptions.py` | `TextAdditionError` and its subclasses |

## Shape inventory

`extract_text` walks each slide, flattens groups to absolute positions, and keeps tables with rows and shapes with a
text frame. An empty text shape is kept only when it is a TITLE, CENTER_TITLE, SUBTITLE, BODY or OBJECT placeholder,
so a slide added from a layout has keys for `add-text` to fill. SLIDE_NUMBER placeholders and footers holding only
digits are dropped. Shapes are sorted into rows of 0.5 in by their top edge, then by top and left, and numbered in that
order: `slide-N/shape-M` is a reading-order id, not the z-order (which is stored separately as `z_order`). Any
command that edits the deck can renumber the shapes.

The inventory flags frame overflow above 0.05 in, slide overflow above 0.01 in, and overlaps whose width and height
both exceed 0.05 in. `extract-shapes`, `validate`, `get`, `add-text` and `visual-preview --outline-text` read this
inventory; `inspect-template` uses its shape collection and ordering, so its ids match.

## Text measurement and fitting

`measure.py` is the one font loader. It searches the system font directories and LibreOffice's bundled fonts, maps
Calibri to Carlito and Cambria to Caladea (the metric clones LibreOffice substitutes), prefers an exact file name and
penalises style tokens not asked for, so "Calibri" does not measure Carlito-Bold. Without a match it uses
`assets/fonts/Inter_24pt-Light.ttf`, and only then PIL's default font; PIL's bitmap default has metrics unrelated to the
deck. The line count wraps at 90% of the column width and adds the lines forced by a word wider than the column.

`add-text` computes every shape's fit before writing anything. A paragraph's base size is its `font_size`, else the
size the shape inherits: the shape's `lstStyle`, then the layout and master placeholders, then the master `titleStyle`,
`bodyStyle` or `otherStyle`, or `defaultTextStyle` for a non-placeholder. All paragraphs of a shape drop by the same
amount in 2 pt steps down to 12 pt, against 95% of the height inside fixed margins (0.1 in sides, 0.05 in top and
bottom) at 1.4 times the font size per line. A shape that still overflows at 12 pt fails the whole command and nothing
is saved. A paragraph without `font_size` gets an explicit size only when its shape was reduced, so it otherwise keeps
inheriting from the template.

The frame-overflow check of the inventory measures the written deck differently: the first run's explicit size or 18
pt, and the paragraph's line spacing or 1.0 times the font size. Both paths share `measure_text_lines`.

`add-text` clears every inventoried text shape on every slide, including shapes the data does not name; a shape keeps
text only if the data gives it `paragraphs`. Tables in the inventory are skipped.

## Slide copying

python-pptx has no slide copy and no insert at an index. `cmd_select_slides.py` works at the OPC part level:

- A new slide gets the first `/ppt/slides/slideN.xml` name no part uses, since python-pptx reuses names of deleted
  slides and the saved zip then holds duplicate entries.
- `copy-slide` between decks relates the copy to a target layout of the same name (else the first target slide's
  layout, else the first layout), so the source layout, master and theme are not pulled in. The slide's own parts
  (images, media, embedded objects) are deep-copied under fresh names, and `r:id`, `r:embed` and `r:link` attributes
  are remapped to the new relationship ids. Notes are dropped, because a notes slide refers back to its slide and
  cloning it copies the whole layout tree.
- Insertion at a position appends the slide, then moves its entry in `sldIdLst`.
- `select-slides` copies the template, deletes the slides not in the sequence, duplicates repeated indices in place,
  then reorders `sldIdLst`.

## Placeholders

`add-images` and `add-chart` remove the placeholder and add a picture or chart at its geometry. `add-images` stretches
the image to the placeholder box. Their `--index` is the ordinal among placeholders of that type on the slide, while
`add-table`'s `placeholder_index` is the placeholder `idx`. `add-table` removes the placeholder it fills when it holds
no text; left in place it would overlap the table and count as unfilled in `validate`. `add-chart` makes a clustered
column (type 51) or pie (type 5) chart at 95% of the placeholder width and 90% of its height, coloured from
`CHART_COLORS` (the neutral brand accents, then tints). `add-shapes` turns off the inherited shadow by setting the
shape's theme `effectRef` to index 0, since LibreOffice renders that shadow despite an empty effect list.

## edit

`edit` copies the input into a temporary directory, runs each operation's command runner on the previous step's file,
and replaces the output path only after the last step succeeds. A runner's `sys.exit(1)` becomes a failed step. The
action names are the command names, so there is no second vocabulary to keep in step with the CLI.

## Rendering

`export-slides` and `visual-preview` convert to PDF with LibreOffice headless and rasterise with `pdftoppm`.
`find_libreoffice` looks on `PATH` for `libreoffice` or `soffice`, then in the macOS and Windows default install
locations. Without either tool the commands fail with an install hint. `visual-preview` puts at most `cols * (cols +
1)` slides on one grid and draws a placeholder for hidden slides (`show="0"`). `validate` exits 2 when it reports any
issue.

## Tests

Unit tests are in `tests/unit/pptx/`; `test_libreoffice_gate.py` runs the rendering commands with an empty `PATH` and
checks the install hint. Integration tests in `tests/integration/pptx/` run `pptx.sh` on decks built by the helpers in
its `__init__.py`; the rendering tests need LibreOffice. Their files go to `tests/data/tmp_pptx/` and are deleted unless
`KEEP_TMP` is set, in which case a summary slide describing the expected result is inserted first in each kept deck.
`tests/unit/pptx/test_add_text_sizes.py` reads the neutral brand's template from `brand:brand`.
