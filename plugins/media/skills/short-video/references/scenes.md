# Writing a scene

A scene version (`scenes/<id>/v<N>/`) is a self-contained HyperFrames
project. `scaffold` writes everything except the animation; you edit only
`index.html`. The first version starts from `assets/scene.html` (a template
scene: `assets/<name>.html`); later versions start from the previous
`index.html`.

Read `brief.md` first: the brief, each sentence's beat, `S(n)`/`SE(n)` and
the start time of every word. It is generated from `storyboard.md`; a change
to the brief, a beat or a sentence goes into `storyboard.md`.

## Composition rules

- The frame size and frame rate are `video:` in `settings.yaml` (also in
  `brief.md`). Do not change the root `div`'s attributes, the background
  layers (`#bg-fill` and, on image scenes, `#bg-image`) or any
  `data-duration` marked `data-full-length`; `scaffold` sets those to the
  scene length.
- One GSAP timeline, created `paused: true`, registered as
  `window.__timelines["<scene id>"]`. The renderer seeks it frame by frame, so
  everything is a function of time: no `setTimeout`, no
  `requestAnimationFrame`, no `Math.random()` at play time, no CSS
  transitions or animations, no audio elements, and no video element other
  than the background video below.
- Overlays (labels, arrows, boxes, SVG diagrams) are absolutely positioned
  elements inside `#root`, after the `<!-- overlays here -->` comment,
  starting hidden (`opacity: 0`) and shown by the timeline.
- Local files only: `gsap.min.js`, `timing.js`, `background.png`,
  `background.mp4` and files you add to the version directory. No network fonts or CDNs.
- The page has no audio; `render` muxes the narration.

## Timing helpers (`timing.js`)

```js
S(n)            // start of sentence n (1-based), seconds
SE(n)           // end of sentence n
W(n, "word")    // start of the first "word" in sentence n
W(n, "word", 2) // start of its second occurrence
WE(n, "word")   // end of that word
```

Words match case-insensitively with punctuation removed (`W(2, "spike")`
matches `spike,`); hyphenated and numeric words as written (`W(1, "1995")`,
`W(3, "state-of-the-art")`). Use literal arguments: `render` checks every
literal call against `timing.json`. A wrong non-literal call throws in the
page and renders a scene with no animation.

Land an event a little before its word (`W(2, "spike") - 0.1`), and keep it
on screen until its sentence ends (`SE(n)`), not for a fixed delay.

## Placing overlays on the image

`#bg-image` uses `object-fit: contain`. For a frame `W x H` and an image of
native size `w x h` (`file background.png`), the scale is
`k = min(W / w, H / h)` and the image's top-left corner is at
`((W - k*w) / 2, (H - k*h) / 2)`. Image pixel `(x, y)` is at
`(left + k*x, top + k*y)` on screen.

An image that is almost 16:9 (gpt-image-2 returns 1360x768) leaves a thin
dark line of the blurred fill at the frame edges. Close it with
`#bg-image { transform: scale(1.012); }` (or the scale that covers the gap),
not with `clip-path`. A camera move on `#bg-image` then starts from that
scale.

Overlays placed on the image do not follow a camera move of `#bg-image`: show
them only while the camera is still, or give them the same transform.

## Background video

A pre-rendered clip (such as a morph from `media:video-effects`) can replace
the still image while overlays and camera moves run on top. HyperFrames
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
placement work as on `#bg-image`, with `#bg-video` as the target:

```js
tl.fromTo("#bg-video", { scale: 1 }, { scale: 1.3, transformOrigin: "50% 50%",
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

// Label appears on the word that names it, leaves at the end of the sentence
tl.fromTo("#lbl-spike", { opacity: 0, y: 12 }, { opacity: 1, y: 0, duration: 0.35 }, W(2, "spike") - 0.1);
tl.to("#lbl-spike", { opacity: 0, duration: 0.3 }, SE(2));

// Slow camera push-in over a sentence (scale the image, not the page)
tl.fromTo("#bg-image", { scale: 1 }, { scale: 1.25, transformOrigin: "62% 40%",
          duration: SE(2) - S(2), ease: "sine.inOut" }, S(2));

// Arrow drawn as an SVG line
tl.fromTo("#arrow line", { attr: { x2: 600, y2: 300 } },
          { attr: { x2: 840, y2: 420 }, duration: 0.5 }, W(3, "binds"));

// Number counting up as it is said
const n = { v: 0 };
tl.to(n, { v: 95, duration: 0.8, onUpdate: () => {
  document.querySelector("#pct").textContent = Math.round(n.v) + "%";
} }, W(4, "95%"));

// Highlight box pulse
tl.fromTo("#box", { opacity: 0, scale: 0.9 }, { opacity: 1, scale: 1, duration: 0.3 }, W(1, "nucleus"));
```

## Style

Defaults for a 1920x1080 frame. Depart from them when the film needs it, as
long as text stays legible and the frame uncluttered; record a change the
user asks for in `lessons.md`.

- Label text at least 36 px, with a solid or semi-opaque background, inside a
  60 px margin from the frame edge.
- At most three overlays at once; remove an overlay when the narration moves
  on.
- Ease with `power2.out` or `sine.inOut`; entrances 0.3-0.5 s; camera moves
  span a whole sentence.
- Nothing moves in the last 0.5 s of the scene.

## Title, summary and end scenes

The suggested pages have a dark navy background, white text and a yellow
accent as placeholders. Restyle the page to match the prototype's
`index.html` and the film's images (background, colours, fonts, sizes, label
style, motion): light images get a light card with dark text. Render the
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
- The text fits: check `contact.png` for wrapping.

With `brand:` set, the title and end scenes show the brand logo: copy the
file named by `logo` in the brand folder's `brand.yaml` into the version
directory, and place it as the folder's `guidelines.md` says. A scene renders
from its own folder and `scaffold` does not copy the logo, so copy it into
each new version after `scaffold`.

## Procedure

1. `short-video.sh scaffold -p <project> --scene ID`.
2. Edit `index.html`: overlays in the body, the timeline in the script.
3. `short-video.sh render -p <project> --scene ID`. Fix any error it reports
   and render again; this re-renders the same version.
4. Look at `contact.png`, and at `frames --at <t>` for each beat's key word.
