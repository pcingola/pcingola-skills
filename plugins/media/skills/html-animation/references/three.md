# three.js chapters

A three.js chapter renders inside the timeline's update callback. The camera, lights and objects are functions of
values the timeline animates, so a seek renders the exact frame. There is no render loop: no
`requestAnimationFrame`, `setAnimationLoop` or `THREE.Clock`. `init --with three` adds three.js r159 (the classic
`THREE` global); `index.html` cannot load ES modules from `file://`, so the addons (OrbitControls, loaders) are
not available.

## Setup, the same in every library

```html
<!-- chapters/scene.html -->
<style>
#scene-gl { position: absolute; left: 0; top: 0; width: 100%; height: 100%; }
#scene-caption { position: absolute; left: 120px; top: 80px; font: 56px sans-serif; color: #fff; }
</style>
<div id="scene-gl"></div>
<div id="scene-caption"></div>
```

```js
var W = 1920, H = 1080;                                  // the stage size of animation.json
var renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(1);
renderer.setSize(W, H);
renderer.domElement.id = "scene-canvas";                 // every created element has an id
el("scene-gl").appendChild(renderer.domElement);
var scene = new THREE.Scene();
var camera = new THREE.PerspectiveCamera(40, W / H, 0.1, 100);
// lights, meshes from content.json ...
var state = { angle: -0.7, rise: 0 };                    // the values the timeline animates
function draw() {
  camera.position.set(Math.sin(state.angle) * 14, 6, Math.cos(state.angle) * 14);
  camera.lookAt(0, 1.5, 0);
  // set object transforms from state
  renderer.render(scene, camera);
}
draw();
```

## The update callback of each library

GSAP: `onUpdate` of the timeline runs after its tweens have set their values.

```js
var tl = gsap.timeline({ paused: true, onUpdate: draw });
tl.to(state, { angle: 0.7, duration: ctx.duration, ease: "none" }, 0);
tl.to(state, { rise: 1, duration: 1.5, ease: "power2.out" }, 0.3);
return tl;
```

anime.js 4: `onRender`, not `onUpdate`. A timeline's `onUpdate` runs before its children update, so it draws the
values of the previous seek.

```js
var tl = anime.createTimeline({ autoplay: false, onRender: draw });
tl.add(state, { angle: 0.7, duration: ctx.duration * 1000, ease: "linear" }, 0);
tl.add(state, { rise: 1, duration: 1500, ease: "outQuad" }, 300);
return tl;
```

Motion: a sequence segment has no update callback, and Motion sets values in its frame loop one frame after a seek.
A motion value that runs over the whole chapter schedules the render in `frame.postRender`, after every value of
that frame is set.

```js
var clock = Motion.motionValue(0);
clock.on("change", function () { Motion.frame.postRender(draw); });
return Motion.animate([
  [clock, [0, ctx.duration], { duration: ctx.duration, ease: "linear", at: 0 }],
  [state, { angle: [-0.7, 0.7] }, { duration: ctx.duration, ease: "linear", at: 0 }],
  [state, { rise: [0, 1] }, { duration: 1.5, ease: "easeOut", at: 0.3 }]
]);
```

## Look

- One camera move per chapter: an orbit, a push-in or a rise, eased or linear over the chapter.
- HTML labels over the canvas (captions, values) animate with the same timeline as DOM elements.
- Headless Chromium renders WebGL in software (SwiftShader); shadows and high polygon counts slow `still`.
