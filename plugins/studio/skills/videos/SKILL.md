---
name: videos
description: "Carries out Studio page requests on short-video projects: storyboard, scene pictures and styles, voices, music, the film, its review and phone version. TRIGGER when: a prompt carries a Studio request JSON naming studio:videos."
allowed-tools: Skill Read Write Glob
metadata:
  version: "0.1.0"
---

# Studio Videos

The Studio page in the user's browser sends each action on a short-video project as a request JSON inside a prompt
that names `studio:videos`. This skill defines the project format and how to carry out each request `action`.
The film is made by loading `media:short-video` with the Skill tool and running its commands with `-p <project>`;
scene pictures are made with `media:image-gen`, styles come from `brand:style`, brands from `brand:brand`, tracks
from `media:music` and voice samples from `media:voiceover`. Every answer goes to the page through the
`mcp__studio__note` and `mcp__studio__post` tools.

Load `studio:images` with the Skill tool for every request that makes a scene picture: its "Building a prompt"
section builds each picture's prompt, its `change`, `variations` and `other-styles` steps make the pictures of those
actions, its rules for `"auto"` and `"invent"` styles choose or invent styles, and its Autonomy check applies to new
pictures. Its project files and its `generate` action do not apply; the files are those below.

## Project files

A project is the request's `project` directory (absolute). Every file this skill writes is inside it; the user's
files, brand files and style samples are read in place.

| File | Content |
|---|---|
| `project.json` | `brief`, `kind`, `created`, `autonomy`, `film`, `scene_styles` and `origin` are the server's and kept as found; this skill writes `name` (the storyboard's `title`, after each `storyboard`, unless `named` is true: the user renamed the project in the page), `settings` (the last `storyboard` request's `brief`, `refs`, `sources`, `style`), `style` (`{"name"}`, plus `invented` with `name`, `description`, `style_line`, `palette` for an invented style; null before one is chosen) and `samples` (`{"scene", "versions": [N, N, N], "style": "auto" \| "invent"}` while the user is to pick a style; absent otherwise) |
| `storyboard.json` | the storyboard, in the structure `media:short-video` defines for `storyboard.json` |
| `settings.yaml` | `media:short-video` settings: only the keys of [settings.yaml](#settingsyaml) |
| `status.json` | the state of each scene ([status.json](#statusjson)) |
| `lessons.md` | `media:short-video`'s lessons file; created with the first storyboard |
| `refs/`, `sources/` | the user's pictures and sources, written by the page; research sources this skill saves go in `sources/`, generated tracks in `sources/music/` |
| `images/<scene>/v<N>.png`, `v<N>.json` | picture N of scene `<scene>`, numbered from 1 within the scene's directory, never overwritten; the sidecar has the fields of a `studio:images` version sidecar, with `kind` `"short-video"`, `model` `best` (image-gen's tier), `model_id` the `<provider>:<model>` of the task that made it (`image_best`, from the request's `models`), `shape` the film's and `brand` the film's; written after the PNG |
| `images/<scene>/marks/` | marked copies and edit masks, written by the page |
| `voice/`, `scenes/`, `music/v<N>/`, `film/v<N>/` | `media:short-video`'s versions, written by its commands |
| `music/v<N>/studio.json` | `source` (`made` or `own`), `brief` (the request's; `""` for an own track), `note` (one line on how it sounds), `duration` (seconds), `created`; written after the `music` command imported the version |
| `film/v<N>/studio.json` | `changes` (one line: what is new since the previous film), `created`; written after the film is checked |
| `film/v<N>/review.json` | the film critic's findings on film N that hold: `{"created", "model": <the critic's model>, "findings": [{"k": 1, "start": <s>, "end": <s>, "problem": "...", "change": "..."}]}`, `k` numbered from 1, `start` and `end` film time in seconds, `findings` `[]` when none holds; written whole by each review ([Film review](#film-review)) |
| `samples/voice-<k>/narration.wav`, `samples/voice-<k>.json` | voice samples, k from 1, never overwritten; the directory is `media:voiceover`'s output directory; the sidecar, written after the WAV: `voice` (`backend`, `name`, `speed`, `style`), `text`, `created` |

- `created` is the request's `time`.
- `project.json` and `storyboard.json` are read right before each write and rewritten whole; only what the request
  asks changes, every other key keeps its value. The page writes both at any time.
- Never run `media:short-video`'s `init`: this skill writes `settings.yaml`, `storyboard.json` and `lessons.md`.
  A project whose storyboard is Markdown was made in the terminal: post that Studio cannot work on it and end the turn.
- Picture numbering: Glob `images/<scene>/v*.json` and `v*.png`; the next N is one more than the highest (1 when
  there is none). Several pictures of one scene reserve consecutive numbers before the first generation starts.
- A scene uses picture N when its `image` is `<scene>/v<N>.png`. Making a picture the scene's picture is a write of
  that `image` to `storyboard.json`.

### Scenes

- `id`: `[a-z0-9_]+`, unique, reading as the scene's title (`the_injection`; the page shows it with `_` as spaces).
  A new scene never gets an id that has a directory under `images/`, `voice/` or `scenes/`. A scene kept by a
  rewrite keeps its id. The page creates no ids.
- The film moves as `media:short-video` requires: each scene's beats and `brief` say what moves during each sentence,
  and each scene's kind (image, drawn, template, manim or clip scene) is chosen by `media:short-video`'s rules from
  the movement it shows. Image and template scenes get a picture: a template scene's picture is its background.
- `engine` picks what animates a scene that is neither a template nor a clip: `html` (HyperFrames, also when absent),
  `manim`, or `video` (the config task `video` animates the scene's picture from its `brief`, the prompt). A video
  scene gets a picture like an image scene. The page sets `engine`; an engine the user set is kept by every request
  except a new storyboard. The request's `models` names each task's model; with `models.video` null, no scene gets
  `engine` `video`.
- A drawn scene is an HTML scene without `image` (no `template`, `engine` absent or `html`): written where a picture
  would not help the point, such as a diagram, chart, map, process or text built with the speech. Its `brief` says
  what the page draws and how it moves. It gets no picture: every step below that makes pictures for "every scene",
  "every scene with a picture" or "the first scene" leaves drawn scenes out, and the style samples are made on the
  first scene in the film that gets a picture.
- A scene's picture shows what its narration is about, with no text unless the scene's `brief` needs text in the
  picture; the On screen text is drawn by the scene. The sidecar's `scene` is that description.
- "The scene's style" is its `scene_styles` entry, else the film's `style`. Any catalogue style may be offered or picked
  for a film; `suits` is one of the things compared when choosing, never a filter.
- The narration fits `film.length` at about 2.5 words per second.

### settings.yaml

Before each `media:short-video` command of a request, write `settings.yaml` from the request's `film` (else
`project.json`'s `film`), keeping `music.file` and the phone keys as found:

| `film` | `settings.yaml` |
|---|---|
| `voice` | `voice.backend`, `voice.name`, `voice.speed`, `voice.style` |
| `music.mode` `none` | `music.file: null` |
| `music.volume` | `mix.music_db`: `quiet` -20, `normal` -14, `louder` -9 |
| `shape` | `video.width` and `video.height`: `16:9` 1920 by 1080, `9:16` 1080 by 1920 |
| `length` | `length.min_seconds` 0.75 and `length.max_seconds` 1.25 times it; in a project with `origin` and `shape` `9:16`, the phone-version limits of `media:short-video` |
| `author` | `author` |
| `brand` | `brand` |
| `review` | `critic.claude` false always (Studio never runs the scene critic); `review` false: `critic.model` null; `review` true: `critic.model` not written, so `media:short-video`'s default film critic runs |

`music.file` is set to the track's path right before each `music` command. A phone version also holds
`templates.end.hold_seconds`, `credit.margin` and `credit.corner` with the values `media:short-video`'s phone
version gives. No other key is written; the commands take their defaults for the rest.

With `brand` set, ask `brand:brand` for the brand's folder and pass it as `--brand DIR` to `validate` and
`assemble`. Run `validate` before every other command; fix each error in the project's files, or post it. While `samples` is
present, its errors for pictures not made yet are expected.

### status.json

After every request that changes `storyboard.json`, a scene's picture, a recording or a clip, run `status` and write:

```json
{"created": "<request time>", "film": {<the film settings settings.yaml was written from>},
 "speakers": {<speakers of storyboard.json>} | null,
 "scenes": {"<scene>": {"state": "voice" | "render" | "ready", "basis": {<the scene object of storyboard.json>}}}}
```

Per scene: `voice` when `status` reports `needs_voice`, else `render` when it reports `needs_render`, else `ready`.
`basis` is the scene exactly as `storyboard.json` held it when `status` ran.

## Actions

Every request is carried out exactly as given. Read `project.json` first. Send a `note` at each step that takes
time (storyboard written, each picture, each recording and render, music, assembly).

### storyboard

Fields: `brief`, `refs`, `sources`, `style`, `film` (already in `project.json`), `make_film` (optional; true: this
request is carried out as in `auto` autonomy, whatever `autonomy` says, and `autonomy` is not changed).

1. Set `settings` in `project.json` to `brief`, `refs`, `sources`, `style`.
2. Write the story with `media:short-video`'s storyboard step from the `brief`, the reference pictures and the
   files in `sources` (research only when the brief asks for it; save what is used in `sources/`). A script in the
   brief goes in word for word. `source` is the main source file when there is one. Replace `storyboard.json`
   whole, following [Scenes](#scenes); keep the old storyboard's `speakers` when it has them. Each scene with a
   picture has as `image` the path of the number reserved for its next picture, made or not. Create `lessons.md`
   when missing. Unless `named` is true, set `name` in `project.json` to the storyboard's `title` (a short title, not the brief's first
   words).
3. Pictures, by `style`:
   - a style name: set `style` to it and make every scene's picture in its style.
   - `"auto"` or `"invent"`, `step` autonomy: three styles, chosen or invented as `studio:images` does for an image,
     one picture each of the first scene of the film that gets a picture, as its versions; set `samples` to that scene, the three N and
     `style`. No other picture is made. The scene's `image` is left as it is until `use-style`; in a new storyboard it is the reserved path of the first sample.
     When no scene gets a picture (every scene drawn, manim or clip), no samples: one style is chosen or invented
     as in the next branch and set as `style`.
   - `"auto"` or `"invent"`, `auto` autonomy or `make_film`: one style chosen or invented the same way, set as `style`, every
     scene's picture made in its style.
4. Write `settings.yaml`, run `validate`, write `status.json`.
5. `auto` autonomy or `make_film`: go on as [make-film](#make-film).
6. Post: the title, per scene its number, title and sentences, the style (with the samples: each style's name and
   why it was chosen, or its description when invented), and the pictures as `images`.

### use-style

Exactly one of `version` and `style`.

- `version` (one of `samples.versions`): post a problem when `samples.scene` is no longer a scene. The film's
  `style` becomes that sample's `style` (with its `invented`); the sample becomes the picture of `samples.scene`;
  remove `samples`; every other scene with a picture and without its own style gets a new picture in it.
- `style` (a catalogue name): the film's `style` becomes it; every scene with a picture and without its own style
  gets a new picture in it, used by the scene.

Then `status.json`, and post the style and the new pictures.

### style-samples

Field: `style` (`"auto"` or `"invent"`). In `step` autonomy, as step 3 of `storyboard` with that style, on the scene
first in the film now among those that get a picture; that scene keeps its picture. In `auto` autonomy, as the `auto` branch of that step: one style
chosen or invented, set as `style`, a new picture in it for every scene with a picture and without its own style,
used by the scene; then `status.json` and [make-film](#make-film).

### change, variations, other-styles

Fields: `scene` and those of the `studio:images` action of the same name, carried out with its steps inside
`images/<scene>/` (`version`, `marked` and `mask` are files of that directory). For `other-styles` with empty
`styles`, the three styles are chosen as in `storyboard` with `"auto"`, other than the version's. A `change` makes the
new picture the scene's picture, then `status.json`; `variations` and `other-styles` leave the scene's picture as it
is. Post the new pictures with their numbers.

### add-scene

Fields: `after` (a scene id, or null for the end), `text`. Write a new scene after `after` (at the end for null) with
a new id, its narration, beats and brief from `text`, and its picture in the film's style (made, then used); a drawn
scene gets no picture.
`status.json`; post the scene's number, title and picture.

### remake-scene

Fields: `scene`, `film`. Write `settings.yaml` from `film`, run `validate` and `status`, and redo for that scene
what `media:short-video`'s "What an edit needs" lists for the reasons `status` gives: a new recording with its voice
step, a new render with its scaffold and render steps, a new clip as it says for clip scenes. Then `status.json`, and
post the scene's clip path and its `contact.png` as `images`.

### music

Fields: `brief`, `film`. Write `settings.yaml`, run `length` for the music length, make a track of that length with
`media:music` from `brief` into `sources/music/`, set `music.file` to it (relative to the project), run `music`,
and write `music/v<N>/studio.json` with `source: "made"`. Post the version number, length and note.

### own-music

Field: `file` (in `sources/`). Set `music.file` to it, run `music`, and write `studio.json` with `source: "own"`,
`brief: ""`, `note` and `duration` from `media:music`'s analysis of the imported track, with `music/v<N>/analysis/`
as its output directory (inside the version, apart from the user's sources). Post the version number.

### voice-sample

Field: `voice`. Voice "This is how the narration of your film will sound in this voice." with `media:voiceover` in
that voice with `samples/voice-<k>/` as its output directory (k: one more than the highest among `samples/voice-*`),
then write `samples/voice-<k>.json`. Post the path of `narration.wav`.

### make-film

Field: `film`. Follow `media:short-video`'s workflow from its voice step, with Studio's answers to its gates:

1. Write `settings.yaml` from `film`; run `validate` and `status`.
2. Record and render each scene `status` reports as needing it (voice step, then the scene steps; the remaining
   scenes in parallel subagents as it says), with `lessons.md`. The prototype is not reviewed with the user and no
   file is opened with `play`; it and every other scene pass `media:short-video`'s motion check, and a scene that fails
   it is made again with more movement.
3. The music version: `music_used` is null for `music.mode` `none`; otherwise, among the complete music versions
   whose `studio.json` `source` is the mode, `music.version` when it is one of them, else the newest. With mode
   `made` and none, make one as the `music` request does from `music.brief` (the topic when it is empty).
4. Run the audio check and `assemble` (`--music v<N>` of `music_used`; without it for `none`), then the checks
   `media:short-video` lists before hand-over. When one fails, in every autonomy and whatever `film.review`, fix it
   and `assemble` once more; that film is film N below. The scene critic never runs.
5. Write `film/v<N>/studio.json` and `status.json`.
6. Post film N at once, so the user watches it: its path, length, music version and `changes`, with the scenes'
   `contact.png` as `images`.
7. Only when `film.review` is true, in the same turn: [Film review](#film-review) of film N. Then, by `autonomy`:
   - `step`: post the findings that hold (as `review` does); nothing is fixed.
   - `auto`: when a finding holds, fix the findings that hold as [fix](#fix) does from step 2 (one assembly;
     `changes` names the fixes); that film is not reviewed. With none, post that the review found nothing; no new
     film is made.

An empty `film.author` gives a film without a creator credit; it does not stop the work.

### Film review

Of film N: write `settings.yaml` as for `film.review` true, whatever `film.review` is, so `critic.model` takes
`media:short-video`'s default. Ask `media:short-video` for one run of its film critic step on `film/v<N>/film.mp4`
(at most `critic.max_findings` findings), and verify each finding against the film as that step says; fix nothing.
Write the findings that hold to `film/v<N>/review.json`, numbered `k` from 1 in the critic's order, with `created`
the request's `time` and `model` the critic's model.

### review

Field: `version` (film N of this project). [Film review](#film-review) of film N, then post the findings that hold
as a list, one line each: time range, what is wrong, what to change ("no findings" when none holds). Nothing is fixed
or assembled, and no file other than `review.json` is written.

### fix

Fields: `version` (film N of this project), `findings` (the `k` of the findings of film N's `review.json` the user
kept, possibly empty), `note` (the user's text, possibly empty), `film`.

1. Write `settings.yaml` from `film`; run `validate` and `status`.
2. Fix the kept findings and the note together, as `media:short-video`'s "What an edit needs" says for each change:
   edit `storyboard.json` or a scene's files, and re-record or re-render only the scenes they touch, each passing the
   motion check of make-film step 2. A correction of the film is added to `lessons.md` as one dated line.
3. Run the audio check and `assemble` once, as make-film step 4.
4. Write `film/v<N>/studio.json` of the new film (`changes`: the fixes, in one line) and `status.json`.
5. Post the film as make-film step 6, with what was fixed and any finding or note that could not be. The new film is
   not reviewed.

### phone

Fields: `version` (film N of this project), `target` (the new project, with its `project.json` made by the server).
Build film N's phone version in `target` as `media:short-video`'s short-version and phone-version steps say, with
the original read in place and never changed. The message and audience are the original film's (its `topic` and
`project.json` `brief`); nothing is confirmed with the user. The voice is `film.voice` as the server copied it, with
no speed change.

1. Copy the original's `lessons.md` and `storyboard.json` (as `sources/storyboard.json`, the new `source`); write
   `settings.yaml` with the phone keys.
2. Write the new `storyboard.json` (3 to 5 scenes, one message, new ids where scenes merge), and each picture as a
   9:16 version of the original scene's picture, made with the original as reference image in that picture's style
   (its sidecar's `style`, and `invented` when present), as `images/<scene>/v<N>.png` in `target`.
3. The music is `target`'s `music/v1/`, the server's copy of the track film N used (`film.music.version` 1); none
   for a film without music.
4. `status.json`, then [make-film](#make-film) in `target`, in either autonomy.

### message

Field: `text`; optionally `scene`; `project` may be null. Answer with `post`. Work the message asks for is done with
the rules of the action it matches; a message with `scene` changes that scene (its sentences, beats, brief or
picture). A correction of the film is added to `lessons.md` as one dated line. With `project` null and work asked
for, post that a project has to be opened first.

## Answering

- Progress: `mcp__studio__note` with one short line. During `make-film` the page shows the latest note as progress.
- Result: `mcp__studio__post` with `text` and `images` (absolute paths of new pictures or contact sheets).
- Failure: post the error text and what was not made; what succeeded is kept and posted.
- A prompt may first say that the user stopped earlier requests in the page: their work is not continued, and what
  they made is kept as it is.
- Questions: never asked in the terminal. A request that cannot be carried out as given (a scene, version or file
  that does not exist, a style or brand not found) is answered with the problem in `post`, and the turn ends.

## Autonomy

`autonomy` in `project.json`, read again before each step that would go further:

- `step`: make what the request asks (for `phone`, the phone film), post it and end the turn.
- `auto`: as `step`, except that `storyboard` and `style-samples` go on to the finished film without waiting. New
  pictures are viewed (Read) and checked as `studio:images`'s Autonomy says.

## Rules

- Writes go only inside the request's `project` (for `phone`, `target`).
- No version file is overwritten; every picture, recording, clip, track and film is a new version.
- The skills loaded here are given a task in prose: what to make, the inputs and the output path.
