# Techniques

Working scene pages to start from, change or ignore. Each directory has `index.html` (a silent 1920x1080 scene page on GSAP), `still.png` (one frame) and `note.md` (when to use it, camera and timing, what to vary). Palette and fonts are CSS variables at the top of each page.

To use one, copy its page into the scaffolded `index.html`. Keep the scaffold's root attributes (`data-composition-id`, `data-duration`) and its `window.__timelines` key. Replace the literal times with `S(n)` and `W(n, "word")` in a narrated scene, or `ST("id")` and `STE("id")` in a world. `scaffold` and `render` copy the libraries and `kit/` files the page's `<script src>` names.

- `aerial_routes`: aerial city map with route ribbons drawing between stations, rider glows, pinned labels and tilt-shift (three.js, kit).
- `street_hero`: one object at street level, low camera, soft shadows, slow push with depth blur (three.js, kit).
- `data_card_3d`: a card with a counting number, caption and share bar over a slowly orbiting 3D scene (three.js, kit).
- `flat_chart`: a d3 bar chart built mark by mark with GSAP, accent and source last; no three.js.
- `title`: kicker, title words rising out of line masks, rule and subtitle over drifting light (GSAP only).
