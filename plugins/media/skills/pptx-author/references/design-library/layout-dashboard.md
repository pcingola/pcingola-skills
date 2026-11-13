# Layout — KPI Dashboard

Guide image: `layout-dashboard.png`

Center layout **F** (extends `infographic.md`'s A–E). 3–5 equal tall white rounded
tiles in a single horizontal row.

## When to use

Metrics/scorecard slides — a handful of numbers you want read at a glance. Not for
narrative or process content; use one of the other layouts for those.

## Center layout

3–5 equal tall white rounded tiles in a single horizontal row, no dividers or borders
between them (separated by white space only). Each tile, top to bottom: a short grey
label, a large number in a **light/regular weight, not bold**, and one small line icon
in the lower half. Tiles fill most of the canvas height with an even bottom margin, not
floating in the top half.

## Pitfalls (learned the hard way)

- **Never use a chart or sparkline** for the icon — even a fake trend line reads as
  real data and someone will ask what it's plotting. Use a plain line icon instead.
- Tiles that are short/thin leave a large empty gap in the bottom half of the canvas —
  make them tall enough to fill the vertical space.
- Bold numbers read as too heavy at this size — use light/regular weight.
- No vertical divider lines between tiles — white space alone separates them.

## Design tokens

Colours and fonts from the deck's brand (`brand:brand`), else the `neutral` brand.
Pairs with any of the 3 styles in this directory (`style-minimal.md`,
`style-editorial.md`, `style-colorblock.md`).
