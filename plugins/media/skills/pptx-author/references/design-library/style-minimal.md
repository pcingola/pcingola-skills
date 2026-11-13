# Style — Minimal Enterprise

Catalogue style: `minimal-enterprise` from `brand:style`. Its style line and the deck's
palette are the first line of every prompt (see `infographic.md`).

Guide image: `style-minimal.png`

## When to use

Default. Works for almost any content: process flows, comparisons, capability
lists, pillar summaries.

## Header line (brand is a slot, not baked in)

> Top-left header, small and subtle: bold `accent1` text "{PROJECT / DECK
> TITLE}", then lighter grey small text "{SLIDE LABEL}". [If a brand mark
> applies, add: "with {logo description} to the left of the title, small and
> understated, never dominant." Omit entirely for brand-neutral use.]

## Subtitle line (the assertion)

> Below the header, one short bold subtitle line in `dk1`: "{ONE-LINE
> CLAIM}". One sentence, an assertion of value, not a topic label.

## Closing line (paste verbatim, last line before Negative)

> Extremely clean, elegant, minimal, generous breathing room. All text
> correctly spelled and crisp.

## Negative block

> neon, glow, dark background, greek columns, 3d, photorealistic, busy,
> cluttered, gibberish, misspelled, heavy gradients, drop shadows, large logo

## Center layout

Pick one of the shared layouts: A–E defined inline in `infographic.md` (card
row, three-stage flow, pipeline, hub-and-spoke, columns with chips), or F–I in
their own files (`layout-dashboard.md`, `layout-timeline.md`,
`layout-flowchart.md`, `layout-comparison.md`) — all style-agnostic and reused
across every style doc in this directory.

## Design tokens

Same vocabulary as `infographic.md`: card = white rounded rectangle + thin
colored top accent + one line icon + bold title + grey subtitle. Chips, hero
panel, foundation band and connectors are as defined there. Colours and fonts from
the deck's brand (`brand:brand`), else the `neutral` brand.
