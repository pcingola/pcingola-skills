---
name: videos
description: "Carries out Studio page requests on short-video projects: storyboard, scene pictures and styles, voices, music, the film, its review and phone version. TRIGGER when: a prompt carries a Studio request JSON naming studio:videos."
allowed-tools: Skill Read Write Glob Agent
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
| `project.json` | `brief`, `kind`, `created`, `autonomy`, `film`, `scene_styles` and `origin` are the server's and kept as found; this skill writes `name` (the storyboard's `title`, after each `storyboard`, unless `named` is true: the user renamed the project in the page), `settings` (the last `storyboard` request's `brief`, `refs`, `sources`, `style`), `style` (`{"name"}`, plus `invented` with `name`, `description`, `style_line`, `palette` for an invented style, and `page_style` once the film has a drawn scene ([Page style](#page-style)); null before one is chosen) and `samples` (`{"scene", "versions": [N, N, N], "style": "auto" \| "invent"}` while the user is to pick a style; absent otherwise) |
| `storyboard.json` | the storyboard, in the structure `media:short-video` defines for `storyboard.json` |
| `settings.yaml` | `media:short-video` settings: only the keys of [settings.yaml](#settingsyaml) |
| `status.json` | the state of each scene ([status.json](#statusjson)) |
| `lessons.md` | `media:short-video`'s lessons file; created with the first storyboard |
| `refs/`, `sources/` | the user's pictures, reference videos (MP4, MOV, WebM) and sources, written by the page; research sources this skill saves go in `sources/`, generated tracks in `sources/music/`; `media:short-video`'s `refs` writes its frames and `refs.json` into `refs/` |
| `reference.md` | the description of the reference videos, written in the storyboard step ([storyboard](#storyboard) step 2) |
| `images/<scene>/v<N>.png`, `v<N>.json` | picture N of scene `<scene>`, numbered from 1 within the scene's directory, never overwritten; the sidecar has the fields of a `studio:images` version sidecar, with `kind` `"short-video"`, `model` `best` (image-gen's tier), `model_id` the `<provider>:<model>` that made it (the `--model` of image-gen's model routes, else `image_best` from the request's `models`), `shape` the film's and `brand` the film's; written after the PNG. A drawn scene's versions are sidecars only, each naming a still of its page ([Page stills](#page-stills)) |
| `images/<scene>/marks/` | marked copies and edit masks, written by the page |
| `voice/`, `scenes/`, `music/v<N>/`, `film/v<N>/` | `media:short-video`'s versions, written by its commands |
| `music/v<N>/studio.json` | `source` (`made` or `own`), `brief` (the request's; `""` for an own track), `note` (one line on how it sounds), `duration` (seconds), `created`; written after the `music` command imported the version |
| `film/html/v<N>/studio.json` | `changes` (one line: what is new since the previous HTML film), `created`; written after `html` wrote the HTML film |
| `film/v<N>/studio.json` | `changes` (one line: what is new since the previous MP4), `created`; written after the MP4 is checked |
| `film/v<N>/review.json` | the film critic's findings on film N that hold: `{"created", "model": <the critic's model>, "findings": [{"k": 1, "start": <s>, "end": <s>, "problem": "...", "change": "..."}]}`, `k` numbered from 1, `start` and `end` film time in seconds, `findings` `[]` when none holds; written whole by each review ([Film review](#film-review)) |
| `samples/voice-<k>/narration.wav`, `samples/voice-<k>.json` | voice samples, k from 1, never overwritten; the directory is `media:voiceover`'s output directory; the sidecar, written after the WAV: `voice` (`model`, `name`, `speed`, `style`), `text`, `created` |

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
  `manim`, `video` (the config task `video` animates the scene's picture from its `brief`, the prompt) or
  `presenter` (the config task `presenter` makes the person in the scene's picture speak the scene's narration
  recording; `brief` optional, when given the model's prompt). A video or presenter scene gets a picture like an
  image scene; a presenter's picture is a portrait of one person facing the camera. A scene gets `presenter` only
  when the user asks for a talking presenter, never by the agent's choice. The page sets `engine`; an engine
  the user set is kept by every request except a new storyboard. The request's `models` names each task's model;
  with `models.video` null, no scene gets `engine` `video`, and with `models.presenter` null none gets `presenter`.
- A drawn scene is an HTML scene without `image` (no `template`, `engine` absent or `html`): written where a picture
  would not help the point, such as a diagram, chart, map, process or text built with the speech. Its `brief` says
  what the page draws and how it moves. It never gets `image`. Every step below that makes a scene's picture makes a
  drawn scene's page and one still of it instead ([Page stills](#page-stills)).
- The key scene, on which the style samples are made: the first scene in the film with a picture that is not a
  template scene; with none, the first drawn scene; with neither, the first template scene.
- A scene's picture shows what its narration is about, with no text unless the scene's `brief` needs text in the
  picture; the On screen text is drawn by the scene. The sidecar's `scene` is that description.
- "The scene's style" is its `scene_styles` entry, else the film's `style`. Any catalogue style may be offered or picked
  for a film; `suits` is one of the things compared when choosing, never a filter.
- The film's length is `film.length`, or the length the request's `brief` names when it names one ("a 40-second
  film"); that length is "the film's length" everywhere below and in `settings.yaml`.
- The narration fits the film's length at about 2.5 words per second.
- A silent film (`film.silent` true) has no narration: every scene is an HTML scene with `length` (drawn, or with a
  picture; no template) or a clip scene, with no `narration` and no `speakers`, and the scene lengths sum to the
  film's length. No voice is recorded and no page is timed from an estimate; `media:short-video`'s silent HTML scene
  rules apply.

### Page stills

A drawn scene gets its page and one still of it wherever a scene with a picture gets its picture: in `storyboard`,
`use-style`, `style-samples`, `add-scene` and the `change` of one of its stills. Its picture versions in
`images/<scene>/` are these stills. The film uses the scene's latest page version, and every page version that
becomes the latest gets a still and its sidecar (also in `make-film`, `remake-scene`, `fix`, `mark-scene`, `message`
and `use-still`).

Writing a page here uses `media:short-video`'s HTML scene steps for the page itself only: its Brief check, its
motion check rounds and its stills-critic loop do not run when a still is made.
Only [make-film](#make-film) runs a critic round and the motion check, on the scenes it builds.

Several pages of one scene in one request (the three style samples): each is built fully, steps 1 to 4 (scaffold,
write, check, still and sidecar), before the next is scaffolded, since `check` checks only the scene's latest page
version.

1. `scaffold --scene <scene>`, so every still keeps the page version it shows. A narrated scene without a voice
   version is not recorded for its page: `scaffold --scene <scene> --estimate` times the page from its words at
   2.5 words per second, and [make-film](#make-film) re-times it after recording. A world scene is scaffolded
   through its world, which needs its scenes recorded: record them first with `media:short-video`'s voice step in
   `film.voice`.
2. Write `index.html` as `media:short-video` says for an HTML scene, from the scene's brief, beats and On screen
   text, in the page style ([Page style](#page-style)); then `check --scene <scene>`.
3. `stills --scene <scene> --at <t>` at one time: the moment the brief names as the scene's main view, else 80% of
   the scene's length.
4. Write `images/<scene>/v<N>.json` (N numbered as pictures) after the still: the fields of a picture sidecar with
   `prompt`, `model` and `model_id` null, plus `page_version` (the version directory relative to the project:
   `scenes/<scene>/v<K>` or `worlds/<world>/v<K>`), `still` (the still's file name in its `stills/`), `t` and
   `page_style`. The page shows the still once the sidecar exists.
5. Post the still at once as `images`.
6. Then, in the same turn, one critic subagent (Agent tool, waited for) views the still against the scene's brief,
   its On screen text and the page style, and lists clear defects only: text cut off or unreadable, an element
   missing or overlapping another, colours outside the palette. Post its defects as a text-only `post` (nothing
   when it lists none). Nothing is fixed from them and no second round runs; the user asks for a `change`. The
   request ends there, with no background task left running. Several stills of one request are posted first,
   and one critic per still then runs in parallel.

A page version that a still's sidecar names is never edited: any fix made while looking at stills (a critic's
defect, a `change`, a message) starts with `scaffold`, so the fix is a new page version with a new still.

A `change` of a still has the fields of a picture's `change`; `marked` is the still with the marks. It starts from
that still's `page_version`, not from the latest page: `scaffold`, copy that version's `index.html` into the new
version, then make what the marks and the note ask, and steps 2 to 6 with `change` and `source` as for a picture.
The server refuses `variations` and `other-styles` of a still.

### Page style

`page_style` is the look of a drawn scene's page: `{"palette": [<hex>, ...] (background, ink and 2 to 4 accents),
"light": "<one line>", "typography": "<heading and body font families>", "dimension": "2D" | "3D", "camera":
"<one line>"}`. A 3D page is a three.js page as `media:short-video` says. The film's page style is `style.page_style`
in `project.json`, used by every drawn scene's page.

- Typography names font families the HTML film can carry: families under the SIL Open Font License installed on
  this machine (`fc-list : family file | grep -i "<family>"`; every Google Font family is OFL). Each page copies the
  font files it uses into its version's `fonts/` and loads them with `@font-face`, so `html` embeds them; `html`
  warns for a font a page names without embedding it, and that warning is fixed like a card warning.
- Precedence: once the film's page style is chosen, its palette and typography hold for every page. A reference
  video (`reference.md`) keeps camera, motion, composition and density. After `use-style`, the look lines of each
  HTML scene's `brief` (colours, ground, fonts) are rewritten to the chosen page style before its page is made, and
  a page made before is scaffolded again (`scaffold --refresh`) with the rewritten brief, so every critic judges
  the page against the chosen style.

- Style samples on a drawn key scene: three page styles, each a sample's `page_style`. With `"auto"`, three catalogue
  styles chosen as `studio:images` does, each with its default palette and the light, typography, dimension and
  camera that suit its style line; with `"invent"`, three invented styles (`invented` with `name`, `description`,
  `style_line`, `palette`) and their page styles. The three differ in palette, light, typography, 2D or 3D, and
  camera. The chosen sample's `page_style` becomes `style.page_style`.
- Any other film style (picture samples or a catalogue name): the palette is the picture style's (its invented
  `palette`, else its default palette from `brand:style`); light, typography, dimension and camera suit its style
  line and the brief. It is written as `style.page_style` when the style is set and the film has a drawn scene.

### settings.yaml

Before each `media:short-video` command of a request, write `settings.yaml` from the request's `film` (else
`project.json`'s `film`), keeping `music.file` and the phone keys as found:

| `film` | `settings.yaml` |
|---|---|
| `voice` | `voice.model`, `voice.name`, `voice.speed`, `voice.style` |
| `music.mode` `none` | `music.file: null` |
| `music.volume` | `mix.music_db`: `quiet` -20, `normal` -14, `louder` -9 |
| `shape` | `video.width` and `video.height`: `16:9` 1920 by 1080, `9:16` 1080 by 1920 |
| `length` | `length.min_seconds` 0.75 and `length.max_seconds` 1.25 times the film's length ([Scenes](#scenes)); in a project with `origin` and `shape` `9:16`, the phone-version limits of `media:short-video` |
| `author` | `author` |
| `brand` | `brand` |
| `silent` | nothing: a silent film's scenes carry `length` in `storyboard.json` |
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
2. When `refs` holds videos (`.mp4`, `.mov`, `.webm`): run `media:short-video`'s `refs --src <video>` once per
   video (its output goes to the project's `refs/`), with the reference pictures of `refs` as frames of the video
   or as an image source as it says, and write `reference.md` with its reference-video step before the storyboard.
   Every Brief is then written from `reference.md` as that step says.
3. Write the story with `media:short-video`'s storyboard step from the `brief`, the reference pictures and the
   files in `sources` (research only when the brief asks for it; save what is used in `sources/`). A script in the
   brief goes in word for word. `source` is the main source file when there is one. Replace `storyboard.json`
   whole, following [Scenes](#scenes) (a silent film: silent scenes with `length`); keep the old storyboard's
   `speakers` when it has them. Each scene with a
   picture has as `image` the path of the number reserved for its next picture, made or not. Create `lessons.md`
   when missing. Unless `named` is true, set `name` in `project.json` to the storyboard's `title` (a short title, not the brief's first
   words).
4. Pictures, by `style` (a drawn scene's page and still where "picture" stands, [Page stills](#page-stills)):
   - a style name: set `style` to it (with its `page_style`) and make every scene's picture in its style.
   - `"auto"` or `"invent"`, `step` autonomy: three styles, chosen or invented as `studio:images` does for an image,
     one sample each on the key scene, as its versions: a picture of a scene with a picture, or a page version and
     its still in each of three page styles ([Page style](#page-style)) of a drawn key scene. Set `samples` to that
     scene, the three N and `style`. No other picture or page is made. The scene's `image` is left as it is until
     `use-style`; in a new storyboard it is the reserved path of the first sample (a drawn scene has none).
     When there is no key scene (every scene manim or clip), no samples: one style is chosen or invented
     as in the next branch and set as `style`.
   - `"auto"` or `"invent"`, `auto` autonomy or `make_film`: one style chosen or invented the same way, set as `style`, every
     scene's picture made in its style.
5. Write `settings.yaml`, run `validate`, write `status.json`.
6. `auto` autonomy or `make_film`: go on as [make-film](#make-film).
7. Post: the title, per scene its number, title and sentences, the style (with the samples: each style's name and
   why it was chosen, or its description when invented), and the pictures as `images`.

### use-style

Exactly one of `version` and `style`.

- `version`: one of `samples.versions`, or an earlier style sample of the same scene (`samples.scene`, else the key
  scene): any still of it whose sidecar has a `page_style`, such as a sample of an earlier round. Post a problem when
  that scene is no longer a scene. The film's `style` becomes that sample's `style` (with its `invented`, and a
  still's `page_style`); the sample becomes the picture of that scene (a still: its page becomes the scene's latest
  page version; when it is not, `scaffold` and copy the sample's `index.html` into the new version, then take its
  still as [Page stills](#page-stills) says); remove `samples` when present; every other scene with a picture and
  without its own style gets a new picture in it, and every other drawn scene its page and still, each from its
  brief rewritten to the page style ([Page style](#page-style), Precedence).
- `style` (a catalogue name): the film's `style` becomes it; every scene with a picture and without its own style
  gets a new picture in it, used by the scene, and every drawn scene its page and still.

Then `status.json`, and post the style and the new pictures and stills.

### style-samples

Field: `style` (`"auto"` or `"invent"`). In `step` autonomy, as step 4 of `storyboard` with that style, on the key
scene of the storyboard as it is now; that scene keeps its picture (a drawn scene: the samples are new page versions,
the film's page is the latest until `use-style`). In `auto` autonomy, as the `auto` branch of that step: one style
chosen or invented, set as `style`, a new picture in it for every scene with a picture and without its own style,
used by the scene, and a page and still for every drawn scene; then `status.json` and [make-film](#make-film).

### change, variations, other-styles

Fields: `scene` and those of the `studio:images` action of the same name, carried out with its steps inside
`images/<scene>/` (`version`, `marked` and `mask` are files of that directory). For `other-styles` with empty
`styles`, the three styles are chosen as in `storyboard` with `"auto"`, other than the version's. A `change` makes the
new picture the scene's picture, then `status.json`; `variations` and `other-styles` leave the scene's picture as it
is. Post the new pictures with their numbers. A `change` of a drawn scene's still changes its page as
[Page stills](#page-stills) says.

### use-still

Fields: `scene` (a drawn scene), `version` (a still of it whose page is not the scene's latest page). The page sends
it from "Use this still", as "Use this picture" makes a picture the scene's picture. `scaffold --scene <scene>`, copy
the `index.html` of the still's `page_version` into the new version, `check`, then `stills --scene <scene> --at <t>`
at the still's `t`, and write its sidecar ([Page stills](#page-stills) step 4) with `action` `use-still` and `source`
`version`. That page is now the scene's latest page version. `status.json`, then post the still; no critic runs.

### add-scene

Fields: `after` (a scene id, or null for the end), `text`. Write a new scene after `after` (at the end for null) with
a new id, its narration, beats and brief from `text`, and its picture in the film's style (made, then used); a drawn
scene gets its page and still ([Page stills](#page-stills)).
`status.json`; post the scene's number, title and picture or still.

### remake-scene

Fields: `scene`, `film`. Write `settings.yaml` from `film`, run `validate` and `status`, and redo for that scene
what `media:short-video`'s "What an edit needs" lists for the reasons `status` gives: a new recording with its voice
step, a new page version with its scaffold step, a new clip as it says for clip scenes. An HTML scene (drawn,
template or with a picture) gets its page built, checked and a still taken, with no render, as in
[make-film](#make-film); a drawn scene's still gets its sidecar ([Page stills](#page-stills) step 4, `action`
`remake-scene`). A manim, video or presenter scene is rendered. Then `status.json`, and post the still (an HTML
scene) or the clip path and its `contact.png` as `images`.

### mark-scene

A comment on a paused frame of an HTML scene's latest page version, rendered or not. Fields: `scene`, `version` (that
page version: a scene version, or for a world scene a world version), `t` (scene time in seconds), `world` and
`world_t` (the world and the time in its page; null for a scene without a world), `mark` (`{point: {x, y}}` or
`{rect: {x, y, w, h}}` in frame pixels), `ids` (the page elements with an id under the mark, innermost first; may be
empty), `marked` (the frame with the mark, a PNG, or null), `text` (what to change).

1. With `marked` null (the version has no render), make the marked still from the page before any edit:
   `media:short-video`'s `stills --scene <scene> --at <t> --mark <x>,<y>` for a point, `--mark <x>,<y>,<w>,<h>` for a
   rect. Read the `_mark.png` copy it writes. Otherwise Read `marked`.
2. Run `scaffold` on the scene (on a world scene it acts on its world) before the first edit, so the commented
   version stays as it is.
3. Change in the new version's `index.html` what `text` asks, on the elements `ids` names as they are at `t` (at
   `world_t` in a world page). With no `ids`, find the elements from `mark` and the marked still.
4. `check --scene <scene>`, then `stills --scene <scene> --at <t>`, and Read the still. `render` the scene only when
   the commented version had a render (`marked` not null).
5. On a drawn scene, write the still's sidecar as [Page stills](#page-stills) step 4 says (`action` `mark-scene`),
   so the page shows the new still. `status.json`, then post what changed with the still as `images`.

The page shows the new page version at `t` once it exists.

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

Field: `film`. Follow `media:short-video`'s workflow from its voice step to its HTML film step, with Studio's
answers to its gates. The film is the HTML film `film/html/v<N>/film.html`; no scene is rendered for it and nothing
is assembled.

1. Write `settings.yaml` from `film`; run `validate` and `status`.
2. Record each scene `status` reports as needing a voice (voice step), then make each scene's page or clip with the
   scene steps (the remaining scenes in parallel subagents as it says), with `lessons.md`: an HTML scene (template
   scenes included) gets its page built and checked with `check` and `stills`, without `render`; a manim, video or
   presenter scene is rendered and a clip scene gets its clip, since the HTML film plays their `scene.mp4`. A page
   timed from an estimate (`status` says so) is scaffolded again after the recording, which keeps its `index.html`
   and times it to the recording, and its beats are moved to the new times. The prototype is not reviewed with the
   user and no file is opened with `play`. Each scene gets at most one round of `media:short-video`'s stills critic
   (its findings fixed once, no second round) and its motion check on its stills (on its frames for a rendered
   scene); a scene that fails the motion check is made again once with more movement. Each drawn scene's final
   page version gets a still and its sidecar ([Page stills](#page-stills) step 4, `action` `make-film`).
3. The music version: `music_used` is null for `music.mode` `none`; otherwise, among the complete music versions
   whose `studio.json` `source` is the mode, `music.version` when it is one of them, else the newest. With mode
   `made` and none, make one as the `music` request does from `music.brief` (the topic when it is empty).
4. Run the audio check, then `html` (`--music v<N>` of `music_used`; without it for `none`); that HTML film is HTML film N below. A warning of `html` for a scene shown as
   a card is fixed (the scene's page or clip made) and `html` runs once more. The scene critic never runs.
5. Write `film/html/v<N>/studio.json` and `status.json`.
6. Post HTML film N at once, so the user watches it: its path, length, music version and `changes`, with a still
   of each HTML scene and the `contact.png` of each rendered scene as `images`.

`film.review` does not apply here: the film critic watches an MP4, so the review runs after
[export-mp4](#export-mp4). An empty `film.author` gives a film without a creator credit; it does not stop the work.

### export-mp4

Field: `film`. The MP4 of the current scenes, `film/v<N>/film.mp4`, as `media:short-video`'s MP4 step makes it.

1. Write `settings.yaml` from `film`; run `validate` and `status`. A scene `status` reports as needing a voice or a
   new version is made first as make-film step 2 says.
2. `render --scene <id>` every HTML scene whose latest page has no render (`rendered` false in `status`), one call
   per world, in parallel subagents.
3. The music version as make-film step 3. Run the audio check and `assemble` (`--music v<N>` of `music_used`;
   without it for `none`), then the checks `media:short-video` lists before hand-over. When one fails, in every
   autonomy and whatever `film.review`, fix it and `assemble` once more; that film is film N below.
4. Write `film/v<N>/studio.json` (`changes`: what is new since the previous MP4) and `status.json`.
5. Post film N at once: its path, length, music version and `changes`, with the scenes' `contact.png` as `images`.
6. Only when `film.review` is true, in the same turn: [Film review](#film-review) of film N. Then, by `autonomy`:
   - `step`: post the findings that hold (as `review` does); nothing is fixed.
   - `auto`: when a finding holds, fix the findings that hold as [fix](#fix) does from step 2 (one assembly;
     `changes` names the fixes); that film is not reviewed. With none, post that the review found nothing; no new
     film is made.

### Film review

Of film N: write `settings.yaml` as for `film.review` true, whatever `film.review` is, so `critic.model` takes
`media:short-video`'s default. Ask `media:short-video` for one run of its film critic step on `film/v<N>/film.mp4`
(at most `critic.max_findings` findings), and verify each finding against the film as that step says; fix nothing.
Write the findings that hold to `film/v<N>/review.json`, numbered `k` from 1 in the critic's order, with `created`
the request's `time` and `model` the critic's model.

### review

Field: `version` (MP4 film N of this project). [Film review](#film-review) of film N, then post the findings that hold
as a list, one line each: time range, what is wrong, what to change ("no findings" when none holds). Nothing is fixed
or assembled, and no file other than `review.json` is written.

### fix

Fields: `version` (MP4 film N of this project), `findings` (the `k` of the findings of film N's `review.json` the user
kept, possibly empty), `note` (the user's text, possibly empty), `film`.

1. Write `settings.yaml` from `film`; run `validate` and `status`.
2. Fix the kept findings and the note together, as `media:short-video`'s "What an edit needs" says for each change:
   edit `storyboard.json` or a scene's files, and re-record or re-render only the scenes they touch, each passing the
   motion check of make-film step 2, and render every HTML scene whose latest page has no render, as export-mp4
   step 2. A page is changed in a new page version (`scaffold` first); a drawn scene's new page version gets a still
   and its sidecar ([Page stills](#page-stills) step 4, `action` `fix`). A correction of the film is added to
   `lessons.md` as one dated line.
3. Run the audio check and `assemble` once, as export-mp4 step 3; then `html`, so the HTML film plays the fixed
   scenes.
4. Write `film/v<N>/studio.json` of the new MP4 and `film/html/v<N>/studio.json` of the new HTML film (`changes`:
   the fixes, in one line, in both) and `status.json`.
5. Post the MP4 as export-mp4 step 5, with what was fixed and any finding or note that could not be. The new film is
   not reviewed.

### phone

Fields: `version` (MP4 film N of this project), `target` (the new project, with its `project.json` made by the server).
Build film N's phone version in `target` as `media:short-video`'s short-version and phone-version steps say, with
the original read in place and never changed. The message and audience are the original film's (its `topic` and
`project.json` `brief`); nothing is confirmed with the user. The voice is `film.voice` as the server copied it, with
no speed change.

1. Copy the original's `lessons.md` and `storyboard.json` (as `sources/storyboard.json`, the new `source`); write
   `settings.yaml` with the phone keys.
2. Write the new `storyboard.json` (3 to 5 scenes, one message, new ids where scenes merge), and each picture as a
   9:16 version of the original scene's picture, made with the original as reference image in that picture's style
   (its sidecar's `style`, and `invented` when present), as `images/<scene>/v<N>.png` in `target`. Each drawn scene
   gets its page in `target` laid out for 9:16 (1080 by 1920), from the original scene's latest page and in the
   original's page style (copied into `target`'s `project.json` `style`), and a still with its sidecar, as
   [Page stills](#page-stills) steps 1 to 5 say (timed from an estimate; make-film re-times it).
3. The music is `target`'s `music/v1/`, the server's copy of the track film N used (`film.music.version` 1); none
   for a film without music.
4. `status.json`, then [make-film](#make-film) and [export-mp4](#export-mp4) in `target`, in either autonomy:
   the phone version is a video file.

### message

Field: `text`; optionally `scene`; `project` may be null. Answer with `post`. Work the message asks for is done with
the rules of the action it matches; a message with `scene` changes that scene (its sentences, beats, brief or
picture; a drawn scene: its page, in a new page version with a still and its sidecar as
[Page stills](#page-stills) says, `action` `message`). A correction of the film is added to `lessons.md` as one dated line. With `project` null and work asked
for, post that a project has to be opened first.

## Answering

- Progress: `mcp__studio__note` with one short line. During `make-film` and `export-mp4` the page shows the latest note as progress.
- Result: `mcp__studio__post` with `text` and `images` (absolute paths of new pictures or contact sheets).
- Failure: post the command's one-line error message (never a traceback) and what was not made; what succeeded
  is kept and posted.
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
