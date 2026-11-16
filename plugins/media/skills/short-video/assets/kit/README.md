# Kit

Classic scripts for three.js 0.159.0 (global `THREE`). Load them with `<script src>` after `three.min.js`; they work from `file://`. Each adds functions to `window.Kit`. They set no colours, fonts or layout of their own. Functions of time take the scene time `t` as an argument.

- `camera.js`: `Kit.camera.pose(camera, {tx, ty, tz, d, pitch, yaw, fov})`, `Kit.camera.path(keys)` returning `{at(t), apply(camera, t), keys}` with keys `{t, ...fields, ease}`, `Kit.camera.fit(camera, state, params, goals[[x, y, z, fx, fy]], iterations)`, `Kit.ease.<name>(u)`.
- `labels3d.js`: `Kit.project(camera, point, width, height)` returning `{x, y, behind}`, `Kit.anchor(el, camera, point, {width, height, anchor, offset, hideBehind})`.
- `glow.js`: `Kit.glowTexture(size)`, `Kit.glow({color, size, opacity, position})`, `Kit.glowPoints(positions, {color, size, opacity})`, `Kit.pulse(t, period, lo, hi, phase)`.
- `shadow.js`: `Kit.lights(scene, renderer, {sky, ground, fill, sun, intensity, elevation, azimuth, target, extent, mapSize, radius, bias, normalBias})` returning `{hemi, sun, aim(target, extent, elevation, azimuth)}`, `Kit.shadows(obj, cast, receive)`, `Kit.shadowCatcher({size, opacity, color, y})`.
- `ribbon.js`: `Kit.roundCorners(pts, radius, step)`, `Kit.pathSampler(pts)` returning `{length, at(s)}`, `Kit.ribbonGeometry(pts, width, y)`, `Kit.ribbon(pts, {width, y, color, opacity, feather, order, progress})`, `Kit.ribbonProgress(mesh, head, tail)`. A ribbon is a `ShaderMaterial`: its opacity after creation is `mesh.material.uniforms.uOpacity.value` (and its colour `uColor.value`); `mesh.material.opacity` has no effect.
- `tiltshift.js`: `Kit.tiltShift(renderer, {width, height, samples, tilt, band, edge, dof, focus, range, vignette, dither})` returning `{render(scene, camera, target), set(opts), setSize(w, h), dispose(), uniforms}`.

Each file's header comment states the defaults and conventions: pitch in degrees above the horizon, yaw 0 looking toward -z, path points as `[x, z]` on the ground plane, frame fractions from the top left.
