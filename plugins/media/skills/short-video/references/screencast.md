# Screencast clips

`screencast` composes screen recordings and screenshots of a software UI into
a video for an `Engine: clip` scene. A YAML shot list says what each shot
shows, how the camera moves over the page, and what is highlighted, clicked,
typed, drawn and labelled. The command writes the clip at the size and frame
rate of `video:` in `settings.yaml`, so `clip` accepts it.

```
screencast [-p PROJECT] --shots FILE --scene ID   # writes sources/<ID>-screencast.mp4, prints `clip --scene ID FILE`
screencast [-p PROJECT] --shots FILE -o OUT.mp4
screencast [-p PROJECT] --shots FILE -o OUT.mp4 --at 0.5,2.1   # PNG frames OUT_<time>.png, no MP4
```

With `--scene`, the scene must have `Engine: clip`; when it is narrated and
voiced, `screencast` warns if the clip is shorter than the narration. Check
the motion with `--at` stills before the full render, then run
`clip --scene ID FILE` as "Clip scenes" in `SKILL.md` describes.

## Capturing the sources

- Record and capture the page at 2x (a 1920x1080 page as 3840x2160) and give
  the shot `scale: 2`. The camera then zooms to 2x and stays sharp; past the
  source's px per page px times 1.25, `screencast` warns.
- UI text is unreadable below about 1.4 screen px per page px. A shot with
  highlights, clicks or typing whose camera stays below that for its whole
  length gets a warning; frame a smaller rect around the control.
- Static stretches read sharper from a 2x screenshot than from a recording.
- A native dropdown or a page load renders black frames for about 0.5 s.
  End a shot's interval before such a layout change and start the next one
  after it. `screencast` warns when a shot reads a black recording frame.
- Typing is rebuilt from a screenshot of the finished text, so capture the
  field once the text is typed.
- For a dark film, capture the app in its dark theme. A light-mode capture
  that cannot be redone takes `grade` (see "Panel shot").
- A picture smaller than the zoom needs takes `upscale: <px>` (Lanczos and
  an unsharp mask).

Ways to capture:

- Screen recording at 2x: the OS recorder on a HiDPI display, or FFmpeg
  (`ffmpeg -f x11grab -video_size 3840x2160 -framerate 30 -i :0.0 rec.mp4`
  on Linux, `-f avfoundation` on macOS). Record at the film's frame rate.
- Screenshots at 2x: Playwright with `deviceScaleFactor: 2`
  (`page.screenshot()`). Playwright's `recordVideo` records at the CSS
  viewport size (1x), so use it with `scale: 1`, or record the screen.
- Rects in page px: `element.boundingBox()` in Playwright returns CSS px,
  which are page px. Otherwise measure them on a still: `--at` writes
  frames, and a screenshot's pixel position divided by its `scale` is the
  page position.

## Coordinates and times

- Page px: pixels of the given source divided by the shot's `scale`
  (before any `upscale`, so `upscale` never moves a coordinate). Camera keys,
  highlights, clicks, typing, marks, patches, inserts, the wipe divider and
  page-anchored labels use page px.
- Screen px: pixels of the output frame. Labels' `at` and card keys use them.
- Times inside a shot are seconds from the shot's start. `from` and `to`
  default to the shot's start and end.
- Colours: `#RRGGBB` or a name of the style's `palette`. A highlight, click
  or label without a colour takes `accent`; a drawn mark `mark`; a wipe
  `divider`.
- Relative file paths resolve against the shot list's folder.

## The shot list

```yaml
style: {}          # optional: overrides of `screencast:` in settings.yaml (palette, background, ...)
fade: 0.3          # optional: crossfade into each shot, s (0 = hard cuts); default `screencast.fade`
shots:
  - ...
```

Shots play back to back; the clip lasts the sum of their `length`. Each shot
crossfades into the next over its `fade`; during the crossfade the outgoing
shot holds the last frame of its interval. Every key is checked, and an
unknown key or a missing file stops the command with its place
(`shots[2].camera[0]`). `note:` takes any text and is ignored.

### Panel shot (`type: panel`, the default)

The page as a rounded panel turned in 3D over the background, with a soft
shadow and an edge light.

| Key | Value |
|---|---|
| `length` | seconds (required) |
| `video` | a recording; with `from` and `to` (recording seconds, re-timed to `length`) or `times: [[shot s, recording s], ...]` (piecewise linear, for a pause or a jump) |
| `image` | a screenshot (instead of `video`) |
| `wipe` | a before/after wipe (instead of `video` or `image`), see "Wipes" |
| `scale` | source px per page px (default 1; 2 for 2x captures) |
| `upscale` | enlarge a picture narrower than this many px; page coordinates do not change |
| `rect` | `[x, y, w, h]`: the part of the page shown as the panel (default the whole page) |
| `radius` | panel corner radius, page px (default `screencast.panel.radius`) |
| `camera` | camera keys, see "Camera" |
| `highlights` | `[{rect, from, to, color, shape: box/ellipse, grow, pulse, fade}]`: a glowing outline, 8 page px outside `rect`, faded in and out over `fade` (0.3 s), pulsing unless `pulse: false`; `grow: true` draws it out over 0.4 s |
| `clicks` | `[{t, at: [x, y], color}]`: a ripple expanding over 0.7 s |
| `typing` | `[{rect, from, to, caret, caret_color, threshold}]`: the text in `rect` of the screenshot typed glyph by glyph at a constant rate; needs `image` |
| `draw` | `[{shape: box/ellipse, rect, from, to, color, width}]`: a mark drawn on the page as a user draws it (a box from its top-left corner, an ellipse from its left end); `to` defaults to `from` + 0.6 s |
| `patches` | `[{rect, copy: [x, y]}]` or `[{rect, color}]` or `[{rect}]`: paint over a tooltip, a resting cursor or an earlier run's log, from another page area, a colour, or the median colour around it |
| `inserts` | `[{rect, video, from, to}]` or `[{rect, image}]`: a film playing in the page, its own frames warped into the player rect at full resolution |
| `grade` | `{gamma, gain, tint: [r, g, b]}`: a tone change of the page, out = 255 · gain · (in / 255)^gamma, then each channel times `tint`; `{gamma: 1.6, gain: 0.62, tint: [0.92, 1.0, 1.12]}` sets a light-mode capture into a dark film |
| `labels`, `caption` | see "Labels and captions" |

Typing finds the field background from the rect's border, the ink as pixels
that differ from it by more than `threshold` (default 40 of 255), lines as
rows with ink and glyphs as the ends of ink column runs. Give a rect that
holds only the text and some field background around it.

### Picture shot (`type: picture`)

A picture filling the frame, without tilt. Keys: `length`, `image` or `wipe`,
`scale`, `upscale`, `camera`, `highlights`, `clicks`, `draw`, `patches`,
`grade`, `labels`, `caption`. The default camera, and a `rect` key, cover
the frame with the rect, so no edge of the picture shows.

### Cards shot (`type: cards`)

Pictures as rounded cards with soft shadows over the background: fans,
triptychs, variations growing out of their source.

```yaml
- type: cards
  length: 0.9
  glow: accent2            # optional: a coloured glow under the cards
  cards:                   # drawn in this order
    - image: v3.png
      upscale: 2400
      keys: [{t: 0, center: [960, 560], width: 640}, {t: 0.6, center: [440, 590], width: 640, angle: -6}]
    - image: v1.png
      keys: [{t: 0, center: [960, 540], width: 760, angle: 0, alpha: 1}]
```

Keys are screen px: `center`, `width` (card width), `angle` (degrees),
`alpha` (0 to 1), on the same smooth path as the camera.

### Camera

```yaml
camera:
  - {t: 0, rect: [0, 0, 1920, 1080], yaw: -10, pitch: 6}   # the whole page, tilted: zoom 0.92
  - {t: 1.4, center: [1310, 150], zoom: 1.5, yaw: -4, pitch: 2}
  - {t: 2.9, rect: [1000, 40, 760, 300], yaw: 0, pitch: 0} # the control and its surroundings: zoom 2.3
```

A key sets the page point in the frame centre (`center`) and the zoom in
screen px per page px (`zoom`), or `width` (page px across the frame), or
`rect` (its centre, and the zoom that fits it in 0.92 of the frame: about
0.92 × frame width / rect width for a wide rect). A 240 px control as `rect`
gives a zoom near 7: frame the control with its surroundings, a rect of 600
to 1000 page px across for a zoom of 2 to 3. `yaw` turns the panel about
its vertical axis and `pitch` about its horizontal axis, in degrees. A field
left out keeps the previous key's value; the first key's defaults frame the
whole page. Every field moves on a smooth path through the keys (cubic
Hermite, the zoom in log scale): it eases out of the first key and into the
last and moves through the keys between without stopping, slowing only where
a field turns back. Without `camera` the shot holds the whole page. A turn
of 5 to 15 degrees reads as depth; 0 shows the page flat.

### Wipes

```yaml
wipe:
  before: v1.png
  after: v8.png
  divider: [[0, 1440], [1.5, 30], [2.3, 760]]   # [t, page x], on a smooth path
  labels: ["Before: v1", "After: v8"]           # optional, beside the divider
  label_colors: [accent2, accent3]              # optional
  label_edge: top                               # top or bottom of the divider
  fade: [1.35, 1.8]                             # optional: the divider fades out over these times
  align: true                                   # default: align `after` to `before`
```

`before` shows left of the divider, `after` right of it. With `align`,
`after` is warped onto `before` (OpenCV ECC, affine, at quarter size), so the
wipe changes only what the edit changed and not the framing; two versions
from an image model are often shifted by 10 to 20 px. If ECC does not
converge, `screencast` warns and shows them unaligned. To outline the region
a user marked, add a highlight with `pulse: false` that ends as the divider
passes it.

### Labels and captions

```yaml
labels:
  - {text: Mark a region, at: [90, 120], from: 0.1, to: 1.1, color: accent3}
  - {text: Typo, at: [612, 418], page: true, anchor: left, size: 40}
caption: Write what to change             # or {text, from, to, color, size}
```

A label is a dark rounded pill with a coloured dot, faded in and out over
0.35 s. `at` is its top-left corner in screen px (`anchor: center` or
`right` names the top centre or top-right corner instead), or a page point
with `page: true`, which follows the camera. Labels stay
`screencast.safe_margin` px (90) inside every frame edge; keep them at least
100 px from the top. A caption sits in the caption band at the bottom of the
frame; when the shot list has a caption, panel shots darken the band
(`screencast.caption`) so captions read over any page. Hold a label at least
1 s.

## Style

`screencast:` in `settings.yaml` sets the look, and a shot list's `style:`
overrides any part of it for that clip: `palette` (with `accent`, `mark` and
`divider`), `background` (gradient `colors`, drifting `glows`, `particles`),
`panel`, `label` (`font`: a TrueType or OpenType file; null is Pillow's
built-in font), `caption`, `focal`, `vignette`, `safe_margin`, `fade` and
`crf`. The vignette darkens the background only, never a panel or a
picture. The comments in `assets/settings.yaml` describe each field. Sizes in
the style (label size, margins, band height) are px of a 1080 px frame side
and scale with the frame. Match the film's palette and fonts here so the clip
sits with the HTML scenes around it.

## Example

```yaml
style:
  palette: {accent: "#28BEFF", accent2: "#8E7CFF", accent3: "#FF8A3D", mark: "#EC4040", divider: "#FFC46B"}
  background: {colors: ["#070B16", "#101A3A"], glows: [{x: 0.2, y: 0.25, radius: 0.3, color: accent2, amount: 0.3}]}
shots:
  - video: rec/05-mark.mp4        # 3840x2160 recording
    scale: 2
    from: 19.9
    to: 24.6
    length: 1.1
    camera:
      - {t: 0, center: [800, 580], zoom: 1.5, yaw: 7, pitch: 3}
      - {t: 1.1, center: [960, 700], zoom: 2.0, yaw: 1, pitch: 1}
    caption: Mark a region
  - image: shots/comment-typed.png  # 2x screenshot with the comment typed
    scale: 2
    length: 0.9
    typing: [{rect: [1173, 652, 340, 30], from: 0.05, to: 0.8}]
    highlights: [{rect: [1173, 648, 353, 38], color: accent2}]
    camera: [{t: 0, center: [1200, 700], zoom: 2.0}, {t: 0.9, rect: [900, 560, 760, 300]}]
    caption: Write what to change
  - wipe: {before: v4.png, after: v6.png, divider: [[0, 1440], [1.5, 30], [3.2, 250]], labels: ["Before", "After"]}
    scale: 0.8                      # 1152x864 pictures shown as a 1440x1080 page
    upscale: 2048                   # sharper when zoomed; coordinates stay 1152x864 / 0.8
    length: 3.2
    camera: [{t: 0, rect: [0, 0, 1440, 1080], yaw: -7, pitch: 3}, {t: 3.2, center: [740, 730], zoom: 1.55}]
    caption: Only that region is redrawn
```
