# card_deal

A deck dealt on the beat: one card per beat flies in and lands on a stack, the cards under it step back, and the stack sweeps away when the caption group changes. A caption with a counter and ticks names the group.

## When to use

- A fast opening or montage that shows many items of a few kinds: charts, photos, slides, screens, products.
- A count the viewer follows, rising with each card.
- Scenes cut to music, since every landing falls on a beat.

## Build

- DOM and CSS 3D transforms on GSAP; no three.js, no images. The page is portrait.
- One paused timeline tweens a clock over the scene length; `draw(t)` sets every transform from `t`, so each frame is a pure function of time. The captions and the flash are ordinary tweens on the same timeline.
- The constants at the top of the script hold every value: frame size, stack centre, card width, the deal path `PATH`, `FLIGHT`, `BEATS`, `GROUPS` and `CARDS`. Each group deals its cards on consecutive entries of `BEATS` from its start.
- Card sizes come from the aspect ratios in `CARDS` only. No size depends on a loaded image; an image still loading would give each render worker a different layout, and the frames would jump.
- The placeholder drawings (charts, landscape, slide) are blocks placed in percent of the card, varied by a seeded generator.
- Real pictures: an `<img>` in `.face` with `object-fit: cover`, its aspect ratio in `CARDS`.
- Each card flies along a curved path from off-frame, alternating sides, with a 3D tilt that eases out on landing. `PATH` keeps the path below the caption; a path from above the stack crosses the caption.
- A buried card steps up, shrinks, dims and tilts a little per card above it, alternating sides so its edges show.
- Each landing has an edge flare, a light sweep and a small scale dip.
- Two walls of small blurred cards drift behind the stack, so the background moves on every frame.

## Camera and timing

- No camera. Each stack pushes in slowly while it is up; the last one keeps pushing to the last frame.
- Every landing is on a beat of `BEATS`; a card's flight takes `FLIGHT`, which is shorter than one beat.
- At a group change the old caption leaves, the stack drops out of frame under a flash, and the new caption punches in with the next group's first card.
- The counter and the ticks step up as each card lands.

## What to vary

- Palette and fonts: the `:root` variables.
- `GROUPS`, `CARDS` and `BEATS`. A gap of one beat before a group change lets the last card of a group hold before the sweep.
- Card heights: keep a full stack clear of the caption and of the bottom of the frame.
- Tempo: scale `BEATS` and `FLIGHT` together.
- Landscape: the frame size, the stack right of centre, the caption in the left column, a path that enters from the sides at the stack's height, and a shorter sweep drop.
- Narrated: each landing on `W(n, "word")` of the word that names the card, each group start on `S(n)`.
