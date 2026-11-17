# Short versions of a film

A short version (about 2 minutes) is a new project made from an existing
film (usually 4 to 5 minutes). The original project is read only: nothing in
it is changed, replaced or deleted.

Before writing the storyboard, confirm the target message and the audience
with the user, and whether the audience differs from the original film's. An
example: "the new audience is a general audience with no background in the
subject, and the message is the main result and why it matters". A short version is high level: lead with the strongest
results, show concrete outcomes, leave out methods and technical detail.

1. Read the original: `storyboard.md`, `settings.yaml`, `lessons.md`, the
   files under `sources/` and the latest film: `film/html/v<N>/film.html`,
   or `film/v<N>/film.mp4` when the original has one.
2. Create the new project next to the original, named
   `<original name>_short`:
   `init <new> --images <original>/images --source <original>/storyboard.md`.
   Copy the original's `settings.yaml` and `lessons.md` over the ones `init`
   wrote, and its other files under `sources/` (not `sources/narration/`).
   In the new `settings.yaml`, set `length.min_seconds: 90` and
   `length.max_seconds: 150`.
3. Storyboard: the `Topic:` says it is the short version of the original
   project's film version and names the audience and the message; `Source:` is
   `sources/storyboard.md`. Pick the scenes that carry the main results,
   merge or drop the rest, and keep the title and end scenes. Write new
   narration in plain words for the audience, not cuts of the original
   sentences. Reuse the original images; generate a new one only when no
   original image fits a scene.
4. Run `validate` and get the storyboard approved as in step 2 of the
   workflow, then follow the workflow from step 3 (voice) in the new project. Give each scene
   subagent, as the starting style, the latest `index.html` (or `scene.py`)
   of the original scene the new scene draws on (the one that showed the
   same point or used the same image); its timing calls and its movement
   follow the new narration, and it passes the motion check
   (`references/scenes.md`) like any scene. A clip scene (`Engine: clip`) imports the original's clip
   (`clip.<ext>` in its latest version) with `clip`, or a new one when its
   images or the `video:` size changed. For music, generate a track of the
   new `length`, or copy the original's track into the new `sources/` and
   set `music.file`; `assemble` loops or trims it to the film.

## Phone version (under 1 minute)

A vertical film for a phone, in the form of a YouTube Short. The steps are
the same, with these differences:

- Name the project `<original name>_phone`. In its `settings.yaml` set
  `video.width: 1080`, `video.height: 1920`, `length.min_seconds: 30`,
  `length.max_seconds: 58`, `templates.end.hold_seconds: 1.5`, and
  `credit.margin: h/8` with `credit.corner: [0.5, 0.78, 0.5, 0.12]`, which
  move the credit caption, and the region measured for its colour, away
  from the bottom and right edges.
- One message, three to five scenes of about 10 seconds each. The first
  sentence states the most striking result; the title scene, if kept, shows
  it, and the summary scene is dropped. Short sentences, and a faster voice
  (`voice.speed` 1.1 to 1.2, on a speech model with a speed setting).
- Images: a 16:9 image fills less than a third of a 9:16 frame. Make a 9:16
  version of each original with `media:image-gen`, the original as reference
  image and the same style, or fill the frame height with the original and
  pan across it during the sentence.
- Layout: restyle the scene and template pages for a portrait frame; the
  original pages give the colours and fonts, not the positions. Text is
  larger than the landscape defaults (labels at least 56 px), at most two
  overlays at once, and away from the bottom and right edges, where the
  phone app draws its buttons and the video title. Write these layout
  rules into the new project's `lessons.md`, so every scene subagent gets
  them. The techniques `vertical_feed` and `card_deal` in
  `assets/techniques/` are portrait pages to start from.
