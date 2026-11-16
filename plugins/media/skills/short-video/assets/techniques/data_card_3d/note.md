# data_card_3d

A card with a counting number, a caption and a share bar over a 3D scene that keeps moving underneath.

## When to use

- The scene states one number: a total, a count, a share.
- After a 3D sequence, to give its result without cutting away from the world.

## Build

- three.js 0.159.0 with `kit/camera.js`, `kit/glow.js`, `kit/shadow.js`, `kit/tiltshift.js`; the card is HTML over the canvas, outside `#anchored`.
- One GSAP clock tween drives `draw(t)`; the card tweens are ordinary GSAP tweens on the same timeline.
- The 3D world dims under the card: a proxy `dim` (0 to 1, 0.6 to 1.4 s) raises the vignette and the tilt-shift strength.
- The bar is a `scaleX` tween from 0 with `fromTo` and no CSS `transform` (HyperFrames lint refuses a CSS transform that GSAP also tweens).

## Camera and timing

- A slow orbit: yaw -6 to 18 degrees, pitch 50 to 46, d 22 to 19 over the whole length, `sineInOut`.
- Card rises at 0.8 s. Number counts 0 to its value from 1.1 s over 1.8 s (`power2.out`), formatted with `toLocaleString`.
- Caption words at 1.6 s, 0.12 s apart. Bar and percentage from 3.0 s over 1.4 s.
- The count ends on the exact value; the last 2 s hold the card while the orbit continues.

## What to vary

- `VALUE`, `SHARE`, the caption words, `--accent` and the card's top border.
- The world under the card: any 3D scene of the film; reuse the previous scene's world and camera so the card arrives over a known place.
- Glow points (`Kit.glowPoints`) are additive and almost vanish on a light ground. On a light palette use solid markers; on a dark one, glows.
- Two cards: place them left and right of centre and stagger them by about 1 s.
