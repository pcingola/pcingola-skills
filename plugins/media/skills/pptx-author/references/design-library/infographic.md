# Slide Template — Infographics (base frame)

Reference for writing image-generation prompts that stay visually consistent across a
deck. Every slide prompt is built from the **fixed frame** below plus **one center
layout** chosen from the patterns. Copy the frame verbatim, swap the variable bits, pick
a layout.

Brand is a **slot**, not baked in: the header, logo, and colors are placeholders you set
once and reuse on every slide. Colours, fonts, type sizes and the card, chip, axis and
hero vocabulary come from the deck's brand, loaded with `brand:brand` (`brand.yaml` and
`guidelines.md`); a deck without a brand uses the bundled `neutral` brand. Colour roles in
these docs (`accent1`, `accent2`, `accent3`, `dk1`, `lt1`) are the `colors` keys of that
`brand.yaml` and go into the prompt as their hex values.

---

## Fixed metadata (same on every slide)

- **Model:** the `media:image-gen` tier `multi-ref` (`--tier multi-ref`), the
  `image_multi_ref` model of its config, which takes several reference images
- **Aspect:** 16:9 — **Size:** 2K
- **Ref:** your brand logo, if any (`--ref`), so it stays consistent; tokens from the
  deck's brand

## Style line (first line of every prompt)

Load `brand:style` and ask for the style line of the deck's catalogue style (named in the
chosen `style-*.md`, for example `minimal-enterprise`). The first line of every prompt is
that style line, then the palette: the deck brand's `accent1`, `accent2`, `accent3`,
`dk1` and `lt1` hex values (the `neutral` brand's when the deck has no brand), which
replace the style's default palette.

## Fixed header line (brand is a slot)

> Top-left header, small and subtle: bold `accent1` text "{PROJECT / DECK
> TITLE}", then lighter grey small text "**{SLIDE LABEL}**". [If a brand mark applies,
> add: "with {logo description} to the left of the title, small and understated, never
> dominant." Omit entirely for brand-neutral use.]

- `{SLIDE LABEL}` = e.g. `Section 3 — Overview`, `How it works`.
- Logo (if any) is **always small, tasteful, understated**. Never dominant.

## Fixed subtitle line (the assertion)

> Below the header, one short bold subtitle line in `dk1`: "**{ONE-LINE CLAIM}**".

- One sentence, an assertion of value — not a topic label.
- Examples: "Weekly reports in one click instead of a day of work";
  "Every forecast checked against last year's actuals".

## Fixed closing line (paste verbatim, last line before Negative)

> Extremely clean, elegant, minimal, generous breathing room. All text correctly
> spelled and crisp.

(Exec-summary slides add "corporate" and "lots of breathing room" — interchangeable.)

## Fixed negative block

> neon, glow, dark background, greek columns, 3d, photorealistic, busy, cluttered,
> gibberish, misspelled, heavy gradients, drop shadows, large logo, dominant logo

- Add `architecture pillars` for exec-summary / "pillars" slides.
- Add `heavy colored boxes, boxes without icons` when a layout risks over-coloring.

---

## Design tokens (vocabulary to reuse)

- **Palette:** three accent colors (`accent1`, `accent2`, `accent3`) + `dk1` for body
  text, lighter grey for subtitles/captions. Use exactly the three accent colors of the
  deck's brand.
- **Card:** white rounded rectangle + **one** small minimal line icon + bold title +
  one short grey subtitle. Accent is either a *thin colored top accent line* or a
  *colored header band* — pick one convention per slide, not both.
- **Hero panel:** a taller white rounded panel with an **accent border** — marks the one
  most important element (the core component of the story).
- **Foundation band:** one wide band spanning under the cards. Style it the **SAME as
  the cards** (white, rounded, thin colored accent) — explicitly **NOT a flat grey box**.
  Holds a left line icon + one bold dark line of text (the summarizing "shared layer").
- **Chips / pills:** small light pill chips list examples inside a card.
  - status pill: green "Done", grey "Planned", etc.
  - "new / expansion": a single **accent-outlined dashed chip** (e.g. "New region").
  - faint grey "+ more" chip to imply a longer list.
- **Connectors:** thin lines / thin rightward arrows. No loop or feedback arrows
  unless the content is genuinely a cycle.
- **Icons:** always small minimal **line** icons, one per card.
- **Spacing:** generous, evenly spaced, vertically centered relative to each other.

---

## Center layouts (pick one)

### A. Card row (+ optional foundation band)
3–5 equal cards in one horizontal row, lots of space between, thin colored top accent,
one icon, bold one-word/short title, one grey subtitle. Optionally a wide foundation
band underneath (same card style) carrying the summarizing statement; thin connectors
may drop from each card to the band.
*Good for:* exec summaries, a platform/capability overview.

### B. Three-stage left-to-right flow (input → hero → output)
- **LEFT:** a vertical stack of small same-style cards (the inputs/sources), optionally
  captioned above in small grey text.
- **MIDDLE:** the **hero** — taller white panel, accent border, icon at top, bold title,
  and ~3 small pill chips inside.
- **RIGHT:** a single card in the **same style as the left cards** (the outcome).
- Thin rightward arrows between stages; all stages vertically centered.
- Optional small accent-outlined pill chip hanging off the hero via a thin line.
*Good for:* a knowledge/reasoning flow, an assistant that turns sources into an answer.

### C. Horizontal pipeline (steps with arrows)
4 equal cards in a row, each with a **colored header band** (icon + bold short title)
and one short grey caption; thin rightward arrows between them. Optionally wrap all
steps in a thin rounded outline box with a small accent label at top-left
("End to end").
*Good for:* a multi-step process, an intake-to-output flow, a model pipeline.

### D. Hub-and-spoke
Center `accent1` circle with a small icon and bold white label (e.g. "You"). 4 cards
arranged around it (top/right/bottom/left), each connected by a thin line, each with
an icon, bold title, short grey subtitle.
*Good for:* a personalization / "everything points at the user" story.

### E. Columns with chips
Equal tall columns in a row, each a card with a colored header band (icon + domain
title) and a vertical list of small pill chips (example apps). Use the dashed
accent-outlined chip / "+ more" conventions for empty vs. populated columns.
*Good for:* verticals / domains with example applications under each.

### More layouts (own files)
Patterns F–I each have their own spec + guide image, same shape as the style docs:
- `layout-dashboard.md` — KPI dashboard (metrics/scorecard slides)
- `layout-timeline.md` — timeline / roadmap (phased plans)
- `layout-flowchart.md` — flowchart (branching process/decision logic)
- `layout-comparison.md` — comparison split (trade-offs, option A vs. B)

### Optional bottom caption (any layout)
One thin centered grey caption line for provenance / qualifier / a `Days → Minutes`
style takeaway. E.g. "Source: annual customer survey, 2,000 respondents".

---

## Skeleton to copy

```
# Prompt — {TITLE}

- **Model:** tier multi-ref
- **Aspect:** 16:9 — **Size:** 2K
- **Ref:** {your brand logo, if any}; tokens from the deck's brand

## Prompt

{STYLE LINE from brand:style} {PALETTE: accent1, accent2, accent3 hex values, dark tone dk1, light tone lt1}

{FIXED HEADER LINE, with {SLIDE LABEL}}

{FIXED SUBTITLE LINE, with {ONE-LINE CLAIM}}

Center: {ONE LAYOUT FROM A–E below, or F–I in their own files, with its cards/stages/chips spelled out}.

{optional foundation band}  /  {optional bottom caption line}

{FIXED CLOSING LINE}

## Negative

{FIXED NEGATIVE BLOCK (+ slide-specific additions)}
```

---

## Styles

The frame above pairs with any of three interchangeable style treatments — pick one per
deck (or per slide, sparingly):

- `style-minimal.md` — clean flat white, the house default.
- `style-editorial.md` — oversized numerals, magazine typography, no cards.
- `style-colorblock.md` — solid color panels, high contrast; for dividers / standout slides.
