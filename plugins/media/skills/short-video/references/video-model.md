# Writing a video scene

A scene with `Engine: video` is the scene's image animated by a video model
from a motion prompt, timed to the narration. `render` writes `silent.mp4`,
`scene.mp4`, `contact.png` and `meta.json` as for an HTML scene. The model
is the one of task `video` in the settings file `config.yaml`
(`setup:settings`).

## The storyboard

A video scene needs both `Image:` and `Brief:`. A template scene takes no
`Engine:`.

- `Image:` is the first frame the model animates. Make it with
  `media:image-gen`, at the aspect ratio of `video:` (16:9 at 1920x1080);
  `render` scales an image of another shape to cover the frame and crops the
  rest.
- `Brief:` is the motion: what moves in the picture and how the camera
  moves. It is the first `prompt.txt`.
- The On screen cells say what the viewer sees during each sentence, as for
  any scene. The model sees only the prompt, not the sentences or the word
  times: a video scene cannot key an event to a word.

## The version folder

`scaffold -p <project> --scene ID` writes `scenes/<id>/v<N>/`:

- `prompt.txt`, the file you edit: copied from the previous version, else
  the scene's `Brief:`. `render` sends it with its whitespace collapsed.
- `background.png`: the scene's image, sent to the model.
- `timing.json`, `voice_version`, `brief.md` (sentences, beats and word
  times, the frame size and the narration's length).

After `render` the version also holds `model.mp4`, the clip the model
returned. `meta.json` records the model, the prompt, the seed and the clip's
length.

A change to the brief, a beat, a sentence or the image goes into
`storyboard.md`. After `Engine:` changes either way, run `scaffold` before
`render`.

## Length

`render` asks the model for the narration's length (`timing.json`
`duration`) at the model's own size, reshaped to the `video:` aspect ratio.
A model makes clips of a few seconds and may return a shorter or longer
clip, at another size or frame rate. `render`
makes `silent.mp4` from it:

- scaled to cover the `video:` frame, centre-cropped, at the `video:` fps;
- a clip shorter than the narration holds its last frame until the
  narration ends;
- a clip longer than the narration is cut at its end.

A hold longer than about 2 s fails the motion check. For a long sentence
split the scene into several video scenes, or use an HTML scene over the
clip (an imported clip, `Engine: clip`, or "Background video" in
`references/scenes.md`).

## Writing the prompt

The prompt describes motion, not the picture: the model already has the
picture.

- One subject movement and one camera movement, stated with direction and
  speed: "the cells drift slowly to the right; the camera pushes in on the
  largest one".
- Name the things in the picture as they look ("the red cell at the
  centre"), so the model moves the right one.
- Physical motion the model renders well: flow, drift, rotation, growth,
  light changing, a slow push in, pan or orbit.
- No text, labels, numbers or diagrams to draw: models garble text. Put
  them in an HTML scene, or over a clip scene's video.
- No cuts, scene changes or new objects entering: the clip is one shot.
- Keep the style words of the image ("flat illustration", "photograph") so
  the frames keep its look.

## Procedure

1. `short-video.sh scaffold -p <project> --scene ID`.
2. Edit `prompt.txt` from `brief.md` and the rules above.
3. `short-video.sh render -p <project> --scene ID`. Each render is a model
   call, which costs time and money. `--seed N` fixes the model's seed, so a
   prompt change is compared at the same seed. A fix found while looking at
   frames edits `prompt.txt` and runs `render` again on the same version;
   `scaffold` makes a new version only when the storyboard, the image or
   the voice changed.
4. Motion check, over the whole scene, as for any scene: `frames --at
   0,1,2,...`, one per second, each frame next to the frame 2 s later. The
   pair fails when neither the view nor any object moved by about a tenth
   of the frame width and no new element appeared. The held tail of a short
   clip counts. Where a pair fails, change the prompt (more or faster
   motion) and render again until every pair passes.
5. Look at the frames for artefacts: melting shapes, extra limbs, garbled
   text, a subject changing identity. Render again with another prompt or
   seed, or switch the scene to another engine.
