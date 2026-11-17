# Writing a scene

A scene version (`scenes/<id>/v<N>/`) is a self-contained HyperFrames
project. `scaffold` writes everything except the animation; you edit only
`index.html`. The first version starts from `assets/scene.html` (a scene
without `Image:`: `assets/scene-drawn.html`; a template scene:
`assets/<name>.html`); later versions start from the previous `index.html`.

Read `brief.md` first: the brief, each sentence's beat, `S(n)`/`SE(n)` and
the start time of every word. It is generated from `storyboard.md`; a change
to the brief, a beat or a sentence goes into `storyboard.md`.

## Movement

The scene is a shot of a film: something on screen moves the whole time, in
step with the sentences, and the movement shows what the narration says. No
stretch is still for longer than about 2 s (the last 0.5 s excepted), and
frames 2 s apart differ in a way a viewer sees (the motion check in
"Procedure"). Labels appearing on a still picture are not movement enough.

For each sentence, decide what moves before writing any label:

- The camera: a move per sentence to the part of the picture the sentence
  names, large enough to notice without looking for it (a push-in from 1.05
  to 1.3, a pan across a third of the picture), changing target or direction
  as the sentences change.
- Drawn movement: lines and paths drawn along a route, arrows growing,
  shapes outlined, diagrams built part by part.
- Flows: particles, dots or arrows streaming from one part of the picture to
  another while the sentence describes it.
- Values: numbers counting, bars and gauges growing, a marker sliding along
  a scale.
- Text built with the speech, word by word or line by line.
- Layers: an added element, a crop of the picture or a second image moving
  over the background at another speed.

Between two cues the scene keeps changing visibly: the camera move runs on
to the next cue, a flow continues, a line keeps drawing. A slow drift alone
does not pass the motion check.

## Composition rules

- The frame size and frame rate are `video:` in `settings.yaml` (also in
  `brief.md`). Do not change the root `div`'s attributes, the background
  layers (`#bg-fill` and, on image scenes, `#bg-image`) or any
  `data-duration` marked `data-full-length`; `scaffold` sets those to the
  scene length.
- One GSAP timeline, created `paused: true`, registered as
  `window.__timelines["<scene id>"]`. The renderer seeks it frame by frame, so
  everything is a function of time: no `setTimeout`, no
  `requestAnimationFrame`, no `Math.random()`, no CSS
  transitions or animations, no audio elements, and no video element other
  than the background video below.
- `render` checks the page and the scripts you add for these rules before
  lint and fails with `<file>:<line>` for each break: timers
  (`setTimeout`, `setInterval`, `requestAnimationFrame`,
  `setAnimationLoop`, `THREE.Clock`), wall clocks (`Date.now`,
  `new Date()` without arguments, `performance.now`; a literal date such
  as `new Date(2020, 0, 1)` passes), `Math.random` and the library random
  functions,
  d3 `.transition()`, endless repeats (`repeat: -1`, `loop: true`),
  `autoplay: true` or `.play()`, `new Audio`, `<audio>`, a `<video>`
  without `data-start`, CSS `animation`, `transition` or `@keyframes`,
  `fetch`, `XMLHttpRequest`, `import()`, remote URLs, and a declaration
  that shadows a timing helper (`const W = 1920`; name the frame size `FW`,
  `FH`). Comments and
  strings are not checked; the library, kit, `timing.js` and `card.js`
  files are trusted. Values that look random come from a seeded generator:
  `const rand = (s => () => (s = (s * 16807) % 2147483647) / 2147483647)(7);`.
- Overlays (labels, arrows, boxes, SVG diagrams) are absolutely positioned
  elements inside `#root`, after the `<!-- overlays here -->` comment,
  starting hidden (`opacity: 0`) and shown by the timeline. An overlay fixed
  to a point of the picture goes inside `#anchored`, the full-frame layer
  that moves with the camera.
- Local files only: the library files below, `timing.js`, `background.png` (scenes
  with `Image:`), `background.mp4` and files you add to the version directory. No network fonts or CDNs.
- The page has no audio; `render` muxes the narration.

### Library files

A page loads libraries with a `<script src>` of the bare file name, from the version directory:

| File | Library | Global |
|---|---|---|
| `gsap.min.js` | GSAP 3.13.0 | `gsap` |
| `anime.umd.min.js` | anime.js 4.5.0 | `anime` |
| `motion.js` | Motion 14.14.0 | `Motion` |
| `d3.min.js` | d3 7.9.0 | `d3` |
| `three.min.js` | three.js 0.159.0 | `THREE` |

GSAP has its own no-charge licence; `gsap.min.js` is 72 KB minified. d3 is
ISC, `d3.min.js` 280 KB; three.js is MIT, `three.min.js` 668 KB. The
licence and size of anime.js and Motion are at the top of
`references/anime.md` and `references/motion.md`.

- `setup` installs them at pinned versions and checks each file's SHA-256.
- `scaffold` copies `gsap.min.js` always, and each other file the page names in a `<script src>`.
- `render` copies a named file the version directory lacks, so a `<script src="three.min.js">` added after `scaffold` works.
- A `<script src="kit/<file>.js">` loads a kit script (`tiltshift.js`, `glow.js`, `shadow.js`, `ribbon.js`, `labels3d.js`, `camera.js` on three.js; `beat.js` on GSAP only). `scaffold` and `render` copy it into the version's `kit/` the same way.
- A three.js page: `references/three.md`.
- `render` refuses a page that HyperFrames cannot seek: it needs `window.__timelines["<root id>"] = tl` or a `window.addEventListener("hf-seek", ...)`. A root with `data-no-timeline` (anime.js, Motion) needs the `hf-seek` listener (`references/anime.md`, `references/motion.md`).

## Timing helpers (`timing.js`)

```js
S(n)            // start of sentence n (1-based), seconds
SE(n)           // end of sentence n
W(n, "word")    // start of the first "word" in sentence n
W(n, "word", 2) // start of its second occurrence
WE(n, "word")   // end of that word
```

`S`, `SE`, `W`, `WE`, `ST` and `STE` are globals of `timing.js`: a page
declares no variable or function of these names.

Words match case-insensitively with punctuation removed (`W(2, "spike")`
matches `spike,`); hyphenated and numeric words as written (`W(1, "1995")`,
`W(3, "state-of-the-art")`). Use literal arguments: `render` checks every
literal call against `timing.json`. A wrong non-literal call throws in the
page and renders a scene with no animation.

Land an event a little before its word (`W(2, "spike") - 0.1`), and keep it
on screen until its sentence ends (`SE(n)`), not for a fixed delay.

## Scenes without a picture

A scene without `Image:` has no `background.png` and no `#bg-image`.
Everything on screen is drawn in the page: a diagram, chart, map, process or
text built with the speech, as HTML, SVG or canvas drawn from the timeline.
`#bg-fill` is the background, a flat colour or gradient in the film's
palette (the suggested page's navy gradient is a placeholder; restyle it as
for "Title, summary and end scenes"), or a background drawn in the page.
Put the drawing inside `#anchored`, the full-frame layer the camera moves
(`tl.fromTo("#anchored", ...)`); text and labels fixed to the frame go after
it.

The rules of "Movement" apply as for every scene. Over a flat or gradient
background a camera move on `#bg-fill` is invisible, so the movement comes
from the drawing: parts built with the sentence that names them, flows
along its lines, values counting, and camera moves on `#anchored` to the part
each sentence names. The motion check is the same.

Charts and diagrams follow `references/motion-rules.md`.

`render` refuses a page other than a template's that uses `background.png`
when the version has none: a scene whose `Image:` was removed keeps its
previous page, so redraw it without the picture.

## Silent scenes and shared worlds

A silent HTML scene (`Length:` in the storyboard) has no voice version.
`scaffold` writes `timing.json` as `{"duration": <Length>, "sentences": []}`
and no `voice_version`; the page keys its tweens to plain seconds, and
`render` gives the scene a silent sound track. The rules of "Movement" apply
over its whole length.

Scenes with the same `World:` share one page in `worlds/<name>/v<N>/`, a
HyperFrames project like a scene version. `scaffold --scene ID` and
`render --scene ID` on any scene of the world act on the whole world.

- Times. Scene k lasts its narration (or its `Length:`). Scene starts are
  whole frames: the first starts at frame 0, and each next one at the frame
  nearest to the sum of the lengths before it. The world lasts the sum.
  `world.json` holds the world, its length, the fps and, per scene, its
  `start`, `duration`, `frames` (`[first, end)`) and `voice_version`.
- Page. The root has `data-composition-id="<name>"` and the timeline is
  `window.__timelines["<name>"]`. A new world starts from
  `assets/world.html` (drawn, like `scene-drawn.html`); a later version
  starts from the previous version's page, and the files and
  subdirectories you added to the version directory (videos, pictures,
  `fonts/`) are copied with it; `stills/` is not.
- Helpers. `timing.js` holds every scene's times in world time, and every
  helper names the scene first, its id as a string literal: `ST("id")` and
  `STE("id")` (scene start and end), `S("id", n)`, `SE("id", n)`,
  `W("id", n, "word", k)`, `WE("id", n, "word", k)`. `render` checks these
  calls as it checks a scene page; a call without the scene id is an error.
  Key every tween to these helpers, so a new voice version moves the tweens
  with their scene.
- `brief.md` lists each scene's Brief, start and end, and its sentences and
  word times in world time.
- Camera and light. The camera and the light keep moving across scene
  boundaries. A cut between two scenes of a world is what the world exists
  to avoid; a scene that needs a cut belongs in no world.
- Render. `render` checks, lints and renders the world page once to
  `worlds/<name>/v<N>/silent.mp4`, then writes the next version of every
  scene of the world: `scenes/<id>/v<M>/` with its cut `silent.mp4`,
  `scene.mp4` (with the scene's narration, or silence), `contact.png`,
  `world.json` (`world`, `version`, `start`, `duration`) and `meta.json`
  (with `world`, `world_version`, `start`). It prints every `scene.mp4`.
  There is no partial render: an edit for one scene renders the whole world.
- Per scene. `stills --scene ID --at t` opens the world page at
  `start + t` and names the stills by scene and scene time (`t` = world time
  minus the scene's `start`); the motion check and the Brief check use them.
  `frames`, `contact.png` and `assemble` work on the rendered cuts; `assemble`
  joins them frame to frame. The HTML film plays the world page once, across
  its scenes.
- Edits. An edit for one scene goes into the world page. `scaffold` a new
  world version first when a voice or a Brief changed; otherwise edit the
  latest world version and take `stills` again. A Brief edited before the
  world is rendered needs no new version: `scaffold --scene ID --refresh`
  rewrites `brief.md`, the timing files and `world.json` of the latest
  version in place and keeps its page and added files (a scene page: its
  `brief.md`, timing files, `voice_version` and `card.js`). A fix found in the Brief check
  edits the page, not the Brief (see "Procedure").

## Placing overlays on the image

`#bg-image` uses `object-fit: contain`. For a frame `W x H` and an image of
native size `w x h` (`file background.png`), the scale is
`k = min(W / w, H / h)` and the image's top-left corner is at
`((W - k*w) / 2, (H - k*h) / 2)`. Image pixel `(x, y)` is at
`(left + k*x, top + k*y)` on screen.

An image that is almost 16:9 (gpt-image-2 returns 1360x768) leaves a thin
dark line of the blurred fill at the frame edges. Close it with
`#bg-image { transform: scale(1.012); }` (or the scale that covers the gap),
not with `clip-path`. The edge scale only closes the gap: camera moves go
far beyond it and never below it.

The camera moves `#bg-image` and `#anchored` with the same tween, so labels
and shapes fixed to the picture follow it; the camera does not stop for a
label. Both are full-frame boxes, so image pixel `(x, y)` stays under the
point placed at `(left + k*x, top + k*y)` inside `#anchored`. Text inside
`#anchored` scales with the camera: size it for the largest zoom of its
sentence. To keep the image's box over the whole frame, a shift (`xPercent`,
`yPercent`) stays within `(scale - 1) / 2` of the frame on each axis.

## Background video

A pre-rendered clip (a morph from `media:video-effects`, generated video,
the user's footage) can replace the still image while overlays and camera
moves run on top. HyperFrames
extracts the clip's frames with FFmpeg at the render's frame rate and paints
frame `floor(t * fps)` at scene time `t`, copying the video element's
transform, so the clip stays in sync with the timeline frame by frame.

Copy the clip into the version directory as `background.mp4`; `scaffold`
carries it into later versions. Replace the `<img id="bg-image">` line with:

```html
<video id="bg-video" class="clip bg" src="background.mp4" muted playsinline preload="auto"
       data-start="0" data-duration="6.2" data-full-length data-track-index="1"></video>
```

with the root's `data-duration` in place of `6.2` (later scaffolds keep it
equal to the scene length), and add
`#bg-video { object-fit: contain; }` to the style. Camera moves and overlay
placement work as on `#bg-image`, with `#bg-video` and `#anchored` as the
targets:

```js
tl.fromTo(["#bg-video", "#anchored"], { scale: 1 }, { scale: 1.3, transformOrigin: "50% 50%",
          duration: SE(2) - S(1), ease: "sine.inOut" }, S(1));
```

- Length: at least the scene length. A longer clip is cut at the scene's
  end. Where a shorter clip ends, HyperFrames stops updating the element, so
  the picture and the camera move freeze; `render` refuses it. Hold its last
  frame with `ffmpeg -i in.mp4 -vf tpad=stop_mode=clone:stop_duration=S out.mp4`.
- Size: the frame size times the largest zoom, at the frame's aspect ratio:
  2560x1440 for zooms up to 1.3x in a 1920x1080 frame. Frame rate: `video:`.
- The page stays silent: the clip's audio is not used.

## Patterns

```js
const tl = gsap.timeline({ paused: true });
const cam = ["#bg-image", "#anchored"];  // the picture and the overlays fixed to it

// Camera: one move per sentence, each to the part the sentence names, running
// into the next sentence so it never rests (scale the image, not the page)
tl.fromTo(cam, { scale: 1.05, xPercent: 0, yPercent: 0 },
          { scale: 1.35, xPercent: 8, yPercent: -4, transformOrigin: "50% 50%",
            duration: S(2) - S(1), ease: "sine.inOut" }, S(1));
tl.to(cam, { scale: 1.6, xPercent: -14, yPercent: 6, duration: S(3) - S(2), ease: "sine.inOut" }, S(2));

// A path drawn along the route the sentence describes
const route = document.querySelector("#route");
const len = route.getTotalLength();
gsap.set(route, { strokeDasharray: len, strokeDashoffset: len });
tl.to(route, { strokeDashoffset: 0, duration: WE(3, "away") - W(3, "carries"), ease: "none" }, W(3, "carries"));

// A flow along a path: every dot's position is computed from the tween's progress,
// so it is right at every seeked frame. Use this pattern for every flow, the
// prototype's included. #flow-path and the .dot circles are in an SVG in #anchored.
const flowPath = document.querySelector("#flow-path");
const flowLen = flowPath.getTotalLength();
const dots = Array.from(document.querySelectorAll("#anchored .dot"));
const flow = { p: 0 };
tl.to(flow, { p: 1, duration: SE(2) - S(2), ease: "none", onUpdate: () => {
  dots.forEach((d, i) => {
    const f = (flow.p * 4 + i / dots.length) % 1;  // each dot makes 4 trips in the sentence
    const pt = flowPath.getPointAtLength(f * flowLen);
    d.setAttribute("cx", pt.x);
    d.setAttribute("cy", pt.y);
  });
} }, S(2));

// Number counting up as it is said
const n = { v: 0 };
tl.to(n, { v: 95, duration: 0.8, onUpdate: () => {
  document.querySelector("#pct").textContent = Math.round(n.v) + "%";
} }, W(4, "95%"));

// A highlight that keeps pulsing while its sentence plays
tl.fromTo("#box", { opacity: 0, scale: 0.9 }, { opacity: 1, scale: 1, duration: 0.3 }, W(1, "nucleus"));
tl.to("#box", { scale: 1.06, duration: 0.5, yoyo: true, repeat: 3, ease: "sine.inOut" }, W(1, "nucleus") + 0.3);

// Label on the word that names it, inside #anchored so it rides with the camera
tl.fromTo("#lbl-spike", { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.35 }, W(2, "spike") - 0.1);
tl.to("#lbl-spike", { opacity: 0, duration: 0.3 }, SE(2));
```

## GSAP pitfalls

- `fromTo` renders its start state at once, when the timeline is built. A
  later `fromTo` on an element that must stay hidden or placed elsewhere
  until its cue needs `immediateRender: false` in its end values.
- A tween of `x`, `y`, `scale` or `rotation` on an SVG element with a
  `transform` attribute replaces that attribute. Wrap the element in a
  `<g>` and tween the wrapper.
- Rotate or pulse an SVG element about a point with `svgOrigin: "x y"` (in
  the SVG's user units); `transformOrigin` on SVG is relative to the
  element's bounding box.

## Style

Defaults for a 1920x1080 frame. Depart from them when the film needs it, as
long as text stays legible and the frame uncluttered; record a change the
user asks for in `lessons.md`.

- Label text at least 36 px on screen in every frame, after any camera zoom:
  a label inside `#anchored` scales with the camera, so size it for the
  smallest scale of its sentence, and scale it up or remove it where a
  pull-back would shrink it below 36 px. Secondary text may be smaller, down
  to 24 px on screen: chart axis ticks, axis and unit titles, category
  labels on an axis, source lines, and a muted line under a title or
  label. A kicker above a title is a label. Labels sit
  inside a 60 px margin from the frame edge.
- Fonts: every font a page names is a font file in the version
  directory's `fonts/`, under the SIL Open Font License (every Google Font
  family is), loaded with `@font-face { font-family: "<name>"; src:
  url("fonts/<file>"); }`. The renderer would also find an installed font,
  but film.html plays on other machines, and `html` embeds only `fonts/`
  files: it warns for each font stack whose first family no local
  `@font-face` embeds. Pick an OFL family installed here (`fc-list : family
  file | grep -i "<family>"` gives its files) and copy the files of the
  weights the page uses into `fonts/`; a family that is not installed and is
  OFL may be downloaded into `fonts/`. A non-OFL installed font (such as the
  URW Nimbus fonts) is replaced by an OFL family. `scaffold` carries
  `fonts/` into the next version. End every font stack with a generic
  family (`sans-serif`, `serif`, `monospace`).
- Colours, for labels and cards alike: text is dark on a light ground and
  light on a dark ground, in the film's palette. A label carries its own
  solid or semi-opaque ground, so its text contrasts with that ground, not
  with the picture behind it; a card's ground is its background.
- At most three overlays at once; remove an overlay when the narration moves
  on.
- Ease with `power2.out` or `sine.inOut`; entrances 0.3-0.5 s. A camera
  move lasts its sentence and changes target with the next one.
- Nothing moves in the last 0.5 s of the scene; everything before it moves.

## Title, summary and end scenes

The suggested pages have a dark navy background, white text and a yellow
accent as placeholders. Restyle the page to match the prototype's
`index.html` and the film's images (background, colours, fonts, sizes, label
style, motion), with the colour rule of "Style": light images get a light
card with dark text. Render the
suggestion unchanged only when it already matches the film. Later scaffolds
copy the restyled page.

Keep, whatever the style:

- The text comes from `window.CARD` in `card.js`: `rows` (the On screen
  cells), `author`, `image` (whether `background.png` exists), `byline` and
  `credit`. `scaffold` rewrites `card.js` from the storyboard, so never type
  the text into `index.html`.
- Title: `rows[0]` appears as sentence 1 starts, `rows[n-1]` with sentence n,
  `byline` with the title when `byline` is set (null: no byline).
- Summary: point n appears with sentence n and stays to the end.
- End: `rows[0]` with sentence 1, `rows[1]` (if any) with sentence 2. After
  `SE(last)` the `credit` line, when set (null: none), fades in under them
  and holds to the end of the scene. It is a small byline that does not compete with the closing
  line.
- Each sentence, and a hold after the narration (the end scene's credit
  hold), gets its own movement with a new target, as in "Movement". The
  suggested pages move the background to a new framing (a shift and scale
  with no margin limit) and move and scale the text block as far as the
  60 px margin allows, measured on its rows (`fit` in the page), so no text
  leaves the margin at any shot. A restyled page keeps a movement per
  sentence that passes the motion check, with its text inside the margin.
  The last 0.5 s is still.
- Over a flat or gradient background, moving the background is invisible:
  on such a card, and on any text-only card, the per-sentence movement comes
  from drawn elements (a diagram, icon or counter built with the speech).
  The end scene's hold shows a drawn element completing or moving, with or
  without a credit line.
- `#sweep` on the title and end pages, a line drawn across the frame during
  each sentence, is a placeholder: a restyled page replaces it with a drawn
  element tied to the text (an underline of a key word, a shape or icon of
  the point, a counter).
- Summary: each point arrives with an element drawn in the page and tied to
  it (a shape, icon, counter or chart mark); the suggested page draws a
  mark beside each point and a bar under it during its sentence. A crop or
  file from the evidence scene's version may be copied into the summary's
  version directory after `scaffold`, as the logo is, and drawn in.
- The text fits: check `contact.png` for wrapping.

With `brand:` set, the title and end scenes show the brand logo: copy the
file named by `logo` in the brand folder's `brand.yaml` into the version
directory, and place it as the folder's `guidelines.md` says. A scene renders
from its own folder and `scaffold` does not copy the logo, so copy it into
each new version after `scaffold`.

## Stills and the HTML film

An HTML scene needs no render to be seen. `stills --scene ID --at t1,t2,...`
loads the latest page version (a world scene: the latest world version) in
the render browser with `hyperframes snapshot` and seeks it as `render`
does: the GSAP timeline `window.__timelines["<root id>"]`, or the `hf-seek`
event of an anime.js, Motion or three.js page. Each still is the frame
`render` would write at that time. They go to the version's `stills/`, as
`at_<t>.png` (a world scene: `<scene>_at_<t>.png`). `--sheet` adds one
labelled contact sheet of the stills (`sheet.png`, a world scene:
`<scene>_sheet.png`), the overview for the motion check and the Brief
check; each pair is judged on the full-size stills. `--mark x,y` or `--mark x,y,w,h` adds a copy `..._mark.png` with a
red point or rectangle in frame pixels, to show a comment's place.
`--version vN` takes the stills from an older version (a world scene: world
version). `frames` stays for rendered scenes (`scene.mp4`). Each still is
the second of two seeks (the first 5 ms later), because on a hardware GPU
the first three.js draw that links new shader programs can come out black.
A WebGL page's still with half or more of its pixels exactly #000000 is
taken again once, and `stills` fails when it stays so: draw a black ground
as a near-black such as `#050505`.

`check --scene ID` runs the checks of `render` (timing helpers, a seekable
timeline, the determinism rules, `<video>` lengths, the background image,
`hyperframes lint`) on the latest page and renders nothing.

`html` writes the film as one file, `film/html/v<N>/film.html`: each page
with every local script inlined and every local picture, video and font as
a data URI, so the file plays from file:// on another machine; it warns for
each font a page names without a `fonts/` file (Fonts, under Style). A scene's
narration and the music play in step. The player seeks each page through
the same timeline or `hf-seek` listener, so a page that passes `stills` plays
in the film. `film.html#t=12.5` opens the film paused at 12.5 s (film
time), for a check of the film at a given moment. Each page carries its own libraries, so the file grows by the
size of each library per page (GSAP 72 KB, three.js 668 KB) plus its
pictures as base64 (4/3 of their size); `html` prints the file size.

`render` (an MP4 per scene) runs only when the user asks for a video file.

## Procedure

1. `short-video.sh scaffold -p <project> --scene ID`.
2. Edit `index.html`: overlays in the body, the timeline in the script.
3. `short-video.sh check -p <project> --scene ID`. Fix any error it reports
   and check again; run it after each edit of the page. A fix found while looking at stills (layout, size, timing,
   movement) edits the page of the same version and takes the stills again;
   `scaffold` makes a new version only when the storyboard, the image or
   the voice changed, and `scaffold --refresh` takes a storyboard change
   into an unrendered version in place.
4. Motion check, over the whole scene (start, middle, end and any hold):
   `stills --sheet --at 0,1,2,...`, one per second. Put each frame next to the
   frame 2 s later. The pair fails when neither the view nor any object
   moved by about a tenth of the frame width (192 px at 1920) and no new
   element appeared; a slow drift of a few pixels fails. The last 0.5 s is
   excepted. The contact sheet's thumbnails are too small to judge it.
   Where a pair fails, add movement and take the stills again until every pair
   passes; the scene is not done before.
5. Look at the sheet for layout and at `stills --at <t>` for each beat's
   key word, at full size, to see that the text is legible.
6. Brief check, together with steps 4 and 5: `stills --sheet --at` the times the
   Brief names (each camera keyframe, each element's entrance, each light
   change) and compare each still with the Brief and its On screen cell,
   and with the reference stills the Brief names when the film has a
   reference (`refs/`): palette, fonts, light, framing, and each element
   present and in place.
   Fix what differs in the page of the same version and take the stills
   again. The Brief changes only when its intent was wrong; then change it in
   `storyboard.md` and run `scaffold --refresh` (or `scaffold` for a new
   version once the page is rendered).
7. Stills critic, after steps 4 to 6: one fresh critic reviews the stills
   once, as `references/scene-critic.md` says; fix or decline its findings,
   take the stills again, and the scene is done. No second critic follows.

The kit (`assets/kit/README.md`) and the techniques in
`assets/techniques/<name>/` are starting points to use, change or ignore.
A scene they do not cover is written from scratch, and they do not limit
what a film shows. A new technique that worked goes into the project's
`lessons.md` as one dated line; adding it to `assets/techniques/` is the
user's decision.
