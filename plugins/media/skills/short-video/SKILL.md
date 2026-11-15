---
name: short-video
description: "Makes a narrated MP4 film from a storyboard: scenes moving in step with a voiceover, with music. TRIGGER when: user asks for a video, short film, animated explainer, a shorter or phone version of a film, or to animate/narrate images or slides."
allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/short-video.sh:*) Read Skill
metadata:
  version: "0.1.0"
---

# Short video

Output: a numbered MP4 version of a short film narrated by a voiceover, with
music under the voice and the creator credit. The film is a movie: the
explanation is carried by what moves and changes on screen. Every scene shows
continuous movement in step with its sentences, and no stretch of a scene is
still for longer than about 2 s (the last 0.5 s of a scene excepted),
whatever method makes the scene. Still pictures with labels and a
voice are a narrated slide deck and do not count as a film.

The film is defined by its storyboard: the scenes in order, each with its
narration sentences, what moves or changes on screen during each sentence,
and how the scene moves (`Brief:`). The user may give any part of it (images,
a script, source text, animation ideas) or only a topic; the rest is yours to
make. Images the user gives are material for scenes: one image may carry
several shots or scenes. A scene that a picture would not help (a diagram,
chart, map, process or text built with the speech) has no `Image:`: its
HTML page draws everything on screen.

The narration comes from `media:voiceover`, the music from `media:music` or
the user; load those skills with the Skill tool when a step needs them.
short-video imports what they produce and checks it against the storyboard.

All commands: `${CLAUDE_SKILL_DIR}/scripts/short-video.sh <command>`. Commands
on a project take `-p <project>`, the project folder (default: the current
directory). Unless the user names another place, the project is
`presentations/<YYYYMMDD>_<name>/` under the current directory. Every file the
tool writes for a project goes inside that folder.

The story is in the project's `storyboard.md`, or `storyboard.json` in a
project made with `init --json` (format: `references/storyboard.md`). Every setting is in the project's
`settings.yaml`, a copy of `assets/settings.yaml` made by `init`.

## Making a scene

Each scene is a video clip timed to its narration, made by one of four
engines, chosen per scene with `Engine:`: HTML (HyperFrames and GSAP, the
default), Manim, a video model, or a presenter model. HTML, Manim and the
video model are equal options; for each scene, pick the one that can show
the movement its storyboard describes. Use `presenter` only when the user
asks for a talking presenter, never on your own: in a viewing test its mouth
over-articulated and lip sync had gaps, and it took about 23 min per 4 s of
clip on a GB10. Storyboard, narration, music and assembly treat the
four the same; an imported clip is a fifth source:

| method | storyboard | shows well |
|---|---|---|
| HTML page rendered by HyperFrames, a GSAP timeline keyed to sentence and word times (`references/scenes.md`) | `Brief:` with an optional `Image:`, or `Template:` | camera moves across a picture, layers moving over it, shapes and diagrams drawn, numbers counting, text built with the speech; without `Image:`, a diagram, chart, map or text drawn on a plain background |
| Manim animation in the style of 3Blue1Brown (`references/manim.md`) | `Engine: manim` | mechanisms, quantities, processes, transformations of diagrams and equations |
| video model animating the scene's image from a motion prompt (`references/video-model.md`) | `Engine: video` with `Image:` and `Brief:` | natural motion of a photographic or painted picture: water, smoke, crowds, a living cell, a slow camera move through a scene |
| presenter model making the person in the scene's image speak the scene's narration recording (`references/video-model.md`, "Presenter scenes") | `Engine: presenter` with `Image:` (a portrait) and an optional `Brief:` | a host or narrator on screen: lips, head and hands moving with the words |
| imported clip (see "Clip scenes") | `Engine: clip` | a morph or style change from `media:video-effects`, generated video, the user's footage |
| HTML page over a background video ("Background video" in `references/scenes.md`) | `Image:` | a moving picture with drawn shapes, labels and camera moves on top |

Motion check: after `render` (or `clip`), the agent that made the scene runs
`frames` at one per second across the scene and compares frames 2 s apart.
Each pair differs in a way a viewer sees: a new framing (the view has moved
by at least about 10% of the frame), or a new drawn, flowing or counting
element. A slow drift that changes a few pixels fails; the last 0.5 s is
excepted. The check covers the whole scene, its middle and any hold
included: put each frame next to the one 2 s later; when neither the view
nor any object moved by about a tenth of the frame width and no new element
appeared, the pair fails. The contact sheet's thumbnails are too small to
judge it. A scene that fails is made again with more movement, or with
another method, and is not done until it passes. A fix found while looking
at frames edits the page (or `scene.py`) and runs `render` again on the same
version; `scaffold` makes a new version only when the storyboard, the image
or the voice changed.

## Workflow

The user reviews the storyboard, the prototype scene, the music and the final
film. Write every correction the user makes into `lessons.md` (one dated
line) in the same session, and give `lessons.md` to every agent that builds a
scene.

1. Init: `init <project> [--images DIR] [--source FILE]`. The folder must
   be missing or empty. `init` copies the PNGs (if given) to `images/` and the
   source text to `sources/`, and writes `lessons.md`, `settings.yaml` and a
   `storyboard.md` with the suggested structure and one draft image scene
   per PNG, to merge, split or replace while writing the storyboard.
   Set `author:` (a list of names) to the authors the user names, and set
   `voice:` in `settings.yaml`. An empty `author:` gives a film without a
   creator credit. For narration in a real person's voice ("in
   my voice"), set `voice.backend: chatterbox` and `voice.name` to that
   person's cloned voice; `media:voiceover` lists the cloned voices and
   explains how to add one. For several voices, see "Speakers" in
   `references/storyboard.md`.
2. Storyboard: fill `storyboard.md` following `references/storyboard.md`.
   The story comes from what the user gave, or from your research of the
   topic when the user asks for it; save the sources you use under
   `sources/`. A script the user gave goes in word for word; an animation
   idea the user gave goes into that scene's `Brief:`. Each scene's `Brief:`
   says how it moves and its method ("Making a scene"); each On screen cell
   says what moves or changes during its sentence. Every scene with `Image:` needs
   a PNG in `images/`: the user's, or one generated with `media:image-gen`
   from the scene's content at the frame's aspect ratio (`video:`), written
   into the project's `images/` whatever output directory `media:image-gen`
   names by default. Generated images of one film share one style from
   `brand:style`: the prompt starts with its style line, then the palette:
   the film brand's `accent1`, `accent2`, `accent3`, `dk1` and `lt1` (from
   `brand:brand`), else the style's default palette. A style line governs
   the look of the picture only; where it says to avoid camera moves or
   similar, the film's movement still follows this skill. Show the user every image you generate with
   `play`, and replace the ones the user rejects. Run `validate`, fix every
   error, and fix or report each warning.
   Give the user the full path of `storyboard.md` and, per scene, its
   method and what moves, and wait for approval. The user edits the file
   directly; run `validate` after each round.
3. Voice: `script` writes `sources/narration/<scene>/script.txt` (or one
   script per speaker part, see "Speakers" in `references/storyboard.md`)
   for every scene without a voice version and prints each path. Voice each
   script with `media:voiceover` into the directory that holds it
   (`narration.wav`, `timing.json`), with the voice `script` prints under the
   path, else the `voice:` settings. `voice`
   imports each voiced scene as its next voice version; it refuses sentences
   that differ from the storyboard and a recording in the wrong voice.
   Play one narration and fix pronunciation by rewording.
4. Prototype: the first scene without `Template:`, unless the user names
   another. `scaffold --scene ID`, write `scenes/ID/v<N>/index.html` from
   `brief.md` and `references/scenes.md` (a manim scene: `scene.py` and
   `references/manim.md`; a video scene: `prompt.txt` and
   `references/video-model.md`), `render --scene ID` (a video or presenter
   scene: with the `--model` of its row, Model routes), and do the motion check.
   Make it again until it passes, then play `scene.mp4` and revise with the
   user. The remaining scenes are made from it only after it passes.
5. Remaining scenes, including the template scenes: one subagent per
   scene, in parallel. Give each the absolute path of
   `${CLAUDE_SKILL_DIR}/scripts/short-video.sh` as the command `short-video.sh`
   in the references, the project path, its `brief.md` path, the prototype's
   page, `references/scenes.md` (a manim scene: also `references/manim.md`;
   a video scene: `references/video-model.md` instead),
   `lessons.md`, and the motion check: `frames` at one per second across
   the scene, and every two frames 2 s apart differ visibly, by a new
   framing (the view moved by about 10% of the frame or more) or a new
   drawn, flowing or counting element (the last 0.5 s excepted); the scene
   is done only when it passes. For each video or presenter scene, pick its
   row as "Model routes" says and give its subagent the `--model ID` to pass
   to `render`, or none for the default row. A subagent whose clip lacks the
   motion its Brief asks for reports it; then pick again (an escalation row
   may now hold) and give it the new `--model`. With `brand:` set, also
   give the title and end subagents the brand folder. Each scaffolds, writes
   and renders its scene. Clip scenes are made as "Clip scenes" describes,
   not by a scene subagent.
6. Scene critic, only when `critic.claude` is true (default false): a
   subagent that wrote no scene, given `references/critic.md`, the
   storyboard, the source text, `lessons.md`, every latest `brief.md` and
   the `frames` command. Fix what holds and re-render.
7. Music, unless the film is voice only: `length` prints the length to
   request. Generate a track of that length into `sources/` with
   `media:music` (usually instrumental; with Lyria, a scene PNG as image input
   makes music that fits the pictures), or take the user's track. Set `music.file`
   to its path relative to the project and run `music`. Play it, and replace
   it until the user approves. With `music.file` null the film has the voice
   only.
8. Assemble: check every audio track as in `references/audio-check.md`, then
   `assemble [--music vN] [--brand DIR]` and play `film/v<N>/film.mp4` to
   the user before the critic starts, so the user watches it while the
   critic runs.
   `assemble` adds the creator credit (`references/post-production.md`)
   when `author:` names someone. If the voice is hard to hear, lower
   `mix.music_db` and assemble again. Do the checks in
   `references/post-production.md` before handing the film over.
9. Film critic: `critic` prints its model (task `film_critic` of the model
   config, or `critic.model` of `settings.yaml`), or `off`.
   Only a Gemini model of a `google` provider in that config takes video.
   Load `ai:second-opinion` and ask
   it to review `film/v<N>/film.mp4`, the storyboard file (`storyboard.md`
   or `storyboard.json`) and the source text
   under `sources/`, with that model,
   `references/critic.md` as the brief and at most `critic.max_findings`
   findings. Verify each finding against the film with `frames` on the scene
   that holds its time range: a scene starts in the film at the sum of the
   earlier scenes' `duration` in `film/v<N>/manifest.json`. Fix the ones that hold together with the user's
   feedback on the film, assemble once, and tell the user what was found,
   fixed and dropped. That is one round; `critic.rounds` sets how many run,
   and no review follows the last.
   When `critic` prints `off`, skip this step. When `critic` fails (no
   `film_critic` task) or second-opinion stops because the config has no such
   provider or its key is not set, skip this step and tell the user that the
   film critic needs task `film_critic` set to a Gemini model of a `google`
   provider in the model config. `critic.model: null` in `settings.yaml` turns
   the step off.

After a later change to the storyboard or `settings.yaml`, `status` lists the
scenes that need a new voice or render; redo what "What an edit needs" in
`references/storyboard.md` lists, then `assemble`.
`assemble` uses the latest rendered version of each scene and does not check
it against the storyboard.

## Short version

A shorter film made from an existing one, about 2 minutes or a vertical
phone film under 1 minute, is a new project built as
`references/short-version.md` describes; the original project is not changed.

## Manim scenes

A scene with `Engine: manim` has `scene.py` in its version instead of
`index.html`; its subagent gets `references/manim.md`, and
`references/scenes.md` for word matching and style. `render`, `frames`, the
critic and `assemble` handle it like any other scene.

## Video scenes

A scene with `Engine: video` has `prompt.txt` in its version instead of
`index.html`: the motion prompt a video model animates the scene's image
with. Make the image with `media:image-gen` as for an HTML scene, at the
aspect ratio of `video:`. `render --scene ID [--seed N]` calls the model of
task `video` in the settings file `config.yaml` for the narration's length;
a clip shorter than the narration holds its last frame to the end, a longer
one is cut there. A sound track the model generates is mixed under the
narration, `mix.ambience_relative_db` LU from the narration's loudness, unless the scene has `Ambience: off`. Its
subagent gets `references/video-model.md`. `frames`,
the critic and `assemble` handle it like any other scene.

## Presenter scenes

A scene with `Engine: presenter` has no page or prompt file: `render --scene
ID [--seed N]` sends the scene's image (a portrait made with
`media:image-gen`) and its voice version's `narration.wav` to the model of
task `presenter` in `config.yaml`; the person in the image speaks the
recording, for its whole length. A scene gets this engine only when the
user asks for a talking presenter ("Making a scene"). The `Brief:`, when given, replaces the
model's own prompt. `status` asks for a new render when the image or the
recording changes. Its subagent gets `references/video-model.md`.

## Model routes

Before each model call, run `${CLAUDE_SKILL_DIR}/scripts/short-video.sh routes`.
It prints, per task of this skill, `| task | model | when | why |` rows
from the user's `routes.md` beside `config.yaml`: first the task's default
row (`when` is `default`, the model is the task's model in `config.yaml`,
and `why` names the table's recommended model when it differs), then the
escalation rows, without the rows whose model `config.yaml` lacks. Without
the file it prints only the default rows. Use the default row and pass no
`--model`. Take a later row, and pass its `model` with `--model`, only
when its `when` condition holds for the request; the first such row wins.
A model that the user or a calling skill names is passed as given, without
the table.

The task of `render` is `video` for a scene with `Engine: video` and
`presenter` for a scene with `Engine: presenter`; `render --model ID` passes
the row's model. The main agent picks the row of each such scene (Workflow,
steps 4 and 5).

## Clip scenes

A scene with `Engine: clip` shows a video made outside short-video: a morph
or style change from `media:video-effects` (a drawing turning into a
photograph of the same scene), a generated video, or the user's footage. A
clip scene without a narration table between two scenes joins them with an
effect, made from the previous scene's image to the next scene's image; it is
silent and lasts its clip. With a table it is narrated like any scene
(`references/storyboard.md`).

1. Make the clip at the size and fps of `video:` in `settings.yaml`, written
   into `sources/`. For an effect, load `media:video-effects` with the Skill
   tool and ask it for the clip: the start image, the end image or a style
   prompt, the effect, the transformation duration, the holds before and
   after it (each shorter than about 2 s), and any push-in. A narrated clip
   is made at least as long as its narration (`length` gives it), so it
   never ends in a frozen frame. Default transformation durations: 3.5 s
   for a fast-paced film, 5.6 to 7 s for a calmer one; 10.5 s is too slow.
2. `clip --scene ID FILE` imports it as the scene's next version; do the
   motion check on it. It refuses a file whose size or
   frame rate differs from `video:`; make the clip again at those values.
   The clip's audio is not used (`clip` warns when the file has an audio
   stream). A narrated clip scene needs its voice version first: a clip
   shorter than the narration is held on its last frame, and a longer one
   sets the scene length.
3. Play `scene.mp4`. `frames`, the critic, `length` and `assemble` handle it
   like any other scene; `scaffold` and `render` refuse it.

## Brand logo

With `brand: <name>` in `settings.yaml`, `assemble` puts the brand's logo
beside the credit caption, and the title and end scenes show it. Load
`brand:brand` for the list of brands, pick one whose `brand.yaml` has `raster`
and `caption`, set `brand:`, and ask the brand skill for that brand's folder.
Pass the folder as `--brand DIR` to `validate` and `assemble`; its name must
be the `brand:` value.

## Commands

| command | does |
|---|---|
| `init <project> [--images DIR] [--source FILE] [--json]` | create the project; `--json`: `storyboard.json` |
| `validate [--brand DIR]` | check the storyboard, files and settings |
| `storyboard` | print the storyboard as `storyboard.json` stores it |
| `status` | per scene, JSON: whether it needs a new voice or render, and why |
| `script [--scene ID]...` | write the narration scripts of scenes without a voice version, or of the scenes named |
| `voice [--scene ID]... [--src DIR]` | import voiced narration as the next voice version |
| `scaffold --scene ID` | create the next scene version |
| `render --scene ID [--seed N] [--model ID]` | check, render (a video or presenter scene: call the model, `--seed` its seed, `--model` replaces the task's model), mux the narration, write the contact sheet |
| `routes [--task video\|presenter]` | the model routes of the video and presenter tasks (Model routes) |
| `clip --scene ID FILE` | import a video as the next version of a clip scene, mux, contact sheet |
| `frames --scene ID --at 3.2,7.5 [--version vN]` | full-size PNGs at given times |
| `length` | narration length (a clip scene: at least its clip), silent clip length, and the music length to request |
| `critic` | the film critic's model (task `film_critic` of the model config, or `critic.model`), or `off` |
| `music` | import `music.file` as the next music version |
| `assemble [--music vN] [--brand DIR]` | the next film version |
| `audiocheck [FILE...] [--film vN]` | bursts and clicks in each source track; exit 1 if any |
| `credit FILE [-o OUT] --author NAME... [--brand DIR]` | credit caption, logo and tags on any MP4 |
| `setup` | install HyperFrames and GSAP; `render` runs it when needed |
| `play FILE...` | macOS: open images in `play.image_app`, video and audio in `play.app`; Linux: open each file with `xdg-open`; do not use QuickTime or a bare `open` |

## Project layout

```
<project>/
  images/ sources/ lessons.md storyboard.md (or storyboard.json) settings.yaml
  sources/narration/<scene>/   script.txt (or p<k>/script.txt), voiced there
  voice/<scene>/v<N>/   script.txt narration.wav timing.json meta.json
  scenes/<scene>/v<N>/  index.html timing.js timing.json background.png (with Image:) gsap.min.js card.js
                        brief.md voice_version silent.mp4 scene.mp4 contact.png meta.json frames/
  scenes/<scene>/v<N>/  (Engine: manim) scene.py sv_timing.py timing.json background.png (with Image:)
                        brief.md voice_version media/ silent.mp4 scene.mp4 contact.png meta.json frames/
  scenes/<scene>/v<N>/  (Engine: video) prompt.txt background.png timing.json brief.md voice_version
                        model.mp4 silent.mp4 scene.mp4 contact.png meta.json frames/
  scenes/<scene>/v<N>/  (Engine: presenter) background.png timing.json brief.md voice_version
                        model.mp4 silent.mp4 scene.mp4 contact.png meta.json frames/
  scenes/<scene>/v<N>/  (Engine: clip) clip.<ext> brief.md silent.mp4 scene.mp4 contact.png meta.json frames/
  music/v<N>/           music.<ext> meta.json lyrics.txt
  film/v<N>/            film.mp4 manifest.json
```

Version numbers are never reused. `scaffold`, `voice`, `clip`, `music` and
`assemble` each write a new version; `render` rewrites the outputs of the
latest scene version; the other commands write no version.

Scenes are joined back to back; a template scene with `hold_seconds` runs
that long past its narration. The music is looped and trimmed to the film,
faded, ducked under the voice, and the mix is loudness-normalised. Levels and
timings are under `mix:` in `settings.yaml`.

## References

- `references/storyboard.md`: storyboard format, describing movement, speakers, voice settings, storyboard.json, template, manim, video and clip scenes, scene status, what an edit needs.
- `references/scenes.md`: writing an HTML scene and its movement, including the title, summary and end scenes.
- `references/manim.md`: writing a manim scene and its movement.
- `references/video-model.md`: writing a video scene's motion prompt and checking its clip.
- `references/short-version.md`: a 2-minute or a phone version of an existing film.
- `references/critic.md`: critic brief (scene critic and film critic).
- `references/post-production.md`: the creator credit and brand logo, `credit` for other MP4s.
- `references/audio-check.md`: checking the audio tracks.
- `assets/settings.yaml`: every setting with its default.
