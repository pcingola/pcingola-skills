# aerial_routes

An aerial view of a city or map where routes draw from one place to another, with pinned labels and counters.

## When to use

- Movement between places: commutes, supply routes, migrations, network traffic drawn on a map.
- A scene that names two or three places and a flow between them.

## Build

- three.js 0.159.0 with `kit/camera.js`, `kit/ribbon.js`, `kit/glow.js`, `kit/labels3d.js`, `kit/shadow.js`, `kit/tiltshift.js`.
- One GSAP tween of a clock `{t}` over the scene length calls `draw(t)`: camera pose, ribbon heads, rider glows, pulses, label positions, render. `draw(0)` runs at load for frame 0.
- The city is instanced boxes on a street grid of pitch `P`, placed by a seeded generator. Routes run on street centre lines with `Kit.roundCorners`.
- Labels are HTML in `#anchored`, placed each frame with `Kit.anchor` (anchor `[0.5, 1]`, the leader's foot on the point).

## Camera and timing

- `Kit.camera.path`: high and nearly top-down (pitch 74, d 24) at 0 s, tilting to pitch 54 by 4.5 s and 47 by the end, with a 16 degree yaw and a push to d 15.5. Both segments `sineInOut`.
- The target stays between the start and end stations, so both stay in frame for the whole move.
- Title 0.3 to 0.9 s, out at 4.0 s. Labels at 1.0 and 1.4 s. Routes start 1.6 s, 0.45 s apart, 3.2 s each. The counter falls over the same 5 s.
- Tilt-shift band `[0.3, 0.72]` of the frame height; the top and bottom blur.

## What to vary

- Palette and font: the `:root` variables. The page reads them into three.js colours with `getComputedStyle`.
- Grid pitch, block heights (taller near the centre), parks share, `seed`.
- Route polylines, their widths, start times and duration; a route per mover.
- Camera keys: fit a station to a frame position with `Kit.camera.fit` when the Brief names one.
- Night: a dark `--bg` and `--ground`; additive glows read on dark ground only.

