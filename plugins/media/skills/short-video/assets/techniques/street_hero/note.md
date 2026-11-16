# street_hero

One object at street level, seen from eye height, with soft shadows and depth blur on the street behind.

## When to use

- The scene is about one thing in one place: an empty dock, a device, a sign, a product on a pavement.
- A close view after an aerial one, for the moment the narration lands on a single place.

## Build

- three.js 0.159.0 with `kit/camera.js`, `kit/glow.js`, `kit/labels3d.js`, `kit/shadow.js`, `kit/tiltshift.js`.
- `Kit.lights` gives a hemisphere fill and one sun with PCF soft shadows (`radius` 6, `extent` 5 around the hero). The sun sits on the camera's side (azimuth 35, elevation 34) so the hero's front is lit and its shadows fall back and left.
- The hero is a `THREE.Group` of Lambert meshes; `Kit.shadows` sets cast and receive. Glow sprites do not cast shadows.
- `Kit.tiltShift` with `tilt` 0 and `dof` 0.9: focus follows the camera's distance to the hero each frame, so only the background blurs.
- A card pinned to a 3D point beside the hero with `Kit.anchor` (anchor `[1, 1]`).

## Camera and timing

- Pitch 7 to 4.5 degrees, target height 0.7 (eye height on this scale), about 30 degrees off the object's main axis: seen along the axis, a row of parts overlaps into one column.
- One slow push, d 8.2 to 6.0, with the yaw drifting 32 to 22 degrees over the whole length (`sineInOut`). The drift keeps the hold from reading as a still.
- Card in at 0.8 s; the bands pulse with a 1.5 s period, staggered 0.08 s per bollard.

## What to vary

- Palette: the `:root` variables. `--hero` and `--hero-trim` are the object, `--accent` its glowing parts.
- The hero geometry; keep it near the origin, about 5 units wide, or change `extent` and the camera distance with it.
- The street: building heights, road position, fog distances.
- A swoop in from above: add a first key at pitch 60 and d 14, and land on the low keys by about 2 s.
