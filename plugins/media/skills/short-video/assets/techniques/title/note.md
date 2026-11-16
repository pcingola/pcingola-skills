# title

A title card: kicker, title words rising out of line masks, a rule drawing, a subtitle, over light that drifts.

## When to use

- The opening scene of a film, a chapter title, or a silent card between parts.
- Any scene of text alone that must still move for its whole length.

## Build

- GSAP only. Each title line is an `overflow: hidden` span; each word is an `inline-block` that tweens `yPercent` 110 to 0.
- Two blurred radial gradients in `#anchored` drift in opposite directions over the whole length; the text block scales 0.985 to 1.02 linearly. These keep the hold moving.
- The rule tweens `scaleX` 0 to 1 from its left edge, with `fromTo` and no CSS transform.

## Camera and timing

- No camera move on the text; the block's slow scale stands in for a push.
- Kicker 0.2 s. Title words from 0.45 s, 0.12 s apart, 0.7 s each (`power3.out`). Rule 1.3 to 2.0 s. Subtitle 1.7 s.
- Everything is on screen by about 2.3 s; the rest of the length holds with the drift.

## What to vary

- Palette and fonts: the `:root` variables; `--glow-1` and `--glow-2` are the drifting light.
- Line breaks: one `.line` per title line, set by hand so the break falls between phrases.
- A light palette: light `--bg`, dark `--text`, glows a few percent darker than the background.
- With a brand: the logo above the kicker, entering with it.
- Narrated: the title words on `W(1, "word")`, the subtitle on `S(2)`.
