# Techniques

Working scene pages to start from, change or ignore. Each directory has `index.html` (a silent scene page on GSAP, 1920x1080 unless its note says portrait), `still.png` (one frame) and `note.md` (when to use it, camera and timing, what to vary). Palette and fonts are CSS variables at the top of each page.

To use one, copy its page into the scaffolded `index.html`. Keep the scaffold's root attributes (`data-composition-id`, `data-duration`) and its `window.__timelines` key. Replace the literal times with `S(n)` and `W(n, "word")` in a narrated scene, or `ST("id")` and `STE("id")` in a world. `scaffold` and `render` copy the libraries and `kit/` files the page's `<script src>` names. Other files a page loads (generated targets, font files) are made or copied as its `note.md` says.

- `aerial_routes`: aerial city map with route ribbons drawing between stations, rider glows, pinned labels and tilt-shift (three.js, kit).
- `street_hero`: one object at street level, low camera, soft shadows, slow push with depth blur (three.js, kit).
- `data_card_3d`: a card with a counting number, caption and share bar over a slowly orbiting 3D scene (three.js, kit).
- `flat_chart`: a d3 bar chart built mark by mark with GSAP, accent and source last; no three.js.
- `title`: kicker, title words rising out of line masks, rule and subtitle over drifting light (GSAP only).
- `vertical_feed`: placeholder cards scroll up one column and stop on each beat, slower background columns, motion blur, caption band with a counter (GSAP only, portrait).
- `card_deal`: one placeholder card dealt onto a CSS 3D stack per beat, the stack sweeping away at each caption change (GSAP only, portrait).
- `particle_text`: particles spiral in and lock letter by letter into a word or two-line title, with sparks, a light sweep, a hairline, an orbit ring and a caption; targets from the `particle-text` command (three.js, kit).
- `gallery_3d`: framed pictures in a dark 3D space over a mirroring floor with spots and depth blur; a fly-through from picture to picture, a museum row with a dolly and pull-back, or a vortex exit into a flare (three.js, kit).
- `pipeline_3d`: a process as a line of stations lit in turn on their words, with particle flows between them and a pull-back fitted to the whole line, or a hub feeding N nodes; a replaceable backdrop and a solid mode for light grounds (three.js, kit).
- `beat_reel`: shots cut on a music beat grid with a slice wipe, a chromatic slice and a flash frame at each cut, one word per shot, a closing title; placeholder shots stand in for a background.mp4 montage (GSAP, kit).
- `terminal`: commands typed into a floating terminal with a caret, progress bar and output, one camera turn per command, an optional browser opening at the end (GSAP only).
