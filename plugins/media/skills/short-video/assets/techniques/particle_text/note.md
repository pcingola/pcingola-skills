# particle_text

A word formed by particles: spiral arms of glowing points come in from beyond the frame and lock into the letters one by one, each letter flashing and throwing sparks as its glyph fades in, then a light sweep, a hairline and a caption, inside an orbiting ring of particles and a drifting star field.

## When to use

- A title, a name or a closing word that must arrive with energy: an opening hook, an end card, a product or project name.
- A silent beat between parts, on a dark palette.
- Not for running text or more than one short line or two: the reveal reads letter by letter and holds at most 31 letters per text block.

## Build

- three.js 0.159.0 with `kit/particles.js` (`Kit.particles`, `assets/kit/README.md`). The word is two files beside the page: `<name>_targets.js` (points inside the letters, letter centres, the camera they were made for) and `<name>_tex.png` (fill, glow and letter index of the glyphs), loaded by `<script src>` and a hidden `<img>`.
- The targets are precomputed from the font file, so no seek waits on a web font load and every frame is the same in every render.
- One GSAP clock tween drives `draw(t)`; every particle position is a function of `t` and seeded values.
- The glyph texture is made only once its `<img>` is decoded, through a canvas: a texture uploaded empty first fails later, and one made from the `<img>` itself renders black in the render browser. `Kit.particles.prime` compiles the shaders and draws twice at once and again at the load event; without it frame 0 of the render can come out without particles.
- three.js pages render only on the GPU-backed render browser; software WebGL hangs on them.

## Camera and timing

- One push over the whole scene, from 1.35 to `end` (0.9) times the targets' camera distance, both read from the targets file, with yaw -3 to 3, pitch 3.5 to 1.2 and roll -2.5 to 1.5 degrees (`sineInOut`). The last 0.5 s holds still.
- Particles are in flight at 0 s. Letter k locks at `0.8 + k * 1.2 / (letters - 1)` s, so the last letter locks at 2.0 s for any word; its glyph fades in over 0.3 s from 0.1 s before.
- Orbit ring closes in 1.6 to 2.8 s. Light sweep 2.45 to 3.05 s, hairline 2.7 to 3.4 s, caption 3.0 to 3.7 s.
- Narrated: arrival base on `W(1, "word")`, the caption on `S(2)`, the hold to the scene end.

## What to vary

- Palette and fonts: the `:root` variables. `--ink` and `--accent` are the glyph fill gradient (top to bottom of the whole text block), `--glow` its glow, `--stream-1..3` the particles in flight, the ring and the field. A light background needs another blend: the particles add light.
- Seeds (`P.rng(4242)` and the others) change the spirals and the field without changing the timing.
- Density: `--count` of the targets (24000 by default; 20000 here) and `NA`, `NO` in the page. More points slow every seek.
- The caption: its text, size and the 3.0 s entry; remove it for a word alone.

## Another word

The page loads `title_targets.js` and `title_tex.png`, made from Source Sans Pro Semibold with:

```
short-video.sh particle-text Title --font source-sans-pro-semibold.ttf --name title --size 300 --tracking 0.02 --count 20000 --seed 7 --out <dir>
```

For a scene, write the files into its latest version and change `NAME`, the `<script src>` and the `<img>` id and `src` of the page to the new name:

```
short-video.sh particle-text "Your word" --font fonts/your-font-700.woff2 --name word --fit 0.6 -p <project> --scene <id>
```

The command prints the text's width and height in frame pixels at the page's end camera distance and as a share of the frame, and warns above 80% of the frame width (outside title-safe). `--fit F` picks `--size` so the text is F of the frame width.

- One argument per line: `particle-text "First line" "Second line" ...` centres each line; `--line-gap` (em, 1.12) sets their pitch. Letters count left to right, line after line.
- `--size` is the font size in frame pixels at the camera distance `--distance` (20) with `--fov` (35); the page ends at 0.9 times that distance, so the text shows about 1.1 times `--size`. The page takes its camera fov and distances from the targets file.
- `--frame WxH` defaults to `video:` of the project's `settings.yaml` (`-p`, or the current directory), else 1920x1080. `Kit.particles.targets` throws when the targets' frame differs from `#root`'s `data-width` and `data-height`.
- `--tracking` (em) opens the letter spacing; `--edge-share` (0.34) puts that share of the points on the outlines, which sharpens the letters' edges.

## Portrait

- A 1080x1920 page: the viewport meta, the `html, body` and `#root` CSS sizes and `#root`'s `data-width` and `data-height` set to 1080x1920, and targets made with `--frame 1080x1920` (the default in a portrait project).
- The frame is narrow: a word of more than about six letters fits better on two lines (`particle-text "First" "Second" --fit 0.7`). The spirals, the ring and the field scale with the frame and the text box.
- The caption's font size follows the frame's long side (40 px at 1920) and it scales down to at most 80% of the frame width; a long caption reads better split into a second element.
