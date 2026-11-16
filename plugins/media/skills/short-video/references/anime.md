# anime.js scenes

anime.js 4.5.0, MIT licence, `anime.umd.min.js` (118 KB minified), global `anime`. This file states what differs
from a GSAP scene; everything else in `scenes.md` applies.

## The page

- Replace `<script src="gsap.min.js">` with `<script src="anime.umd.min.js">`. `scaffold` copies every library
  file a `<script src>` of the page names.
- Add `data-no-timeline` to `#root` and keep its other attributes as `scaffold` wrote them.
- Register nothing in `window.__timelines`. HyperFrames dispatches `hf-seek` on `window` for each frame, with
  `e.detail.time` in seconds, and the page seeks its own timeline in that listener.

## Timeline

```js
const ms = s => s * 1000;                       // timing.js returns seconds; anime.js counts milliseconds
const tl = anime.createTimeline({ autoplay: false, onRender: draw });
tl.add("#title", { opacity: { from: 0 }, translateY: { from: 60 }, duration: 800, ease: "outCubic" }, ms(S(1)));
tl.add("#anchored", { scale: [1, 1.3], duration: ms(SE(2) - S(2)), ease: "inOutSine" }, ms(S(2)));
```

- `tl.add(target, params, position)`: target is a selector, an element, an array or a plain object; position is
  absolute milliseconds. Every duration and position is in milliseconds.
- Values: `{ from: v }` animates from `v` to the value the element has; `[from, to]` gives both ends.
- Transforms: `translateX`, `translateY`, `scale`, `rotate`. SVG attributes by name (`y`, `height`, `fill`,
  `strokeDashoffset`).
- Eases: `linear`, `outQuad`, `outCubic`, `inOutSine`, `inOutQuad`. Stagger with `anime.stagger(ms)`.
- A line that draws: set `stroke-dasharray` to `getTotalLength()`, then
  `tl.add(path, { strokeDashoffset: [len, 0], duration: ..., ease: "outQuad" }, ...)`.
- d3 draws the finished chart (scales, data join, attributes, an id on every created element); the timeline
  animates it. No d3 transitions.

## Seek

```js
const ZERO = 1e-3;
tl.seek(tl.duration);
tl.seek(ZERO);
window.addEventListener("hf-seek", e => tl.seek(Math.max(ms(e.detail.time), ZERO)));
```

- A child renders its start state only when the playhead passes it backwards. Seeking to the end and back at load
  puts every element in its state at time 0.
- At time 0 exactly anime.js fires no `onRender` or `onUpdate`, so every seek stops 1 microsecond after 0.

## Update callback

Text, counters and three.js draw in `onRender` of the timeline. `onUpdate` of a timeline runs before its children
update, so it draws the values of the previous seek. A callback on a single tween misses the frames before that
tween starts. A count-up tweens a plain object and writes the text in `onRender`:

```js
const n = { v: 0 };
tl.add(n, { v: 4200, duration: ms(SE(1) - S(1)), ease: "outQuad" }, ms(S(1)));
// in draw(): document.getElementById("count").textContent = Math.round(n.v).toLocaleString("en-US");
```

## three.js

three.js 0.159.0 is the classic `three.min.js` (global `THREE`). The addons (OrbitControls, loaders,
EffectComposer, bloom) are ES modules and do not load: glow is additive sprites, blur is hand-written passes in
core three.js. There is no render loop (`requestAnimationFrame`, `setAnimationLoop`, `THREE.Clock`): the camera,
lights and objects are functions of a state object the timeline tweens, and `draw` renders once per seek.

```js
const FW = 1920, FH = 1080;                                   // the frame size
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(1);
renderer.setSize(FW, FH);
renderer.setClearColor(0x0b1320);                           // the canvas is opaque and covers #bg-fill
renderer.domElement.id = "gl-canvas";
document.getElementById("gl").appendChild(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40, FW / FH, 0.1, 100);
const state = { angle: -0.7 };                              // the values the timeline tweens
tl.add(state, { angle: 0.7, duration: ms(SE(2)), ease: "linear" }, 0);
```

- Ribbons and other flat strips are invisible when their triangles face away from the camera: use
  `side: THREE.DoubleSide`.
- Coplanar layers z-fight: separate them in height (0.012 units sufficed on a 0.004 plate).
- A depth blur focused at the camera target blurs the subject; set the focus to the subject's distance.
- HyperFrames renders WebGL on the GPU; shadows and high polygon counts slow the render.

## Determinism

`anime.utils.random` and `anime.utils.shuffle` call `Math.random`, as do `d3.random*`, `d3.shuffle` and
`THREE.MathUtils.rand*`. Use a seeded generator for values that look random.

## Skeleton

A drawn scene with a title, a counter, a camera push and a three.js orbit. A 640x360 copy renders with
HyperFrames 0.8.143 with every element in its expected state from frame 0.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<script src="anime.umd.min.js"></script>
<script src="three.min.js"></script>
<script src="timing.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { width: 1920px; height: 1080px; overflow: hidden; background: #0b1320; }
  #root { position: relative; width: 1920px; height: 1080px; overflow: hidden; font-family: Inter, Arial, sans-serif; color: #fff; }
  .bg { position: absolute; inset: 0; width: 100%; height: 100%; }
  #bg-fill { background: #0b1320; }
  #title { position: absolute; left: 160px; top: 120px; font-size: 96px; }
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
  const ms = s => s * 1000, FW = 1920, FH = 1080;
  const D = Number(document.getElementById("root").dataset.duration);
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(1); renderer.setSize(FW, FH); renderer.setClearColor(0x0b1320);
  renderer.domElement.id = "gl-canvas";
  document.getElementById("gl").appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, FW / FH, 0.1, 100);
  scene.add(new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), new THREE.MeshNormalMaterial()));
  const state = { angle: 0 }, n = { v: 0 };
  function draw() {
    camera.position.set(Math.sin(state.angle) * 8, 3, Math.cos(state.angle) * 8);
    camera.lookAt(0, 0, 0);
    renderer.render(scene, camera);
    document.getElementById("count").textContent = Math.round(n.v).toLocaleString("en-US");
  }
  const tl = anime.createTimeline({ autoplay: false, onRender: draw });
  tl.add(state, { angle: 3, duration: ms(D), ease: "linear" }, 0)
    .add("#title", { opacity: { from: 0 }, translateY: { from: 60 }, duration: 800, ease: "outCubic" }, ms(S(1)))
    .add(n, { v: 4200, duration: ms(SE(1) - S(1)), ease: "outQuad" }, ms(S(1)))
    .add("#anchored", { scale: [1, 1.3], duration: ms(SE(2) - S(2)), ease: "inOutSine" }, ms(S(2)));
  const ZERO = 1e-3;
  tl.seek(tl.duration); tl.seek(ZERO);
  window.addEventListener("hf-seek", e => tl.seek(Math.max(ms(e.detail.time), ZERO)));
</script>
</body>
</html>
```
