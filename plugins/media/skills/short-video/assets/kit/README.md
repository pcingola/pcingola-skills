# Kit

Classic scripts; all except `beat.js` (GSAP only, "Beat cuts" below) need three.js 0.159.0 (global `THREE`). Load them with `<script src>` after `three.min.js` (or `gsap.min.js`); they work from `file://`. Each adds functions to `window.Kit`. They set no colours, fonts or layout of their own. Functions of time take the scene time `t` as an argument.

- `camera.js`: `Kit.camera.pose(camera, {tx, ty, tz, d, pitch, yaw, fov})`, `Kit.camera.path(keys)` returning `{at(t), apply(camera, t), keys}` with keys `{t, ...fields, ease}`, `Kit.camera.fit(camera, state, params, goals[[x, y, z, fx, fy]], iterations)`, `Kit.ease.<name>(u)`.
- `labels3d.js`: `Kit.project(camera, point, width, height)` returning `{x, y, behind}`, `Kit.anchor(el, camera, point, {width, height, anchor, offset, hideBehind})`.
- `glow.js`: `Kit.glowTexture(size)`, `Kit.glow({color, size, opacity, position})`, `Kit.glowPoints(positions, {color, size, opacity})`, `Kit.pulse(t, period, lo, hi, phase)`.
- `shadow.js`: `Kit.lights(scene, renderer, {sky, ground, fill, sun, intensity, elevation, azimuth, target, extent, mapSize, radius, bias, normalBias})` returning `{hemi, sun, aim(target, extent, elevation, azimuth)}`, `Kit.shadows(obj, cast, receive)`, `Kit.shadowCatcher({size, opacity, color, y})`.
- `ribbon.js`: `Kit.roundCorners(pts, radius, step)`, `Kit.pathSampler(pts)` returning `{length, at(s)}`, `Kit.ribbonGeometry(pts, width, y)`, `Kit.ribbon(pts, {width, y, color, opacity, feather, order, progress})`, `Kit.ribbonProgress(mesh, head, tail)`. A ribbon is a `ShaderMaterial`: its opacity after creation is `mesh.material.uniforms.uOpacity.value` (and its colour `uColor.value`); `mesh.material.opacity` has no effect.
- `tiltshift.js`: `Kit.tiltShift(renderer, {width, height, samples, tilt, band, edge, dof, focus, range, vignette, dither})` returning `{render(scene, camera, target), set(opts), setSize(w, h), dispose(), uniforms}`.

Each file's header comment states the defaults and conventions: pitch in degrees above the horizon, yaw 0 looking toward -z, path points as `[x, z]` on the ground plane, frame fractions from the top left.

## Beat cuts (`beat.js`)

A classic script for GSAP 3 (global `gsap`), without three.js; it adds `Kit.beat`. Each effect adds tweens to the page's paused timeline `tl` at time `t`, or returns an `update(t)` for the page's clock tween. Defaults: 1920x1080 frame, 30 fps, 120 bpm, white flash, red, green and blue slice strips, near-black wipe bars with white edges, white particles. It sets no fonts or word colours. An element argument also takes a CSS selector. The technique `beat_reel` uses every function.

- `Kit.beat.rand(seed)`: seeded generator in [0, 1).
- `Kit.beat.grid(bpm, {offset, perBar})` returning `{bpm, beat, bar, at(n), bars(n), index(t), snap(t), list(t0, t1, every)}`: beat `n` at `offset + n * 60 / bpm`.
- `Kit.beat.particles(parent, {n, regions, width, height, seed, colors, size, drift, rise, alpha, twinkle, fade, glow})` returning `update(t)`: glow dots drifting upward inside `regions` (`[{x, y, w, h}]`), wrapping and fading at the region edges.
- `Kit.beat.flash(tl, layer, t, {peak, hold, second, decay, rise, fps, ease})`: the layer jumps to `peak` at `t` (or ramps over `rise` before it), drops to `peak * second` one frame later, then decays to 0. A layer without a background turns white.
- `Kit.beat.slice(tl, layer, t, {seed, colors, offsets, spread, heights, gaps, density, height, fps, target, jolt, filter})`: horizontal strips offset sideways on one frame per entry of `offsets`, centred on `t`; `target` (the footage) is shifted and filtered on the same frames. Returns the end time.
- `Kit.beat.wipe(tl, layer, t, {bars, width, skew, fill, edge, edges, edgeWidth, duration, stagger, lead, dir, frameWidth, height, ease})`: skewed bars sweep across the frame and cover its centre at `t`; hidden outside their sweep. Returns the bars.
- `Kit.beat.stamp(tl, word, t, {until, from, dur, ease, shake, grow, exit, exitScale, blur, origin, keep})`: a word scales from `from` to 1 landing on `t`, shakes, grows slowly and leaves with a blur by `until` (`keep`: holds to `until`). At `t` within `dur` of 0 it is on screen from frame 0. Opacity 0 outside its window.
- `Kit.beat.rise(tl, caption, t, {until, lines, dur, stagger, ease, rotate, exit, exitStagger, drift, keep})`: the caption's `lines` (each the child of an `overflow: hidden` mask) rise in at `t` and leave upward by `until`; the caption has opacity 0 outside its window, since a text shadow bleeds out of a mask box.

## Pipelines (`pipeline.js`)

A classic script for three.js 0.159.0 that adds `Kit.pipeline`; it needs `glow.js` loaded first. It draws stations, connectors and particle flows for a process line or a hub with nodes. Defaults are neutral (white accents, grey-blue objects, near-black platforms); the page passes its palette. Positions are `[x, y, z]` with y up. A level is 0 (unlit) to 1 (lit), above 1 for a flash. The technique `pipeline_3d` uses every function.

- `Kit.pipeline.line(n, {spacing, center})`: n positions along +x, centred, `spacing` (6) apart.
- `Kit.pipeline.hub(n, {radius, center, spread, facing})`: n positions on an arc of `radius` (7) around `center`, spanning `spread` degrees centred on `facing` (0 is toward -z), ends on the arc ends; `spread` 360 (the default) spaces them evenly with the first at `facing`.
- `Kit.pipeline.station({kind, color, body, base, size, position, light})` returning `{group, obj, mat, rim, pool, halo, light, set(level)}`: a platform with a rim, a floor pool, a halo, a point light (peak intensity `light`, 12; 0 for none) and a placeholder object `obj` of kind `box`, `cylinder`, `ring` or `stack`; `set(level)` lights all of them.
- `Kit.pipeline.level(t, tOn, {base, rise, flash, flashWidth})`: `base` (0.2) before `tOn`, rising to 1 over `rise` (0.5) s, plus a flash of `flash` (0.6) at `tOn + 0.3`.
- `Kit.pipeline.curve(a, b, {lift, arc, via})`: a `THREE.Curve` from a to b raised `arc` at its middle and `lift` at both ends, or a Catmull-Rom curve through the `via` points.
- `Kit.pipeline.connector(curve, {color, radius, halo, opacity, segments, solid})` returning `{group, curve, progress(head, tail, gain)}`: an additive tube with a halo tube, drawn between the curve fractions `tail` and `head`; `solid: true` blends normally, for a light ground.
- `Kit.pipeline.flow(curve, {count, speed, spread, size, color, head, seed, solid})` returning `{group, curve, points, headGlow, update(t, t0, {reach, gain, stop})}`: particles that leave the start from `t0` at `speed` (0.5) curve lengths per second, with a head glow on the front; `stop` ends the stream and the last particles run out. `solid: true` blends normally in full colour with no head glow, for a light ground.
- `Kit.pipeline.lin(t, a, b)`, `Kit.pipeline.smooth(u)`, `Kit.pipeline.bump(t, c, w)`, `Kit.pipeline.clamp(v, a, b)`, `Kit.pipeline.rng(seed)`: the ramps and the seeded generator these use.

## Gallery (`gallery.js`)

A classic script for three.js 0.159.0 that adds `Kit.gallery`; it needs `glow.js` loaded first. It draws framed picture cards in a dark space, an optional glossy floor that mirrors them, spot lights from above and dust motes. Defaults are neutral greys; the page passes its palette. Pictures are canvases, `<img>` elements or their ids; an `<img>` is drawn into a canvas before upload, because a texture made from an `<img>` renders black in the render browser. The technique `gallery_3d` uses every function.

- `Kit.gallery(renderer, scene, {fog, fogNear, fogFar, skyTop, floor, seam, tile, floorSize, floorZ, reflect, reflectFall, frame, back, sweep})` returning `{card, spot, dust, picture, update(camera), cards, sky, floor, fog}`. `skyTop: null` drops the sky sphere; `floor: null` drops the floor and the mirrored cards.
- `card({picture, w, h, aspect, b, edge, glow, bright, reflect, pos, yaw})` returning `{group, u, w, h, reflect}`: a card facing +z with a frame of width `b` and an edge light of colour `edge`. The picture keeps its aspect inside `w` x `h` (largest width and height; without `h` it is `w` wide). An `<img>` card created before decode without `aspect` starts at 16:9 and is resized (geometry, `u.uSize`, `w`, `h`) on its first upload; pass `aspect` to size it at once. Per frame the page moves `group` and sets `u.uBright`, `u.uSpot` (top light, 0 to 1), `u.uSweep` (light sweep position, -0.3 before the card to 1.4 past it), `u.uGlow` (edge light) and `u.uFade` (0 fog colour to 1 shown).
- `spot({x, z, color, height, radius, poolR, poolI, poolColor})` returning `{cone, lamp, set(I)}`: a visible cone, a lamp glow and a light pool on the floor (at most 16 pools); `set(I)` sets the intensity, 0 hides it.
- `dust(centers[[x, z, r]], per, {seed, color, size, height})` returning `{points, update(t)}`: seeded motes rising through the beams.
- `picture(src)`: the texture of a canvas, an `<img>` or an id, one per source.
- `update(camera)`: called once per frame before rendering; uploads decoded pictures, centres the sky on the camera and moves the mirrored cards with their cards.

## Particles (`particles.js`)

A classic script for three.js 0.159.0 that adds `Kit.particles`; it needs no other kit file. It draws particle text: glowing point clouds, a gradient sky, a star field, glow sprites and a glyph plane that reveals letters at their lock times. Colours are arguments with neutral defaults (white, greys); the page reads its palette from CSS variables with `css` and passes it. The frame size is `data-width` and `data-height` of `#root`. A word is two files that `short-video.sh particle-text` writes from a font file: `<name>_targets.js` (sets `window.PT_TARGETS[name]`) and `<name>_tex.png` (R fill, G glow, B letter index as (k + 1) * 8, at most 31 letters). The technique `particle_text` uses every function.

- `Kit.particles.targets(name)` returning `{n, x, y, li, w, h, em, ink, letters, lines, lc, ly, camera}`: the points (world units, centred on the text box, y up) with their letter index, the box, font and ink size, the letter centres and the camera (`{width, height, fov, distance, end}`) at which the text measures its `--size` in pixels; `end` is the page's final distance as a share of `distance`. It throws when the camera's frame differs from `#root`'s `data-width` and `data-height`.
- `Kit.particles.stage({fov, near, far, clear, sky, container, width, height})` returning `{renderer, scene, camera, sky, width, height, pxScale}`: a renderer at pixel ratio 1 with `preserveDrawingBuffer`, its canvas in `#gl` (or `#container`), a perspective camera and a sky (`sky: false` for none).
- `Kit.particles.pose(camera, {tx, ty, tz, d, yaw, pitch, roll})`: an orbit pose in degrees, yaw 0 looking toward -z.
- `Kit.particles.sky({top, bottom, blobs})` returning `{mesh, uniforms}`: a vertical gradient sphere with up to three blobs `{dir, col, amp, w}`.
- `Kit.particles.cloud(n, stage, {core, maxPx, depthTest, renderOrder})` returning `{pos, col, size, alpha, points, flush()}`: n additive points; the page fills the arrays from `t` and calls `flush()`. Points larger than 26 px turn into soft bokeh.
- `Kit.particles.glyphPlane(stage, imgId, w, h, {top, bottom, glow, sweepCol, sweepW, reveal, revealDur, mirror})` returning `{mesh, u, tex}`: the glyph texture on a w x h plane. Per frame the page calls `tex.poll()` and sets `u.uT` (scene time), `u.uOpacity`, `u.uFill`, `u.uGlow`, `u.uSweep` (sweep centre across the plane, -1 off) and `u.uSweepAmt`; `u.uLock.value[k]` is the time letter k appears.
- `Kit.particles.imgTexture(imgId, onReady, srgb)` returning `{ready, texture, poll()}`: a texture made through a canvas once the `<img>` is decoded. A texture uploaded empty first fails later ("Offset overflows texture dimensions"), and one made from the `<img>` renders black in the render browser.
- `Kit.particles.glow(stage, color, kind)` returning `{mesh, mat}`: an additive sprite without depth test, kind `dot`, `ring` or `streak`; `Kit.particles.spriteTexture(kind)` is its cached texture.
- `Kit.particles.stars(stage, n, seed, colors)` returning a cloud with `update(t)`: a twinkling field on a far shell behind the scene.
- `Kit.particles.pin(el, camera, point, ref, extra, maxWidth)`: an absolutely positioned DOM element centred on the projected point, `extra` px lower, scaled by `ref` / camera distance and at most to `maxWidth` px wide.
- `Kit.particles.prime(renderer, scene, camera, draw, time)`: `renderer.compile` and two draws at `time()`, now and again at the load event; without it frame 0 of a render can come out without particles.
- `Kit.particles.rng(seed)`, `clamp`, `lin(t, a, b)`, `mix`, `smooth`, `sineIO`, `cubicIO`, `outCubic`, `outExpo`, `inQuad`, `col(css)` returning `[r, g, b]`, `css(name, fallback)`: the seeded generator, ramps, eases and colour helpers these use.
