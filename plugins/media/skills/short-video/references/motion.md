# Motion scenes

Motion 14.14.0, MIT licence, `motion.js` (192 KB minified), global `Motion`. This file states what differs from
a GSAP scene; everything else in `scenes.md` applies.

## The page

- Replace `<script src="gsap.min.js">` with `<script src="motion.js">`. `scaffold` copies every library file a
  `<script src>` of the page names.
- Add `data-no-timeline` to `#root` and keep its other attributes as `scaffold` wrote them.
- Register nothing in `window.__timelines`. HyperFrames dispatches `hf-seek` on `window` for each frame, with
  `e.detail.time` in seconds, and the page seeks its own animation in that listener.

## Timeline

One `Motion.animate(sequence)` call builds the scene. Each segment is `[target, keyframes, options]`; `at` places
it at absolute seconds, so the timing helpers go in unchanged.

```js
const D = Number(document.getElementById("root").dataset.duration);
const anim = Motion.animate([
  [clock, [0, D], { duration: D, ease: "linear", at: 0 }],
  ["#title", { opacity: [0, 1], y: [60, 0] }, { duration: 0.8, ease: "easeOut", at: S(1) }],
  ["#anchored", { scale: [1, 1.3] }, { duration: SE(2) - S(2), ease: "easeInOut", at: S(2) }]
]);
```

- Targets: a selector, an element, a plain object or a motion value. Keyframes are `[start, end]` arrays.
- Transforms: `x`, `y`, `scale`, `scaleX`, `scaleY`, `rotate`. Eases: `linear`, `easeIn`, `easeOut`,
  `easeInOut`, or a cubic bezier `[x1, y1, x2, y2]`.
- The sequence lasts until its last segment ends. A `clock` segment over the whole scene (`D`, read from the
  root, which `scaffold` keeps equal to the scene length) makes the animation span the scene.
- Give each element its start state in CSS too (`opacity: 0` on an element that fades in).
- A line that draws: `[path, { pathLength: [0, 1] }, { duration: 1, ease: "easeOut", at: S(2) }]`.
- SVG: `scale` on a `<g>` scales the group about its centre, so its children move. Give each child its own
  segment, with `transform-box: fill-box` and a `transform-origin` (`50% 100%` for a bar growing from its base).
  Animate `fill` as a style (`.style("fill", ...)` in d3), not as an attribute.
- d3 draws the finished chart (scales, data join, attributes, an id on every created element); the sequence
  animates it. No d3 transitions.

## Seek

```js
anim.pause();
anim.time = 0;
draw();
window.addEventListener("hf-seek", e => {
  anim.time = e.detail.time;
  e.detail.waitUntil(new Promise(r => Motion.frame.postRender(() => r())));
});
```

Motion writes the values of a seek in its next frame, one frame after `anim.time` is set. `waitUntil` holds the
capture until `frame.postRender` runs, after every value of that frame is written. `waitUntil` is called
synchronously inside the listener.

## Update callback

A sequence segment has no update callback. A count-up animates a motion value and writes the text in its
`change` handler, and the script writes the start value once:

```js
const n = Motion.motionValue(0);
const show = v => { document.getElementById("count").textContent = Math.round(v).toLocaleString("en-US"); };
n.on("change", show);
show(0);
// segment: [n, [0, 4200], { duration: SE(1) - S(1), ease: "easeOut", at: S(1) }]
```

## three.js

three.js 0.159.0 is the classic `three.min.js` (global `THREE`). The addons (OrbitControls, loaders,
EffectComposer, bloom) are ES modules and do not load: glow is additive sprites, blur is hand-written passes in
core three.js. There is no render loop (`requestAnimationFrame`, `setAnimationLoop`, `THREE.Clock`): the camera,
lights and objects are functions of a state object the sequence animates.

The `clock` motion value runs over the whole scene. Its `change` handler schedules the render in
`Motion.frame.postRender`, after every value of that frame is set. At time 0 the clock does not change, so the
script calls `draw()` once after `anim.time = 0`.

```js
const clock = Motion.motionValue(0);
clock.on("change", () => Motion.frame.postRender(draw));
// segments: [clock, [0, D], ...] and [state, { angle: [-0.7, 0.7] }, { duration: D, ease: "linear", at: 0 }]
```

- The renderer uses `setPixelRatio(1)` and the frame size. Its canvas is opaque and covers `#bg-fill`: set
  `setClearColor` to the film's background.
- Ribbons and other flat strips are invisible when their triangles face away from the camera: use
  `side: THREE.DoubleSide`.
- Coplanar layers z-fight: separate them in height (0.012 units sufficed on a 0.004 plate).
- A depth blur focused at the camera target blurs the subject; set the focus to the subject's distance.
- HyperFrames renders WebGL on the GPU; shadows and high polygon counts slow the render.

## Determinism

`d3.random*`, `d3.shuffle` and `THREE.MathUtils.rand*` call `Math.random`. Use a seeded generator for values
that look random.

## Skeleton

A drawn scene with a title, a counter, a camera push and a three.js orbit. A 640x360 copy renders with
HyperFrames 0.8.143 with every element in its expected state from frame 0.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<script src="motion.js"></script>
<script src="three.min.js"></script>
<script src="timing.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { width: 1920px; height: 1080px; overflow: hidden; background: #0b1320; }
  #root { position: relative; width: 1920px; height: 1080px; overflow: hidden; font-family: Inter, Arial, sans-serif; color: #fff; }
  .bg { position: absolute; inset: 0; width: 100%; height: 100%; }
  #bg-fill { background: #0b1320; }
  #title { position: absolute; left: 160px; top: 120px; font-size: 96px; opacity: 0; }
  #count { position: absolute; left: 160px; top: 860px; font-size: 96px; }
</style>
</head>
<body>
<div id="root" data-composition-id="s3" data-start="0" data-duration="6.2" data-full-length
     data-width="1920" data-height="1080" data-fps="30" data-no-timeline>
  <div id="bg-fill" class="clip bg" data-start="0" data-duration="6.2" data-full-length data-track-index="0"></div>
  <div id="anchored" class="bg"><div id="gl" class="bg"></div><div id="title">Title</div></div>
  <div id="count">0</div>
</div>
<script>
  const FW = 1920, FH = 1080, D = Number(document.getElementById("root").dataset.duration);
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(1); renderer.setSize(FW, FH); renderer.setClearColor(0x0b1320);
  renderer.domElement.id = "gl-canvas";
  document.getElementById("gl").appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, FW / FH, 0.1, 100);
  scene.add(new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), new THREE.MeshNormalMaterial()));
  const state = { angle: 0 };
  function draw() {
    camera.position.set(Math.sin(state.angle) * 8, 3, Math.cos(state.angle) * 8);
    camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
  }
  const clock = Motion.motionValue(0);
  clock.on("change", () => Motion.frame.postRender(draw));
  const n = Motion.motionValue(0);
  n.on("change", v => { document.getElementById("count").textContent = Math.round(v).toLocaleString("en-US"); });
  const anim = Motion.animate([
    [clock, [0, D], { duration: D, ease: "linear", at: 0 }],
    [state, { angle: [0, 3] }, { duration: D, ease: "linear", at: 0 }],
    ["#title", { opacity: [0, 1], y: [60, 0] }, { duration: 0.8, ease: "easeOut", at: S(1) }],
    [n, [0, 4200], { duration: SE(1) - S(1), ease: "easeOut", at: S(1) }],
    ["#anchored", { scale: [1, 1.3] }, { duration: SE(2) - S(2), ease: "easeInOut", at: S(2) }]
  ]);
  anim.pause();
  anim.time = 0;
  draw();
  window.addEventListener("hf-seek", e => {
    anim.time = e.detail.time;
    e.detail.waitUntil(new Promise(r => Motion.frame.postRender(() => r())));
  });
</script>
</body>
</html>
```
