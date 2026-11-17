# gallery_3d

Framed picture cards in a dark 3D space over a glossy floor that mirrors them, lit by spots from above, with depth blur. `MODE` at the top of the script picks one of three shots.

- `float`: the camera flies from hero card to hero card through cards floating at three depths. Each hero snaps forward, turns to face the camera and takes a light sweep, and the caption steps its counter and title.
- `museum`: large canvases in one row on the floor. The camera dollies along the row, each canvas lights up in turn, then the camera pulls back until the whole row fills the frame width and the caption leaves.
- `vortex`: the `float` fly-through, then every card spirals past the camera into one point that flares under an end word.

## When to use

- The film shows a body of pictures: a portfolio, generated images, slides, screenshots, products.
- `float` for a fast hook on a beat grid; `museum` for a narrated sentence per picture or kind of picture; `vortex` to end a hook or a section on a title.

## Build

- three.js 0.159.0 with `kit/camera.js`, `kit/glow.js`, `kit/tiltshift.js` and `kit/gallery.js` (`Kit.gallery`: cards, spots, dust, sky, floor and mirrored cards).
- `PICTURES` lists the pictures in order: the heroes (or the row) first, the rest fill the background. An entry with `src: null` is a placeholder drawn on a canvas; `src: "img/01.jpg"` loads a file placed next to `index.html`. `Kit.gallery` draws each `<img>` into a canvas before upload, since a texture made from an `<img>` renders black in the render browser.
- Each card keeps its picture's aspect inside a largest width and height: 3.4 x 2.1 for a hero, 3.6 x 2.6 for a museum canvas, w x 0.7 w for a background card. A portrait picture is as high as the box and narrower. The optional `aspect` of a `PICTURES` entry sizes a file's card before the file is decoded; without it the card starts at 16:9 and takes the picture's aspect on the first upload. For a placeholder, `aspect` shapes the canvas (default 1.6); the defaults include one portrait (0.75) and one square picture.
- The cards are `ShaderMaterial` planes. Per frame the page sets `u.uBright`, `u.uSpot`, `u.uSweep`, `u.uGlow` and `u.uFade`; `G.update(camera)` before the render uploads pictures and moves the mirrored cards.
- The background cards in `float` are placed by the seeded generator, out of the camera's path and the lines of sight to the heroes.
- Depth blur focuses on the active hero (`Kit.tiltShift`, `tilt` 0, `dof` 0.5).
- A card that should vanish is hidden with `visible = false` or shrunk to zero scale, never left at opacity 0: under the tilt-shift pass a transparent mesh that still writes depth cuts a sharp rectangle into the blur. Glow sprites that cross the floor have `depthTest` false.

## Camera and timing

- The final camera move always ends at D - 0.5 s, and the last 0.5 s hold. It starts at the last item time (museum: 0.6 s after it), so its speed depends on the gap: a last item within 0.5 s of D - 0.5 s leaves the move almost no time, and a long gap slows it; the motion check (frames 2 s apart) decides whether it still reads as movement.
- `float`: one camera key per hero time in `FLOAT_T` (1 s apart here, 6.8 units apart along -z, alternating sides), distance 6.1, pitch 2 to 5 degrees, yaw ±7. Ease `0.22 u + 0.78 cubicInOut(u)` keeps the camera moving between keys. After the last hero (7 s here) the camera pushes in to D - 0.5 s: distance 6.1 minus 0.6 + 0.5 s per second of gap (at most 2.6), with the yaw drifting across the card on gaps over 0.5 s.
- `museum`: canvases 4.6 units apart at height 2.15; one key per time in `MUSEUM_T` (0.9 s apart here) at distance 9 and yaw 32 to 17 degrees. The camera drifts on the last canvas for 0.6 s, then pulls back to D - 0.5 s, to the distance at which the row plus a 12% margin fills the horizontal field of view (`(width / 2) * 1.12 / tan(hfov / 2)`, about 27 units for six canvases). The caption leaves when the pull back starts.
- `vortex`: heroes up to `TV` (4.6 s); the rush lasts `DV` (2.0 s), each card with a seeded delay up to 0.45 s, spiralling toward a point 22 units ahead of the camera, which rolls up to 22 degrees and back. The point flares at 6.6 s; the end word enters 0.05 s later.
- Replace the literal times with `W(n, "word")` of the words that name each picture, or with `S(n)` for one picture per sentence.

## What to vary

- The palette: the `:root` variables. `--accent-1` to `--accent-4` are the card edge lights in turn, `--spot` the spot lights and dust, `--sweep` the light sweep across a card.
- `PICTURES`, its titles, aspects and the item times. The `float` hero count follows `FLOAT_T`; the `museum` row length follows `MUSEUM_T`, and the pull back distance follows the row.
- Card width (`w` in `G.card`) and spacing; the number of background cards (110 here).
- A light palette: set `floor: null` in `Kit.gallery` to drop the floor and its mirror, and turn the dust and glows down; additive glows vanish on a light background.
- The end of `vortex`: replace `#end` with the film's title, or cut to the next scene on the flare.
