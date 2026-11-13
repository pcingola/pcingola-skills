# Writing a manim scene

A scene with `Engine: manim` is a Manim Community Edition (0.19.0) Python
file timed to the narration. `render` writes `silent.mp4`, `scene.mp4`,
`contact.png` and `meta.json` as for an HTML scene.

## The version folder

`scaffold -p <project> --scene ID` writes `scenes/<id>/v<N>/`:

- `scene.py`, the file you edit: copied from the previous version, else the
  starting page `assets/manim_scene.py`, which shows each beat's text at the
  bottom of the frame while its sentence is spoken.
- `sv_timing.py`: generated from `timing.json`; do not edit it.
- `timing.json`, `voice_version`, `brief.md` (sentences, beats and word
  times, and the class `render` renders, `manim.scene_class`), and
  `background.png` when the scene has `Image:`.

A change to the brief, a beat or a sentence goes into `storyboard.md`. After
`Engine:` changes either way, run `scaffold` before `render`.

## Timing helpers

```python
from sv_timing import DURATION, S, SE, W, WE, TimedScene

S(n)                # start of sentence n (1-based), seconds of scene time
SE(n)               # end of sentence n
W(n, "word")        # start of the first "word" in sentence n
W(n, "word", 2)     # start of its second occurrence (also k=2)
WE(n, "word")       # end of that word
```

Words match as in `timing.js` (`references/scenes.md`). `render` checks every
call with literal arguments before running Manim; a wrong call with variables
raises `ValueError` during the render.

The scene class subclasses `TimedScene`:

- `self.at(t)` waits until scene time `t`. A cue is
  `self.at(W(2, "cell") - 0.1)` followed by `self.play(...)`.
- `self.finish()` waits until the end of the narration and is the last call
  of `construct`.

Scene time moves in whole frames, and every `self.play` and `self.wait`
advances it, so the animations between two cues must fit in the time between
them. `at` raises `ValueError` when the scene is more than one frame past its
cue; `finish` raises when the scene is past the end of the narration.

## background.png

The starting page fits the image inside the frame (height
`config.frame_height`, reduced to `config.frame_width` when wider). The frame
is 8 units high with the origin at its centre; at 1080 px one unit is
135 px. For an image of native size `w x h`, the scale is
`s = bg.height / h` units per pixel and image pixel `(x, y)` is at
`((x - w/2) * s, (h/2 - y) * s, 0)`.

## Manim CE for the 3Blue1Brown look

Objects drawn and transformed on a plain background, in step with the
narration:

- Drawing: `Create`, `Write`, `DrawBorderThenFill`.
- Changing: `Transform` (keeps the first object), `ReplacementTransform`
  (later code uses the target), `TransformMatchingTex`.
- Attention: `Indicate`, `Circumscribe`, `Flash`, `FocusOn`.
- In and out: `FadeIn`, `FadeOut` (`shift=` for a direction),
  `GrowFromCenter`, `Uncreate`.
- Text: `Text` needs no LaTeX; `MathTex` and `Tex` need `latex` and
  `dvisvgm` on `PATH`.
- Plots: `Axes`, `NumberPlane`, `axes.plot(lambda x: ..., x_range=...)`,
  `axes.get_graph_label`, `axes.get_area`, `axes.c2p(x, y)`; `ValueTracker`
  with `always_redraw` or `add_updater` for a moving value.
- Shapes: `Dot`, `Line`, `Arrow`, `Circle`, `Square`, `Rectangle`,
  `SurroundingRectangle`, `Brace`; `VGroup` with `arrange` and `next_to`.

The style rules of `references/scenes.md` apply. The background
(`BACKGROUND_COLOR` in `scene.py`), text and accent colours and the font
(`Text(..., font="...")`) match the prototype and the HTML scenes. The last
animation ends by `DURATION - 0.5`, then `self.finish()`.

## Procedure

1. `short-video.sh scaffold -p <project> --scene ID`.
2. Edit `scene.py` from `brief.md`: one `self.at(...)` per cue,
   `self.finish()` last.
3. `short-video.sh render -p <project> --scene ID`. A video more than
   `manim.length_tolerance_frames` frames away from the narration length is
   refused, usually because `self.finish()` is missing. On a Manim error
   `render` prints the last 30 lines of its output.
4. Look at `contact.png`, and at `frames --at <t>` for each beat's key word.

uv creates the Manim environment on the first render; it needs no
HyperFrames.

## Settings

`manim:` in `settings.yaml`: the scene class `render` renders, the length
tolerance, Manim's log level, and the starting page's colour, font size and
fade. The starting-page keys apply when `scaffold` writes a new `scene.py`.
Frame size and rate are `video:`.
