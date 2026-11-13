# 1. Deck outline

Scope the deck before writing slide copy or touching any visual tool. Skipping this step is
how slide 1 gets regenerated three times because the audience or the ask shifted.

## Decide before drafting

- **Audience.** Who reads this, and what do they already know? A deck for a peer who works
  in the details reads differently from one for an executive who wants the headline only.
- **The ask.** Write the literal request (an email, a verbal ask, a chat message) verbatim
  somewhere durable. Decks drift from the ask over several sessions; the original words
  catch that drift early.
- **Slide count.** For executive one-shot briefings, fewer is better: 2 or 3 slides force a
  sharp argument. Add slides only when the content needs the room. Past **about 15 slides**,
  ask whether the deck should be split, or whether the extra detail belongs in speaker
  notes. This is a check, not a hard limit.
- **Narrative arc.** One sentence per slide stating what it argues or shows, in order. If
  two slides argue the same thing, cut one. A gap in the arc is a missing slide, not a
  missing bullet on an existing one.
- **The trap in the question.** If the ask presupposes something you do not agree with (a
  false binary, a comparison you would lose, a frame that is not yours), decide the reframe
  now, before drafting content that accepts the trap.
- **Build path.** Template (fill the layouts of the brand's template natively) or bespoke
  design (image-gen design, then native backport, or an images-only deck when the user
  chooses one, [04-image-assembly.md](04-image-assembly.md)); see `SKILL.md`. Everything
  below that differs between the two is marked.
- **Brand and layout family (template path).** Decide the brand (the one the user names,
  else `neutral`) and, roughly, whether this is a text deck, a two-column comparison deck or
  a figures deck. Per-slide layouts come in phase 3, but this decision shapes what phase 2
  writes. The template owns colours, fonts, type scale and logo treatment; see
  [03-layout-mapping.md](03-layout-mapping.md).

## File layout: one folder per deck

Every build produces process files (the working doc, generated slide PNGs, icon sheets,
`_v2`/`_v3` drafts, intermediate renders, timestamped backups). Keep all of them in **one
folder next to the deliverable, named after the deck's base filename**, so they never
scatter across the parent directory.

For a deliverable at `path/to/<name>.pptx`, the folder is `path/to/<name>/`:

```
path/to/
  <name>.pptx            <- the deliverable, sits alongside the folder (not inside it)
  <name>/                <- everything else the process produces
    checklist.md         <- progress checklist (create first, tick as you go, below)
    working.md           <- the working doc (content + spec source of truth, below)
    images/              <- generated slide PNGs, icons, logos (bespoke design)
    slides.md            <- the content, in the phase-2 dialect (template path)
    outline.md           <- the layout mapping, ending in template_mapping (template path)
    figures/             <- chart/table JSON specs and user-supplied images (template path)
    renders/             <- export-slides output for verification
    backups/             <- timestamped .pptx backups
```

The deliverable stays at `path/to/<name>.pptx`; the folder of the same name next to it holds
everything else. Decide the exact path of `<name>.pptx` first (the Status line below), then
derive the folder from it.

## Progress checklist

**Create `<name>/checklist.md` before anything else**, and keep it current: it lets a build
survive an interrupted or restarted session. One box per step, per slide for the per-slide
phases. **Tick a box when its step is done, before starting the next one.** A checklist
filled in at the end cannot be resumed from: at any moment, the first unchecked box is where
to continue.

On every start or resume: read this file, find the first `[ ]`, do that step. Do not
restart from phase 1 or redo a checked step.

Template (for a 3-slide deck; add rows per slide):

```markdown
# Build checklist: <deck name>

Resume rule: first unchecked box below is the next step. Tick immediately after each step.

One box per line (two `- [ ]` on one line is not valid markdown: only the first is a
checkbox). Per-slide phases get one box per slide, with the approval/verify gate
folded into the box so it's only ticked when that step is truly done. Deck-level phases
(spec, assembly, consistency) get a single box.

## Phase 1: Outline (deck-level)
- [ ] Deliverable path decided; one-folder layout + this checklist created
- [ ] Audience, verbatim ask, slide count, narrative arc in working doc
- [ ] Shared design spec locked (accent hexes, type scale, logo, reference image)

## Phase 2: Content (one box per slide)
- [ ] Slide 1 content drafted + approved
- [ ] Slide 2 content drafted + approved
- [ ] Slide 3 content drafted + approved
- [ ] Speaker notes drafted (all slides)

## Phase 3: Image design (one box per slide)
- [ ] Slide 1 image generated + approved by name
- [ ] Slide 2 image generated + approved by name
- [ ] Slide 3 image generated + approved by name

## Phase 4: Native backport (one box per slide)
- [ ] Slide 1 backported + verified vs source (150 to 200 DPI)
- [ ] Slide 2 backported + verified vs source
- [ ] Slide 3 backported + verified vs source
- [ ] Deck assembled (jq merge → one add-shapes) + notes applied (add-notes)

## Phase 4, images-only (deck-level; replaces the backport boxes above)
- [ ] Deck assembled: new-deck, one full-slide image per slide (add-shapes), notes (add-notes)
- [ ] Rendered from the deliverable at 150 to 200 DPI; each slide matches its image; notes present

## Phase 5: Consistency (deck-level)
- [ ] Cross-slide scan run (background, header, title, subtitle, accents, captions)
- [ ] All drift reconciled (or each kept difference cited to a working-doc line)
- [ ] Final render + check from the actual deliverable file
```

For the template path phases 3 to 5 differ. Use this instead of the Phase 3 to 5 sections
above (add rows per slide), and one box per slide in phase 2 with "drafted in slides.md"
instead of "drafted + approved": content and mapping are approved together at the end of
phase 3:

```markdown
## Phase 3: Layout mapping (deck-level)
- [ ] Slot map at hand (neutral: 03-layout-mapping.md; other brand: probe deck, in outline.md)
- [ ] Layout chosen per slide, written to outline.md
- [ ] template_mapping line written
- [ ] GATE 1: slides.md + outline.md approved by the user

## Phase 4: Native build (deck-level, one box per stage)
- [ ] edit spec written (add-slide, text, figures, notes)
- [ ] edit applied to the template, saved to the deliverable path
- [ ] Rendered from the deliverable at 150 to 200 DPI and read back

## Phase 5: Consistency (deck-level)
- [ ] Cross-slide content scan run
- [ ] GATE 2: rendered deck approved
```

The phase 1 "shared design spec" box does not apply to the template path: the template owns
the design.

## Working doc setup

Create one markdown doc per deck (`<name>/working.md`, per the layout above) as the single
source of truth for the process: content, design rules, build status. It survives a
context reset in the middle of a build. Structure it like this:

```markdown
# <Deck name>: for <audience> (<date>)

Working doc for <the ask>. Build the deck per the process below.

## Status notes (context only; tick state lives in checklist.md)

- **Deliverable path:** `<path>.pptx`
- **Slide 1: <notes>** (approved PNG path, open questions, caveats: anything a
  checkbox cannot hold)
- **Slide 2: <notes>**

## Design rules: gate the whole deck

> Reference bar: <a real example image that defines the look>.
> 1. <rule>
> 2. <rule>
> ...
> **Build process:** <link to or restate the 5-phase process>

## The ask (<who>, <date>)

> <verbatim ask>

## Slide 1: <working title>

**Headline:** ...
**Subtitle:** ...
<content sections as they firm up>

## How to build the deck

<the phase-by-phase steps, so a fresh session can resume>
```

On the template path the content lives in `slides.md`, not here: the working doc holds the
ask, the audience, the narrative arc, open questions and per-slide caveats (for example
"Slide 2: waiting on the Q3 number from <person>; placeholder in slides.md", "Slide 4: user
asked for a chart; source data is <path>"), and drops the design rules section.

Every session starts by reading `checklist.md` (what is done, where to resume), then this
working doc (content, spec, per-slide notes), then `slides.md` on the template path. The
checklist is the progress state; the working doc holds what a checkbox cannot: the copy,
the design spec and per-slide caveats.

## Design rules: lock the shared spec before slide 1

Bespoke design path only. On the template path the template owns background, header, logo,
fonts, type scale and title position; skip this section.

Before generating any image, write down the shared visual spec every slide follows: colours
by hex (`accent1`, `accent2`, `accent3`, `dk1` and `lt1` from the `colors` of the deck's
brand from `brand:brand`; a deck without a brand uses the bundled `neutral` brand), fonts
from the same brand, a **style** and a **layout family** from the
[design library](design-library/README.md), the style's style line from `brand:style` (the
catalogue style its `style-*.md` names), type hierarchy (title, section label, body, and
roughly the size each reads as; the `neutral` brand's `guidelines.md` lists reference
sizes), logo treatment, and a reference image that defines the look to match (a
design-library `.png` guide works as the starting reference).

When each slide is generated against a *description* of the shared look instead of against
the other slides, headers come out in three sizes, one title lands at 22 pt and another at
36 pt, one background drifts to cream, and none of it shows until the deck is viewed slide
to slide (see [05-consistency-pass.md](05-consistency-pass.md)). A spec fixed before slide 1
avoids that rework.

## Next: [02-slide-content.md](02-slide-content.md)
