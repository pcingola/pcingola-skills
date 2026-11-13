# Design library

Reusable, **brand-neutral** slide designs for `pptx-author`. Use these so a deck starts
from a known-good design instead of a blank canvas: pick a style + a layout, apply the
deck's brand, and prompt `media:image-gen` (phase 3), then backport to native pptx (phase 4).

The designs treat brand as a slot; nothing here is tied to a company. Two skills supply
what the designs leave open, each loaded with the Skill tool:

- `brand:style`: the style line of each style (named in its `style-*.md`), the first line
  of every prompt.
- `brand:brand`: colours, fonts, type sizes and the card, chip, axis and hero vocabulary
  (`brand.yaml` and `guidelines.md` of the deck's brand). A deck without a brand uses the
  bundled `neutral` brand.

## What's here

- `infographic.md`: the base frame, fixed prompt skeleton (style/header/subtitle/negative)
  + center layouts **A–E** (card row, three-stage flow, pipeline, hub-and-spoke, columns
  with chips) + the shared design-token vocabulary.
- Styles (pick one per deck): three interchangeable looks over the same frame, each
  naming its catalogue style in `brand:style`:
  - `style-minimal.md` (+ `.png`): `minimal-enterprise`, the default.
  - `style-editorial.md` (+ `.png`): `editorial-big-number`, oversized numerals, no cards.
  - `style-colorblock.md` (+ `.png`): `bold-color-block`, solid color panels; dividers / standout.
- Layouts F–I (pair with any style), each a spec + guide image:
  - `layout-dashboard.md` (+ `.png`): KPI tiles (metrics/scorecard).
  - `layout-timeline.md` (+ `.png`): timeline / roadmap (phased plans).
  - `layout-flowchart.md` (+ `.png`): boxes/arrows with a branch (decision logic).
  - `layout-comparison.md` (+ `.png`): two-column split (trade-offs, A vs. B).

## How to use in a build

1. **Phase 1 (design spec):** pick a style and a layout family; copy the deck brand's
   tokens (from `brand:brand`, the `neutral` brand when the deck has none) into the deck's
   working doc.
2. **Phase 3 (image design):** build each slide's `media:image-gen` prompt from `infographic.md`'s
   skeleton: the style line from `brand:style` plus the palette, the chosen style doc's
   header, subtitle, closing and negative lines, and one layout. The `.png` guide beside
   each style/layout shows the target.
3. **Phase 4 (backport):** measure the approved image and rebuild in native pptx; the palette
   hexes and type scale come from the tokens you locked in phase 1.

## Adding a design

- **New layout:** add a `.md` in the shape of `layout-*.md` (when to use / center layout /
  design tokens) plus a `.png` guide render. Name colours by their `brand.yaml` roles
  (`accent1`, `accent2`, `accent3`, `dk1`, `lt1`), don't define hex values.
- **New style:** add the style to `brand:style` first, then a `.md` here in the shape of
  `style-*.md` (catalogue style name / when to use / header / subtitle / closing /
  negative / center layout) plus a `.png` guide.
- Keep everything brand-neutral: brand values belong in the brand folder, not in a design doc.
