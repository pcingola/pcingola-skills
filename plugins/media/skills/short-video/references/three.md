# three.js scenes

three.js 0.159.0 is `three.min.js` in the library files of `scenes.md` (global `THREE`). It is the last release
with a classic build; the addons (OrbitControls, loaders, EffectComposer, bloom) are ES modules and do not load.
The kit (`assets/kit/README.md`) covers what the addons would: camera paths, labels on 3D points, glow sprites,
lights and shadows, ribbons, and a tilt-shift or depth blur pass. Load `three.min.js` first, then each kit file
the page uses with `<script src="kit/<file>.js">`.

This file states the GSAP page and what every three.js scene shares. The update callback and the seek of an
anime.js or Motion page are in `references/anime.md` and `references/motion.md`, with their pitfalls (double
sided ribbons, z-fighting, depth blur focus), which apply on GSAP too.

## Drawing from the seek

There is no render loop. One function `draw(t)` sets every object, the camera and the HTML labels from the scene
time `t` and renders once. A seek to any `t` draws the exact frame, in any order of seeks.

```js
const FW = 1920, FH = 1080, D = Number(document.getElementById("root").dataset.duration);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(1);
renderer.setSize(FW, FH);
renderer.setClearColor(0x0b1320);                 // the film's background: the canvas is opaque over #bg-fill
renderer.domElement.id = "gl-canvas";
document.getElementById("gl").appendChild(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40, FW / FH, 0.1, 200);
const cam = Kit.camera.path([                       // one key per sentence, keyed to the timing helpers
  { t: 0,    tx: 0, tz: 0, d: 18, pitch: 55, yaw: 0 },
  { t: S(2), tx: 3, tz: -2, d: 11, pitch: 45, yaw: 20, ease: "sineInOut" },
  { t: SE(2), tx: 3, tz: -2, d: 9, pitch: 40, yaw: 30, ease: "sineInOut" },
]);
function draw(t) {
  cam.apply(camera, t);
  // object transforms, ribbon progress, glow pulses from t
  Kit.anchor(document.getElementById("lbl-a"), camera, [2, 0.1, -1], { width: FW, height: FH, anchor: [0.5, 1] });
  renderer.render(scene, camera);
}

const tl = gsap.timeline({ paused: true });
const clock = { t: 0 };
tl.to(clock, { t: D, duration: D, ease: "none", onUpdate: () => draw(clock.t) }, 0);
// DOM tweens (titles, captions, counters) on the same timeline
draw(0);
window.__timelines = window.__timelines || {};
window.__timelines["<scene id>"] = tl;
```

- A clock tween over the whole scene calls `draw` on every seek; a callback on a shorter tween misses the frames
  outside it. On a GSAP timeline, `onUpdate` of the timeline also works: it runs after its tweens have set their
  values.
- Values the timeline tweens (a plain `state` object) and values computed from `t` with `Kit.ease` both work.
  Values computed from `t` keep `draw` in one place.
- The frame size is `video:` of `settings.yaml`; `setPixelRatio(1)` keeps the canvas at that size.
- `assets/techniques/*/index.html` are full pages on this pattern.

## Look

- The camera moves of "Movement" in `scenes.md` are the three.js camera: one key per sentence in
  `Kit.camera.path`, to the part the sentence names. A CSS `scale` on the canvas magnifies pixels.
- HTML labels and captions over the canvas follow 3D points with `Kit.anchor` inside `draw`, and fade with the
  timeline as DOM elements.
- Shadows, many lights and high polygon counts slow the render: HyperFrames renders WebGL on the GPU of the
  machine, one seek per frame.

## Craft

The stills critic (`references/scene-critic.md`) scores against these rules.

- Night. The sky and the water are the darkest values in the frame, at
  least 3 times darker in luminance than any lit object. Light comes from
  sources in the scene: warm point or spot lights (2700 to 3500 K, about
  `0xffb060`) over quays, roads and work areas, emissive pools on the
  ground under them, and lit windows on buildings (emissive quads, 20 to
  60% of the windows lit, seeded). At least one light casts shadows (the `Kit.lights`
  sun as a dim cool moon, or a `THREE.SpotLight` with `castShadow` over the
  subject), so objects stand on the ground. Ambient light alone
  gives one flat blue: keep the ambient below a third of the key light.
- Ground. Every 3D frame shows a ground plane with detail: quay edges,
  roads, markings, kerbs, grass, yards, and buildings on it. No more than
  about 30% of the frame is empty sky, water or plain ground. Water carries
  reflections of the lights or a texture of streaks; an empty plane reads
  as unfinished.
- Density. Fill the frame with secondary objects: buildings, vehicles,
  stacks, trees, lamp posts, people as simple shapes. Draw repeated items
  with `THREE.InstancedMesh` (one draw call for hundreds), placed by the
  seeded generator of `scenes.md` with varied size, rotation and colour
  within the palette. A wide shot shows hundreds of objects, a close shot
  tens, at three depths: foreground, subject, background.
- Camera paths. No camera position comes closer to any geometry than 3
  times the near plane distance plus the object's size; a boom or tower
  that crosses the frame while the camera passes it shows as a blur. Take
  stills at the middle of every move (key times halfway between path keys),
  not only at the keys, and move the path or the object where one fails.
- Separation. Objects that read as separate keep a visible gap: at least
  2% of the frame between their silhouettes in the stills, or a value or
  colour step between them. Stacked items (containers, boxes) keep a seam
  of 0.03 to 0.05 units, darker than their faces.
- Numbers. A number on screen in two scenes (a time, a count) agrees in
  both, and every number is in the storyboard's data.
