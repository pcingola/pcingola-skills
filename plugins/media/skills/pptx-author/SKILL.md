---
name: pptx-author
description: "Authors editable pptx decks from brand template layouts, or from media:image-gen slide designs rebuilt natively or placed as images. TRIGGER when: user wants a new PowerPoint (.pptx) deck or presentation, or to backport an image-gen slide to pptx."
allowed-tools: Bash Read Write Edit Glob Grep Skill
---

# pptx-author

## What this is

A methodology for producing an **editable** slide deck: real PowerPoint text boxes,
placeholders, charts and tables, not a flattened picture. It has two build paths that share
the same five phases and differ at phases 3 and 4:

- **Template path**: write the words, pick one layout of the brand's PowerPoint template per
  slide, add a slide of that layout and fill its placeholders. The template carries the
  design; no image is generated.
- **Bespoke design path**: design each slide whole with `media:image-gen`, get it approved,
  then measure the approved image and rebuild it as native shapes. When the user chooses
  images-only, the approved images are instead placed full-slide in a deck that is not
  editable.

The skill has no scripts. Other skills do the work, each loaded once with the Skill tool:

- `docs:pptx`: all `.pptx` file work. Here and in `references/`, a step names the operation
  (`add-slide`, `edit`, `export-slides`) and its inputs and outputs; the command line and the
  JSON formats come from `docs:pptx`'s `SKILL.md`.
- `media:image-gen`: image generation and editing, bespoke design path only.
- `brand:brand`: the brand folder and its `brand.yaml`. Template path: the template (see
  "The template"). Bespoke design path: colours, fonts and type sizes.
- `brand:style`: the style line that starts every image prompt, bespoke design path only.
- `ai:second-opinion`: review of the renders against their source PNGs or `slides.md` in the
  phase 4 build checks.

If `docs:pptx` or `brand:brand` is not available, stop and say so: nothing can be built
without them.

## Which path

- User wants a deck **on a brand's template**, or a plain editable deck whose layouts are
  title, section, one block, two blocks → template path.
- User wants a **one-off, high-stakes deck** (executive briefing, leadership review) where the
  visual bar is "looks designed", or a deck matched exactly to an approved image → bespoke
  design path.
- User wants to **backport an image-gen slide into an editable pptx** → bespoke design path,
  starting at phase 4.
- Unclear → ask which, once. Recommend the template path when the template's layouts can hold
  the content.
- User wants to **edit an existing deck's content** without touching layout → use `docs:pptx`
  directly; this skill does not apply.
- User chooses an **images-only deck** (one full-slide image per slide, not editable) →
  bespoke design path, with the [images-only assembly](references/04-image-assembly.md) as
  phase 4. The user's explicit choice is the confirmation: a request that states it needs no further
  question. Never assume it; without that choice the
  bespoke design path ends in the native backport. The choice is per deck.

## The template (template path)

The deck's brand is the brand the user names, else the bundled `neutral` brand. Ask
`brand:brand` for that brand's folder and `brand.yaml`. The template is the file under the
key `pptx.presentation.pptx`, a path relative to the brand folder; its sidecar
`pptx.presentation.json` lists the template's example slides, if any. A brand without a
`pptx.presentation` key has no template: use the `neutral` brand's template, and say so.

Here and in `references/`, `<presentation.pptx>` stands for the brand folder joined with
`pptx.presentation.pptx`, and `<presentation.json>` for the brand folder joined with
`pptx.presentation.json`. Use `<presentation.pptx>` in place as the input of the first `docs:pptx`
operation; never copy or write into the brand folder.

The deck is built from the template's **layouts**, not from example slides: `add-slide`
adds one new slide per layout name, with that layout's empty placeholders. The `neutral`
template has five layouts and no slides; its slot map is in
[03-layout-mapping.md](references/03-layout-mapping.md). Another brand's template gets its
slot map from a probe deck in phase 3.

## The five phases

Each phase gates the next. Do not skip ahead: a built deck or a generated image is costly to
change, a line of markdown is not, so everything is settled while it is still markdown.

1. **[Deck outline](references/01-deck-outline.md)**: scope the deck before writing
   anything: audience, verbatim ask, slide count, narrative arc, build path, the deck folder,
   the checklist.
2. **[Slide content](references/02-slide-content.md)**: draft the words per slide and get
   them stable before any visual work starts. On the template path this is `slides.md` in a
   plain markdown dialect, the artifact the user reviews.

Then one of:

| Phase | Template path | Bespoke design path |
| --- | --- | --- |
| 3 | **[Layout mapping](references/03-layout-mapping.md)**: one template layout per slide, written to `outline.md`, ending in the `template_mapping` line. A request for a layout mapping alone (slide content in, `outline.md` out) runs this phase on its own. | **[Image design](references/03-image-design.md)**: generate each slide whole as one image via `media:image-gen`, starting from a style and a layout in the [design library](references/design-library/README.md); get explicit per-slide approval. A design reference, not the deliverable. |
| 4 | **[Native build](references/04-native-build.md)**: add one slide per mapped layout, fill the placeholders, add speaker notes, all in one `edit` spec; render and check. | **[Native backport](references/04-native-backport.md)**: measure the approved image and rebuild it as editable pptx objects. Icons and logos are regenerated at high resolution, not cropped. Or, when the user chose images-only, **[images-only assembly](references/04-image-assembly.md)**: each approved image full-slide on a blank slide, with its speaker notes. |

5. **[Consistency pass](references/05-consistency-pass.md)**: read the deck as a deck. Both
   paths: parallel phrasing, figures referenced, numbers agreeing. Bespoke design path also:
   header sizes, title positions and background colours that drifted between independently
   generated slides.

## Approval gates

- **Template path: two gates.** (1) Content and mapping: show `slides.md` and `outline.md`
  together, before any `.pptx` exists. (2) The rendered deck: render at 150 to 200 DPI from
  the deliverable file and check it before saying it is done. A native rebuild is cheap, so
  per-slide sign-off buys nothing.
- **Bespoke design path: per slide.** Content approved per slide in phase 2, and a hard gate
  between phases 3 and 4: no slide is backported until the user has approved that specific
  generated image, by name, in chat. One slide at a time.

## Design library (bespoke design path)

`references/design-library/` holds reusable, brand-neutral designs, so a deck starts from a
tested look instead of a layout invented from scratch. Read its
[README](references/design-library/README.md) at phase 1. It has:

- `infographic.md`: the base frame (prompt skeleton, layouts A to E, token vocabulary).
- Three styles (`style-minimal/editorial/colorblock.md`), each naming its catalogue style in
  `brand:style`, and layouts F to I (`layout-dashboard/timeline/flowchart/comparison.md`),
  each with a `.png` guide.

Pick one style and one layout in phase 1. Design tokens (colours, fonts, type sizes) come
from the deck's brand through `brand:brand`; a deck without a brand uses the bundled
`neutral` brand. In phase 3 each slide's `media:image-gen` prompt starts with the style line
from `brand:style`, then the palette: that brand's `accent1`, `accent2`, `accent3`, `dk1` and
`lt1`.

## Resume an interrupted build from a checklist

A build spans phases and often sessions. **The first action of phase 1 is to create a
checklist file** at `<name>/checklist.md`: one box per step, per slide for the per-slide
phases (templates for both paths in
[01-deck-outline.md](references/01-deck-outline.md#progress-checklist)). **Tick each box when
its step finishes, before starting the next.** A checklist filled in at the end cannot be
resumed from.

On every start or resume, read `checklist.md` first and continue at the first unchecked box:

- **Bespoke design path:** content not drafted → draft it; content done but no image →
  generate the image; image approved but not backported → backport; every slide backported →
  run the consistency pass. Images-only: every image approved but no deck → assemble it; deck
  assembled → check it, then the consistency pass.
- **Template path:** content not drafted → draft `slides.md`; content drafted but no layout →
  map it in `outline.md`; gate 1 not passed → show `slides.md` and `outline.md`; gate 1
  passed but no deck → build it; deck built but not rendered from the deliverable → render
  and check; rendered → consistency pass, then gate 2.

Do not re-approve approved content or slides, and do not rebuild or re-measure a finished
slide.

## Optional: strategic critic pass

This process renders the content it is given faithfully and consistently. It does not check
that the deck's argument holds up against its source material. For a high-stakes deck, if a
skill or reviewer exists for that content check, run it against the finished deck before
sending.

## Rules

Both paths:

- **Never flatten a slide into a full-bleed picture unless the user has explicitly chosen
  images-only** ([04-image-assembly.md](references/04-image-assembly.md)). A flattened image
  is a failure when the ask was an editable deck.
- **Never fabricate data.** Every number, name and claim on a slide traces to something the
  user provided. If a figure needs a number nobody stated, ask; do not estimate.
- **Keep `<name>/checklist.md` current.** Create it as the first step of phase 1, tick each
  box when its step is done, and on a resume start from the first unchecked box.
- **Know the deliverable's exact file path before building**, and record it in the working
  doc (phase 1). Iterate in scratch space, but the final save lands at that path.
- **Keep every process file in one folder named after the deck.** For a deliverable at
  `path/to/<name>.pptx`, all working files go in `path/to/<name>/`; the `.pptx` sits next to
  that folder. See
  [references/01-deck-outline.md](references/01-deck-outline.md#file-layout-one-folder-per-deck).
- **Verify against the deliverable file**, not an intermediate build. Render and check the
  file at the target path before calling it done.
- **Verify renders at 150 to 200 DPI** (`export-slides` default 150). Pixelation and small
  misalignments do not show at low DPI.

Template path:

- **Use only the template's layouts.** If a request needs a layout the template does not
  have (a timeline, an org chart, a full-bleed image), say so. The nearest answer is usually
  a one-block layout with a native table or chart in the content slot.
- **Never synthesize an image.** No PIL, no matplotlib, no drawn placeholder box, no
  `media:image-gen`. A visual slot gets a native chart, a native table, or an image the user
  supplied. If none is available, leave the slot out and say it is empty.
- **Address shapes by the `shape-N` of the slot map**, never by a number read off a partly
  filled deck. Inserting a figure replaces a placeholder with a shape and renumbers
  everything after it; see [04-native-build.md](references/04-native-build.md).
- **The template owns the design.** Do not set fonts, colours or positions on text. The one
  time a hex is needed is a native table's header row; take it from the brand's `colors` in
  `brand.yaml`
  (see [03-layout-mapping.md](references/03-layout-mapping.md#theme)).

Bespoke design path:

- **Start from the design library.** Pick a style and a layout from
  `references/design-library/` and apply the brand's palette (the `neutral` brand's when the
  deck has none).
- **Hard approval gate between phases 3 and 4**, one slide at a time (above).
- **Never crop icons and logos from the low-resolution slide export.** The whole-slide PNG
  renders at about 100 DPI for the full canvas, so a cropped icon is 60 to 200 px: it looks
  fine in a preview and pixelated in PowerPoint at real scale. Regenerate at high resolution
  instead; see [references/04-native-backport.md](references/04-native-backport.md).
- **Always run the consistency pass**, even when every slide matches its source image.
  Independently generated images drift from each other in ways that show only when flipping
  between slides.
