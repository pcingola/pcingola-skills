---
name: short-video
description: "Makes a narrated MP4 from a storyboard: animated scenes timed to a voiceover, with background music. TRIGGER when: user asks for a video, short film, animated explainer, a shorter or phone version of a film, or to animate/narrate images or slides."
allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/short-video.sh:*) Read Skill
metadata:
  version: "0.1.0"
---

# Short video

Output: a numbered MP4 version with animated scenes timed to a voiceover,
music under the voice, and the creator credit. The film is defined by its
storyboard: the scenes in order, each with its narration sentences, what is
on screen during each sentence, and its image or animation brief. The user
may give any part of it (images, a script, source text, animation ideas) or
only a topic; the rest is yours to make.

Each scene is a video clip timed to its narration. The tool makes clips in
two ways: an HTML page rendered by HyperFrames, with the image as background
and overlays driven by a GSAP timeline keyed to sentence and word times
(`references/scenes.md`), or a Manim animation (`Engine: manim`,
`references/manim.md`). A clip made another way, such as an image-to-image
effect from `media:video-effects`, is imported into a scene with
`Engine: clip` (see "Clip scenes and transitions").

The narration comes from `media:voiceover`, the music from `media:music` or
the user; load those skills with the Skill tool when a step needs them.
short-video imports what they produce and checks it against the storyboard.

All commands: `${CLAUDE_SKILL_DIR}/scripts/short-video.sh <command>`. Commands
on a project take `-p <project>`, the project folder (default: the current
directory). Unless the user names another place, the project is
`presentations/<YYYYMMDD>_<name>/` under the current directory. Every file the
tool writes for a project goes inside that folder.

The story is in the project's `storyboard.md` (format:
`references/storyboard.md`). Every setting is in the project's
`settings.yaml`, a copy of `assets/settings.yaml` made by `init`.

## Workflow

The user reviews the storyboard, the prototype scene, the music and the final
film. Write every correction the user makes into `lessons.md` (one dated
line) in the same session, and give `lessons.md` to every agent that builds a
scene.

1. Init: `init <project> [--images DIR] [--source FILE]`. The folder must
   be missing or empty. `init` copies the PNGs (if given) to `images/` and the
   source text to `sources/`, and writes `lessons.md`, `settings.yaml` and a
   `storyboard.md` with the suggested structure, one image scene per PNG.
   Ask the user who the authors are and set `author:` (a list of names) and
   `voice:` in `settings.yaml`. For narration in a real person's voice ("in
   my voice"), set `voice.backend: chatterbox` and `voice.name` to that
   person's cloned voice; `media:voiceover` lists the cloned voices and
   explains how to add one. For several voices, see "Speakers" in
   `references/storyboard.md`.
2. Storyboard: fill `storyboard.md` following `references/storyboard.md`.
   The story comes from what the user gave, or from your research of the
   topic when the user asks for it; save the sources you use under
   `sources/`. A script the user gave goes in word for word; an animation
   idea the user gave becomes that scene's `Brief:`. Every image scene needs
   a PNG in `images/`: the user's, or one generated with `media:image-gen`
   from the scene's content at the frame's aspect ratio (`video:`). Generated
   images of one film share one style from `brand:style`: the prompt starts
   with its style line, then the palette: the film brand's `accent1`,
   `accent2`, `accent3`, `dk1` and `lt1` (from `brand:brand`), else the
   style's default palette. Show the user every image you generate with
   `play`, and replace the ones the user rejects. Run `validate`, fix every
   error, and fix or report each warning.
   Give the user the full path of `storyboard.md` and wait for approval. The
   user edits the file directly; run `validate` after each round.
3. Voice: `script` writes `sources/narration/<scene>/script.txt` (or one
   script per speaker part, see "Speakers" in `references/storyboard.md`)
   for every scene without a voice version and prints each path. Voice each
   script with `media:voiceover` into the directory that holds it
   (`narration.wav`, `timing.json`), with the voice `script` prints under the
   path, else the `voice:` settings. `voice`
   imports each voiced scene as its next voice version; it refuses sentences
   that differ from the storyboard and a part voiced with the wrong voice.
   Play one narration and fix pronunciation by rewording.
4. Prototype: the first image scene, unless the user names another.
   `scaffold --scene ID`, write `scenes/ID/v<N>/index.html` from `brief.md`
   and `references/scenes.md` (a manim scene: `scene.py` and
   `references/manim.md`), `render --scene ID`, and play `scene.mp4`. Revise
   with the user.
5. Remaining scenes, including title, summary and end: one subagent per
   scene, in parallel. Give each the absolute path of
   `${CLAUDE_SKILL_DIR}/scripts/short-video.sh` as the command `short-video.sh`
   in the references, the project path, its `brief.md` path, the prototype's
   page, `references/scenes.md` and `lessons.md`; with `brand:` set, also give the
   title and end subagents the brand folder. Each scaffolds, writes and
   renders its scene. Clip scenes are made as "Clip scenes and transitions"
   describes, not by a scene subagent.
6. Critic, when `critic.claude` is true: a subagent that wrote no scene, given
   `references/critic.md`, the storyboard, the source text, `lessons.md`,
   every latest `contact.png` and `brief.md`, and the `frames` command, plus
   the brand folder when `brand:` is set. Fix what holds and re-render.
7. Music, unless the film is voice only: `length` prints the length to
   request. Generate a track of that length into `sources/` with
   `media:music` (usually instrumental; with Lyria, a scene PNG as image input
   makes music that fits the pictures), or take the user's track. Set `music.file`
   to its path relative to the project and run `music`. Play it, and replace
   it until the user approves. With `music.file` null the film has the voice
   only.
8. Assemble: check every audio track as in `references/audio-check.md`, then
   `assemble [--music vN] [--brand DIR]` and play `film/v<N>/film.mp4`.
   `assemble` adds the creator credit (`references/post-production.md`) and
   refuses to run without `author:`. If the voice is hard to hear, lower
   `mix.music_db` and assemble again. Do the checks in
   `references/post-production.md` before handing the film over.
9. Film critic, when `critic.model` is set (default
   `vertex:gemini-3.1-pro-preview`, a model id of the `ai_models` config).
   Only a Gemini model of a `google` provider in that config takes video.
   Load `ai:second-opinion` and ask
   it to review `film/v<N>/film.mp4`, `storyboard.md` and the source text
   under `sources/`, with `critic.model` as the model and
   `references/critic.md` as the brief. Verify each finding against the film
   (play the time range, or `frames` on the scene), fix the ones that hold,
   assemble again, and tell the user what was found, fixed and dropped.
   When second-opinion stops because the config has no such provider or its
   key is not set, skip this step. Tell the user that the film critic needs a
   Gemini model of a `google` provider in the model config. `critic.model: null` in
   `settings.yaml` turns the step off.

After a later change to `storyboard.md` or `settings.yaml`, redo what "What
an edit needs" in `references/storyboard.md` lists, then `assemble`.
`assemble` uses the latest rendered version of each scene and does not check
it against the storyboard.

## Short version

A shorter film made from an existing one, about 2 minutes or a vertical
phone film under 1 minute, is a new project built as
`references/short-version.md` describes; the original project is not changed.

## Manim scenes

A scene with `Engine: manim` is a Manim Community Edition animation in the
style of 3Blue1Brown instead of an HTML page. Use it only when the user asks
for that style, or approves your proposal for a mathematical or diagrammatic
scene. Its version holds `scene.py` instead of `index.html`; its subagent gets
`references/manim.md`, and `references/scenes.md` for word matching and
style. `render`, `frames`, the critic and `assemble` handle it like any other
scene.

## Clip scenes and transitions

A scene with `Engine: clip` shows a video made outside short-video. Use one to
turn one image into another (a drawing into a photograph of the same scene),
or to join two image scenes with an effect: put a clip scene without a
narration table between them, made from the previous scene's image to the
next scene's image. Such a scene is silent and lasts its clip; with a table
it is narrated like any scene (`references/storyboard.md`).

1. Load `media:video-effects` with the Skill tool and ask it for the clip:
   the start image, the end image or a style prompt, the effect, the
   transformation duration, the holds before and after it, any push-in, and
   the output size and fps equal to `video:` in `settings.yaml`, written
   into `sources/`. Default transformation durations: 3.5 s for a fast-paced
   film, 5.6 to 7 s for a calmer one; 10.5 s is too slow.
2. `clip --scene ID FILE` imports it as the scene's next version. It refuses
   a file whose size or frame rate differs from `video:`; make the clip
   again at those values. The clip's audio is not used (`clip` warns when
   the file has an audio stream). A narrated clip scene needs its voice
   version first: a clip shorter than the narration is held on its last
   frame, a
   longer one sets the scene length.
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
| `init <project> [--images DIR] [--source FILE]` | create the project |
| `validate [--brand DIR]` | check the storyboard, files and settings |
| `script [--scene ID]...` | write the narration scripts of scenes without a voice version, or of the scenes named |
| `voice [--scene ID]... [--src DIR]` | import voiced narration as the next voice version |
| `scaffold --scene ID` | create the next scene version |
| `render --scene ID` | check, render, mux the narration, write the contact sheet |
| `clip --scene ID FILE` | import a video as the next version of a clip scene, mux, contact sheet |
| `frames --scene ID --at 3.2,7.5 [--version vN]` | full-size PNGs at given times |
| `length` | narration length (a clip scene: at least its clip), silent clip length, and the music length to request |
| `music` | import `music.file` as the next music version |
| `assemble [--music vN] [--brand DIR]` | the next film version |
| `audiocheck [FILE...] [--film vN]` | bursts and clicks in each source track; exit 1 if any |
| `credit FILE [-o OUT] --author NAME... [--brand DIR]` | credit caption, logo and tags on any MP4 |
| `setup` | install HyperFrames and GSAP; `render` runs it when needed |
| `play FILE...` | macOS: open images in `play.image_app`, video and audio in `play.app`; Linux: open each file with `xdg-open`; do not use QuickTime or a bare `open` |

## Project layout

```
<project>/
  images/ sources/ lessons.md storyboard.md settings.yaml
  sources/narration/<scene>/   script.txt (or p<k>/script.txt), voiced there
  voice/<scene>/v<N>/   script.txt narration.wav timing.json meta.json
  scenes/<scene>/v<N>/  index.html timing.js timing.json background.png gsap.min.js card.js
                        brief.md voice_version silent.mp4 scene.mp4 contact.png meta.json frames/
  scenes/<scene>/v<N>/  (Engine: manim) scene.py sv_timing.py timing.json background.png
                        brief.md voice_version media/ silent.mp4 scene.mp4 contact.png meta.json frames/
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

- `references/storyboard.md`: storyboard format, speakers, template, manim and clip scenes, what an edit needs.
- `references/scenes.md`: writing an HTML scene, including the title, summary and end scenes.
- `references/manim.md`: writing a manim scene.
- `references/short-version.md`: a 2-minute or a phone version of an existing film.
- `references/critic.md`: critic brief (scene critic and film critic).
- `references/post-production.md`: the creator credit and brand logo, `credit` for other MP4s.
- `references/audio-check.md`: checking the audio tracks.
- `assets/settings.yaml`: every setting with its default.
