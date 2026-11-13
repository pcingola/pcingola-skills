# Style — Bold Color Block

Catalogue style: `bold-color-block` from `brand:style`. Its style line and the deck's
palette are the first line of every prompt (see `infographic.md`).

Guide image: `style-colorblock.png`

## When to use

A section-divider slide, a 3-part structure you want to visually dominate a
deck, or a single slide that needs to stand out from a run of Minimal
Enterprise slides around it. Use sparingly: it does not fade into the
background of a deck the way Minimal Enterprise does. Not for dense/long
content: text has to stay short to survive high contrast.

## Header line (brand is a slot, not baked in)

> Top-left header, small and subtle, on a thin white bar above the color
> blocks: bold `accent1` text "{PROJECT / DECK TITLE}", then grey small
> text "{SLIDE LABEL}". [Add a brand mark only if the deck calls for one; omit
> for brand-neutral use.]

## Subtitle line (the assertion)

> Below the header, one short bold subtitle line in `dk1` on white:
> "{ONE-LINE CLAIM}".

## Closing line (paste verbatim, last line before Negative)

> Extremely clean, bold, confident, high contrast, generous internal padding
> within each panel. All text correctly spelled and crisp.

## Negative block

> neon, glow, gradients, 3d, photorealistic, busy, cluttered, gibberish,
> misspelled, drop shadows, large logo, muddy colors, low contrast text

## Center layout

Equal solid-color rectangular panels side by side (`accent1` / `accent3` /
`accent2`, in that order), each with one small white line icon, a bold white
short title, one small light subtitle line. Panels touch edge to edge like a
flat poster grid; thin white arrows at the seams if the content is sequential.
3 panels is the sweet spot; with more than 4 the contrast stops reading as bold
and starts reading as busy.

## Design tokens

Colours and fonts from the deck's brand (`brand:brand`), else the `neutral` brand,
inverted: white text/icons on solid color, instead of colored accents on white.
