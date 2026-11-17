# vertical_feed

A portrait feed: cards scroll up one column and stop on each beat, over slower background columns, with a caption band that names the group and counts its cards.

## When to use

- A phone hook or teaser that shows many items of a few kinds in a few seconds: charts, photos, slides, screens, products.
- A list of outputs where the count matters more than any one item.
- The page is portrait. A landscape version needs the changes in What to vary.

## Build

- GSAP only. One paused timeline tweens a clock `t` over the scene length; `draw(t)` sets every transform, filter and counter from `t`, so any frame can be seeked.
- The constants at the top of the script hold every value: frame size, stop position `CY`, card width and gap, `HOLD`, the card table `CARDS`, `GROUPS` and `BEATS`. The rest of the page derives from them.
- `CARDS` gives each card an aspect ratio, and its height is derived from the card width. No size depends on a loaded image; an image still loading would give each render worker a different layout, and the frames would jump.
- `drawCard(kind, seed)` draws a placeholder in HTML and CSS from a seeded generator: a title bar, text lines and a shape per kind.
- `GROUPS` lists, in screen order, each group's caption, accent, cards and start. The caption, its counter and its ticks are built from it.
- Filler cards above the first card and below the last keep the frame full at both ends.
- Two background layers of smaller, blurred, dimmed cards move with the scroll at fractions of its speed (parallax).
- Motion blur is a vertical SVG blur on the main column, set from its speed and off while it holds.
- A shade behind the caption keeps card content from showing under it.

## Camera and timing

- No camera. The scroll is the only large move.
- The column holds each card for `HOLD`, then a smoothstep move brings the next card to `CY` on its beat. The speed is zero at each beat, so stops are clean.
- `BEATS` sits on the music's beat grid.
- A card grows and brightens as it nears `CY`, and a light sweep crosses it as it settles.
- Each caption enters just before its group's first beat and leaves just before the next group; a flash marks each group change.
- The last card keeps a slow push to the end, so the tail is not still.

## What to vary

- Palette and fonts: the `:root` variables.
- Content: `CARDS`, `GROUPS` and `BEATS`, one beat per card in `GROUPS` order.
- Pace: closer beats give shorter holds and a faster feed.
- Real items: an `<img>` of fixed size replaces the `drawCard` output; the size stays in `CARDS`.
- Landscape: the frame size, a narrower card width so a card fits the height, the caption in the left third, the column in the right two thirds, and more background columns. Cards much taller than wide do not fit.
- Narrated: each beat on `W(n, "word")` of the word that names the item, each group start on `S(n)`.
