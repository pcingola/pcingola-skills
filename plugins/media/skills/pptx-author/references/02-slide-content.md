# 2. Slide content

Draft the words for every slide (headline, subtitle, body copy, chip and bullet text)
directly in the working doc (bespoke design path) or in `<name>/slides.md` (template path),
before generating an image or touching a `.pptx`. Get the content approved and stable first.
Changing wording after a slide has been through image generation and native backport means
redoing both; changing it while it is text in a markdown doc costs nothing. On the template
path, `slides.md` **is the artifact the user reviews**.

## The `slides.md` dialect (template path)

One `##` heading per slide, then plain `key: value` lines. No YAML and no parser: a person
reads it and you translate it.

```markdown
## Slide 3: What changed
layout: Two Content

title: Evening visits rose at every trial branch

col1.body:
- Three branches open until 21:00
- Two branches as controls
col2.figure: chart: figures/evening-visits.json

notes: |
  Full talking track. The caveats, the numbers behind the claims, and anything
  that would read as defensive on the slide.
```

### The keys

| Key | Holds |
| --- | --- |
| `layout:` | the layout name, filled in during phase 3 |
| `title:` | the slide title: the TITLE or CENTER_TITLE placeholder |
| `subtitle:` | the line under the title on a title layout |
| `text:` | the context line on a section layout |
| `body:` | the single content block on a one-block layout |
| `colN.head:` / `colN.body:` | a column's heading and its content |
| `figure:` / `colN.figure:` | one of `chart: <path.json>`, `table: <path.json>`, `image: <path.png>`, in the body or in column N |
| `notes:` | the speaker notes, as a `\|` block |

A brand template other than `neutral` may add roles (a `statement`, a `valueN` and
`captionN`); its slot map in `outline.md` names them. A `body` or `colN.body` value can be a
`-` list or a paragraph. A `-` list becomes bulleted paragraphs; plain lines become
unbulleted ones.

**Use role names, never placeholder indices.** `col2.body` is a role; `OBJECT:2` is a
template detail. The translation between them lives in one place, the slot map in
[03-layout-mapping.md](03-layout-mapping.md), so a template change needs one file fixed.

### `figure:` takes a file, not a description

`figure: chart: figures/throughput.json` points at a chart spec you wrote.
`figure: image: figures/hero.png` points at a file the user gave you.

There is no fourth option. A prose description such as `figure: a diagram of the pipeline`
has nothing to render it: the template path generates no image. If a slide wants a visual
and there is no chart, table or supplied image to fill it, write the slide without one and
say so.

Chart and table spec formats are in [04-native-build.md](04-native-build.md#figures).

## On-slide text vs. talking track

Keep these separate from the start:

- **On-slide text** is short: 3 to 7 word phrases for most elements, one sentence at most
  for a headline. A point that needs a full sentence is a talking point, not slide text.
- **Speaker notes** carry the full argument, the caveats, the reasoning behind a choice of
  words, and anything checkable that would read as defensive if printed on a slide. Draft
  them next to the slide text, in the same doc, marked as notes only. They become the
  `add-notes` payload in phase 4. On the template path they are the `notes:` key, so the
  split is structural: nothing under `notes:` can land on a slide.

This split prevents a common failure: a first image-gen draft with full sentences crammed
onto the slide, because the prompt passed paragraph-length source material without marking
what was talking track only.

## Discipline per slide

- **Source-grounded.** Every claim on a slide traces to something real: a document, a
  number someone committed to, a decision that was made. Do not invent a category, a metric
  or a team split because it looks tidy. If a real breakdown exists (an org roster, a real
  list), use it.
- **Say only what the source supports.** "Evening visits doubled" is a count; it does not
  license "our most popular service" without a ranking. This is the most common way a deck drifts
  past its evidence, and the kind of claim that gets challenged in the room.
- **Do not add sections for a topic the ask mentions in passing.** Say the main point once
  and cut the rest.
- **Say what is live and what is planned** if the deck mixes both. A footnote "includes
  planned features" costs little; an overstatement found by the audience costs more.
- **Count before you commit.** Two parallel items means a two-block layout. Do not write a
  third item and hope to drop it later, and do not pad items to fill a layout.

## Worked example: a full `slides.md`

On the `neutral` template:

```markdown
# Library opening hours: city council, 4 Jun 2026

## Slide 1: Opening
layout: Title Slide

title: Evening visits doubled where branches stayed open late
subtitle: City council, 4 Jun 2026

notes: |
  Open on the result, not the schedule. The council already knows the trial
  ran; what it has not seen is the change in evening visits.
  Source: branch visitor counts, trial report, table 2. Do not upgrade this to
  "our most popular service": we have the visit counts, not a ranking.

## Slide 2: Why now
layout: Title and Content

title: Three reasons to decide this year

body:
- Demand: evening study seats are full four nights a week
- Budget: next year's staffing plan closes in September
- Lease: two branches renew their building lease in 2027

notes: |
  The lease dates are public. The seat counts come from the trial report,
  table 4. The staffing deadline is from the budget calendar.

## Slide 3: What changed
layout: Two Content

title: Evening visits rose at every trial branch

col1.body:
- Three branches open until 21:00
- Two branches as controls
col2.figure: chart: figures/evening-visits.json

notes: |
  Source: daily door counts, 2025-09 to 2026-03. The dip in December is the
  holiday closure, not a drop in demand; expect that question.

## Slide 4: The numbers
layout: Title and Content

title: Where the trial landed

figure: table: figures/trial.json

notes: |
  The 85% is the share of evening visitors who answered the exit survey, not
  the share who were satisfied. Say that plainly if asked; do not let it be
  heard as a satisfaction score.

## Slide 5: The ask
layout: Section Header

text: Decision needed this quarter
title: Extend late opening to all five branches

notes: |
  The ask is one line. Cost detail and the staffing plan are in the appendix
  sent separately.
```

## Approval checkpoint

**Template path:** `slides.md` and `outline.md` are approved together at the end of
phase 3, in one gate. Draft the content, map the layouts, then show both.

**Bespoke design path:** once a slide's content section is written, get it confirmed before
phase 3. A short "does this say what you want it to say" is enough. Without it, the image-gen
draft in phase 3 bakes in wording that then has to be regenerated. Tick that slide's content
boxes in `checklist.md` when it is approved, before starting the next slide.

## Next

- Template path: [03-layout-mapping.md](03-layout-mapping.md)
- Bespoke design path: [03-image-design.md](03-image-design.md)
