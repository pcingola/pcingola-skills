# 3. Layout mapping

One template layout per slide, written to `<name>/outline.md`. Content chooses the layout:
one sentence is a title-only slide, one block of bullets or one figure is a one-block
layout, two parallel items are a two-block layout.

## The vocabulary is the template's layouts

The build adds one slide per layout name from `<presentation.pptx>` (`add-slide` of
`docs:pptx`), so every layout of the template is usable. The template's layouts and their
placeholders are what `docs:pptx`'s `inspect-master` lists under `slide_layouts`
(`layout_name` and the placeholder `shapes` of each).

If a request needs something no layout holds (a full-bleed image slide, a timeline, an org
chart), say so. The nearest answer is usually a one-block layout with a native table or chart
in the content slot.

## The `neutral` template

The bundled `neutral` brand's template is 16:9 (13.33 × 7.5 in) with five layouts and no
example slides:

| Layout | Use it when |
| --- | --- |
| Title Slide | the opening slide: deck title and one subtitle line |
| Section Header | a new section begins: section title and one line of context |
| Title and Content | the default: a title plus one block, chart, table or image |
| Two Content | two parallel items side by side, or text beside a figure |
| Blank | a slide for a user-supplied full-slide image only |

A one-sentence statement slide is `Title Slide` with an empty subtitle left out of the spec,
or `Section Header`.

## The slot map

The one place a role name becomes a real placeholder. Everything else (the dialect in
`slides.md`, `outline.md`, the prose here) uses role names only.

Each entry is `role=shape-N TYPE:idx`. `shape-N` is the key `add-text` and `edit` address on
a slide of that layout, as `docs:pptx`'s `extract-shapes` numbers it on a new, empty slide;
`TYPE:idx` is the placeholder type and its `idx` (the `placeholder_index` of `add-table`).

The `neutral` template:

```slotmap
Title Slide       | title=shape-0 CENTER_TITLE:0, subtitle=shape-1 SUBTITLE:1
Section Header    | text=shape-0 BODY:1, title=shape-1 TITLE:0
Title and Content | title=shape-0 TITLE:0, body=shape-1 OBJECT:1
Two Content       | title=shape-0 TITLE:0, col1.body=shape-1 OBJECT:1, col2.body=shape-2 OBJECT:2
Blank             | none
```

`Section Header` puts its `text` above its `title`, so `shape-0` is the text line. The
shape order follows position (top to bottom, then left to right), not placeholder index.

### Another brand's template: build the slot map from a probe deck

A brand template other than `neutral` has its own layouts. Map them once per deck, in phase
3, before writing `outline.md`:

1. Ask `docs:pptx` for `inspect-master` of `<presentation.pptx>` into
   `<name>/layouts.json`, and read the layout names.
2. Ask `docs:pptx` to `add-slide` one slide of each layout the deck may use, from
   `<presentation.pptx>` into `<name>/probe.pptx`. If `<presentation.json>` lists example
   slides, the probe deck holds them first; the probe slides follow them.
3. Ask `docs:pptx` for `extract-shapes` of `<name>/probe.pptx` and `show-shapes` of the
   result, and `export-slides` of the probe deck to see each layout.
4. Write one slot map line per layout into `outline.md`, in the format above, with a role
   name per `shape-N`. A PICTURE placeholder is not in `extract-shapes` output; note it per
   layout as `picture=PICTURE` from `layouts.json`.

A layout whose placeholders hold prompt text in `extract-shapes` (for example "Click to add
title") needs every one of those placeholders in the spec, or left out on purpose.

## Size budgets (`neutral`)

Slot sizes in inches. Use them to decide how much text a slot can carry. `add-text` shrinks
the font to fit and refuses below 12 pt, so an over-full slot is caught late.

| Layout | Slot | Size (in) | Rough capacity |
| --- | --- | --- | --- |
| Title Slide | title / subtitle | 11.33 × 1.61 / 9.33 × 1.92 | one line, about 50 characters / two short lines |
| Section Header | text / title | 11.33 × 1.64 / 11.33 × 1.49 | one line of context / one line |
| Title and Content | title / body | 12.00 × 1.25 / 12.00 × 4.95 | one line, about 60 characters / about 8 bullets, a chart or a table |
| Two Content | title / col body | 12.00 × 1.25 / 5.89 × 4.95 | one line / about 6 short bullets, or a figure |

`Two Content` has no column heading slot. A column heading is the first paragraph of its
`colN.body`, bold, followed by the bullets.

## Picture placeholders

`neutral` has none. A brand template may have layouts with a PICTURE placeholder (a picture
panel). Use such a layout only with an image the user supplied; left empty, the panel renders
as a grey field. Never fill a picture panel with an image you made: the template path
generates no images.

## Variety across a deck

A deck of eight consecutive one-block slides reads as a document pasted into PowerPoint.

- **Never use the same layout three times in a row.** If the content repeats that shape,
  merge slides instead.
- **Open with the title layout**, and mark section changes with the section layout in decks
  longer than about eight slides.
- **Use a two-block layout for parallel items or for text beside a figure.**
- If two layouts fit equally well, **pick the one used least so far in this deck**.

With five layouts, `neutral` decks repeat layouts. A run of `Title and Content` slides is
broken with `Two Content` when the content splits in two, not by padding.

## User override wins

If the user names a layout for a slide, use it. Never silently substitute a different one;
say what you would have chosen and why, and let the user decide.

## `outline.md`

One section per slide, then the `template_mapping` line, the layout names in deck order.
Phase 4 turns that line into the `add-slide` operation, so keep the format exactly:

```markdown
# Outline: Library opening hours

## Slide 1: Opening
Layout: Title Slide
Argues: evening visits doubled where branches stayed open late

## Slide 2: Why now
Layout: Title and Content
Argues: three independent reasons, all due this year

## Slide 3: What changed
Layout: Two Content
Argues: the trend, with the chart carrying it
Figure: native chart from figures/evening-visits.json in col2.body

## Slide 4: The numbers
Layout: Title and Content
Argues: the three numbers that justify the ask
Figure: native table from figures/trial.json

## Slide 5: The ask
Layout: Section Header
Argues: one line, one decision

# Template mapping (layout names, in deck order)
template_mapping = ["Title Slide", "Title and Content", "Two Content", "Title and Content", "Section Header"]
```

Repeat a name to use a layout twice. For a template other than `neutral`, `outline.md` also
holds the slot map lines of the layouts it uses.

## Theme

The template sets background, fonts, type scale, title size and position. A native chart
takes its series colours from `docs:pptx`, not from the spec. The one time a colour is set by
hand is a native table: `add-table` gives a header row a default fill, and the spec sets the
header `background_color` to the brand's `accent1` and the header text to its `lt1`. The
colours are the `colors` of the deck's brand in `brand.yaml`. For `neutral`, `accent1` is
`#1B1B4B` and `lt1` is `#FFFFFF`; its fonts are Calibri for headings and body.

Do not set fonts, colours or positions on text; leave them to the template.

## Next: [04-native-build.md](04-native-build.md)
