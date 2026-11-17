# pipeline_3d

A process as a line of glowing stations on a floor: each station lights on its word, the camera travels from station to station, and a stream of particles flows along a connector to the next. `LAYOUT = "hub"` draws one source in the middle with flows to N nodes on an arc instead.

## When to use

- The narration names the steps of a process in order (a pipeline, a workflow, a supply chain): line layout.
- One thing feeds several (a service to its clients, a model to its tasks, a source to its outputs): hub layout.

## Build

- three.js 0.159.0 with `kit/camera.js`, `kit/glow.js`, `kit/labels3d.js`, `kit/shadow.js`, `kit/tiltshift.js` and `kit/pipeline.js`.
- `STATIONS` (line) and `SOURCE` plus `NODES` (hub) at the top: label, placeholder kind (`box`, `cylinder`, `ring`, `stack`) and time. The page builds each with `Kit.pipeline.station`, places them with `Kit.pipeline.line` or `Kit.pipeline.hub`, and joins them with `Kit.pipeline.curve`, `Kit.pipeline.connector` and `Kit.pipeline.flow`.
- The scene length `D` is read from `#root` `data-duration`; the camera keys follow from `D`, the station times and the station count.
- One GSAP clock tween drives `draw(t)`: camera, station levels (`Kit.pipeline.level`), object turn and pop, connector draw-on, particles, labels. The title is an ordinary GSAP tween on the same timeline.
- Labels are HTML in `#labels` inside `#anchored`, pinned above each station with `Kit.anchor` (anchor `[0.5, 1]`) and faded in as the station lights.
- `buildWorld(WORLD)` is the replaceable backdrop: a floor with a grid and drifting dust, plus far soft glows (`"plain"`, the default) or seeded low blocks with glowing tops (`"blocks"`). It keeps clear of the stations and returns `update(t)`. A film's own world (a city, a lab, a harbour) replaces this one function.

## Camera and timing

- Line: starts close beside the first station (d 12, pitch 20, yaw -24); one key 0.35 s after each station time on that station (d 11, pitch 16, yaw alternating plus and minus 8).
- Line pull back at `T_ALL` + 0.9 s (no later than `D` - 1.6 s and at least 0.8 s after the last station key): the distance makes the line plus 7 units of margin fill 70% of the frame width at the horizontal field of view, so 3 or 7 stations fit alike. From there to `D` - 0.5 s the camera swings from yaw -18 to 18 and dollies 3% of the width along the line.
- Line times: stations at 1.0, 2.3, 3.6, 4.9 and 6.2 s; each connector and flow starts 0.15 s after its station and reaches the next in 1 / `FLOW_SPEED` s (1.25 s); at `T_ALL` (7.2 s) the stations flash in turn, 0.22 s apart. Title 0.2 to 2.5 s.
- Hub: the arc spans 90 + 15 n degrees (at most 180, away from the camera), and the radius grows so neighbouring nodes stay `HUB_GAP` (7) units apart (8.5 at least). Camera distances scale with the radius: a high view (d 29, pitch 50), a lean toward each node as its flow arrives (d 25, pitch 42), and a swing to yaw 44 (d 31, pitch 55) at `D` - 0.5 s.
- Station spacing (7 units) and the station times set the camera speed: gaps under about 0.9 s make the camera whip from one station to the next.

## Keying to the narration

- Replace each station's `t` with `W(n, "word")`, the word that names it: `{ label: "Step 2", kind: "stack", t: W(1, "parse") }`. The station lights and the camera arrives on that word.
- In the line layout the flow to the next station leaves on that word and arrives 1 / `FLOW_SPEED` s later. If the next word comes sooner, raise `FLOW_SPEED` to 1 / (gap) so the flow lands as the next station lights.
- In the hub layout set each node's `t` to the word minus 1 / `FLOW_SPEED` so the node lights on its word, or to the word itself so the flow leaves on it.
- `T_ALL` is the word of the summary ("all", "every"). `TITLE_IN` and `TITLE_OUT` go to `S(1)` and the first station's word.
- In a world, use `ST("id")` and `STE("id")` in place of the scene times.

## What to vary

- Colours, all `:root` variables read into three.js with `getComputedStyle`:
  - `--bg`: clear colour, sky and fog. `--ground`: floor. `--grid`: floor grid lines.
  - `--accent-1` to `--accent-5`: each station's rim, floor pool, halo, emissive object, point light and label border, in order (more stations reuse them); in the hub, also each node's particles.
  - `--body`: station objects. `--base`: platforms and the blocks backdrop.
  - `--connector`: the tubes between stations. `--flow`: the particles of the line.
  - `--dust`: floating dust. `--bokeh`: far glows of the plain backdrop. `--beacon`: glows on the blocks backdrop.
  - `--light-sky`, `--light-ground`: hemisphere light. `--light-sun`: the shadow-casting key light.
  - `--text`, `--muted`, `--label-bg`: title and labels. `--font`, `--font-kicker`: fonts.
- A light ground: the halos, floor pools, connectors, particles, dust and far glows are additive and almost vanish on a light floor. On a light palette pass `solid: true` to `Kit.pipeline.connector` and `Kit.pipeline.flow` (normal blending, particles in full colour, larger `size` around 0.45) and give the accents enough contrast with `--ground`; the station reads by its rim and lit object. On a dark one, keep the glows.
- Station kinds: replace a placeholder by building any object into `station.obj` (a group on the platform) and keep `station.set(level)` for the light.
- Labels: `makeLabel` writes one name; add a second line (a file name, a count) inside `.box`.
- Flow look: `count`, `size`, `spread` and `speed` of `Kit.pipeline.flow`; `arc` of `Kit.pipeline.curve` (0.5 on the line, 1.6 on the hub); `opts.stop` ends a stream with its last particles running out.
- A step-by-step mode: give each flow a `stop` time and a later restart (a second `Kit.pipeline.flow` on the same curve).
