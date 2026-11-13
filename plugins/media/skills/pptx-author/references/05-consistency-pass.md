# 5. Consistency pass

**On the template path** the template guarantees what the visual checks below are for:
background, header, logo, fonts, title size and title position are identical on every slide
by construction. Skip the visual checks and the shapes-JSON method; run
[Content checks](#content-checks-both-paths) and its method. The rule (reconcile, do not
rationalize) applies to both paths.

**On the bespoke design path** run everything below.

Every slide can pass its own verify loop in phase 4 (match its own source image) and the
deck can still look assembled instead of designed. Each slide's source image was generated
*independently* by `media:image-gen` against a described spec, not against the other slides.
Small drifts that are invisible on one slide show when someone flips from slide 1 to slide 2.

**Run this pass after every slide verifies on its own. It is mandatory.** It catches problems
that per-slide checks miss. Typical examples:

- The header logo was about 2x larger on one slide than on the other two, and one slide was
  missing a header element the others had.
- The main slide title was 22 pt on one slide, 32 pt on another, 36 pt on the third, in three
  close but different colours.
- One slide's page background had drifted to a cream tint while the other two were white.
- The main title sat at a different vertical position on one slide, which produced a visible
  jump when switching slides.
- Two parallel labels on the *same* slide (a box heading and its sibling) had different font
  sizes.

None of these showed when checking each slide against its own source PNG: the source PNGs
already held the drift, because they were generated independently.

## The rule: reconcile, do not rationalize

Every element that plays the same role on more than one slide (page background, header
lockup, slide title, subtitle, card and chip styling, accent colours, captions, footers) ends
up with **one** value for size, weight, colour and position across all slides. When the scan
shows two values for the same role, pick one and change the others to match.

A difference stands **only** if an explicit written instruction requires it: a line in the
deck's working doc or plan that names the element and its different treatment (for example,
a plan that says one card's accent is a neutral grey to keep it quiet while the others carry
the brand colours). Cite that line when you keep a difference. Without such a line,
reconcile.

Do not invent a justification. "A deliberate design choice", "intentional for emphasis" and
"that slide is structurally different" count only when the working doc says so. **The source
images are the trap, not the authority.** Each was generated independently, so a drift seen
there (a cream background on one slide, a larger title on another, a teal accent where the
others are blue) is an artifact of separate generation, not a decision. Matching each source
in phase 4 is what baked the drift into the deck; this pass takes it back out. Reconcile every
difference without a written basis and note what you changed.

## What to check (bespoke design path)

Go slide by slide and diff these:

- **Header and logo lockup**: same logo size, same position (top and left), same text size,
  weight and colour for any wordmark next to it, on every slide.
- **Main slide title**: same font, size, weight, colour and X/Y position on every slide. A
  title that moves between slides is the most visible sign of a deck not built as a system.
- **Page background**: every slide uses the same background colour value. One cream slide
  among white ones is drift; reconcile it.
- **Accent and brand colours**: the same hexes across slides, not near-duplicate shades (for
  example `#3E6DB5` on one slide where the others use `#3A6AB0`). List every accent fill and
  collapse the near-duplicates to the palette value.
- **Repeated structural elements within and across slides**: sibling labels, card titles in
  a grid, chip and pill styling share one size, weight and colour.
- **Footers and captions**: if the deck has a recurring footnote or caption, check that size,
  colour and position match.

## Content checks (both paths)

Read the deck in order, once. Where two slides play the same role, they read the same way.

- **Title phrasing is parallel.** Titles across a deck are the same kind of thing: all claims
  or all labels. `Three reasons to decide this year` and `Costs` are not the same kind of thing.
- **List items are grammatically parallel** within a slot: all noun phrases or all verb
  phrases, all with or all without a trailing period.
- **Layout variety** (template path). No layout three times in a row. If the deck used
  `Title and Content` for six slides, some of that content wanted two blocks or a figure; go
  back to phase 3.
- **Every figure is referenced in the text.** The slide text or the speaker notes say what a
  chart shows.
- **On-slide text is still short**: 3 to 7 words for most elements, one sentence at most for
  a headline. Check the render, not the source: `add-text` shrinks overlong text to fit, so an
  over-full slot looks fine in the JSON and cramped on the slide.
- **Speaker notes are absent from the slide.** Text that appears in both places is cut from
  one, usually the slide.
- **The arc still holds.** Read the titles alone, in order: they tell the story. A gap is a
  missing slide; a repeat is two slides to merge.
- **Numbers agree with each other** across slides and with the source. A metric quoted on
  slide 2 and on slide 5 matches, and a title claims no more than the numbers under it.

`extract-text` on the finished deck gives one line per paragraph, the whole deck in a page or
two. Read it top to bottom: phrasing drift shows there and not when checking one slide at a
time. `extract-shapes --issues-only` flags overflow, off-slide shapes, overlaps and hand-typed
bullets; `validate` adds empty placeholders and unfilled visual slots. Ask `docs:pptx` (see
"What this is" in `SKILL.md`) for all three on `<name>.pptx`, the issues-only shapes going to
`<name>/issues.json`.

Then read the rendered slides at 150 DPI for density and fit, which text extraction cannot
show.

On the template path, fix at the `slides.md` level, then rebuild from
[04-native-build.md](04-native-build.md) step 1. Never hand-edit the `.pptx`: the next
rebuild would drop the fix.

## Method (bespoke design path)

Dump the font size, colour and position of every text element across every slide's shapes
JSON and scan the table for outliers. This finds small numeric differences faster than
reading rendered images. One `jq` call per slide file, no script:

```bash
jq -r '."slide-0"[] | select(.type=="textbox") |
  [(.text.paragraphs[0].text[0:25]), (.text.paragraphs[0].font_size|tostring),
   (.text.paragraphs[0].color // "-"), (.left|tostring), (.top|tostring)] | @tsv' \
  slide1_shapes.json | column -t -s $'\t'
```

Run it against each slide's shapes file and compare the columns for the elements that must
match across slides (main title, header lockup): same font size, same colour, same left and
top.

Fix at the shapes-JSON level (not by hand-editing the built `.pptx`), then rebuild and
re-verify with the side-by-side render comparison from phase 4.

## When fixing a position, preserve the rhythm

If a fix moves an element far (for example, a title moved up to match the other slides),
shift the whole content block below it by the same delta. Otherwise the fix leaves an
oversized gap. Apply the same delta to every `top` (and every line's `y1` and `y2`) below the
moved element in the shapes JSON.

## Done

**Template path:** save to the deliverable path, run one final render **from that file**,
read it, and show it to the user. That is gate 2.

**Bespoke design path:** once the consistency pass is clean, save to the deliverable path,
add the speaker notes (from the talking track drafted in phase 2) with `docs:pptx`'s
`add-notes`, and do one final render and read of the deliverable file, not a scratch copy,
before calling the deck done.
