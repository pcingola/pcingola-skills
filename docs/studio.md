# studio

The `studio` plugin is a web page in the user's browser for making images, infographics, slide decks and short videos
with Claude. Every action in the page becomes a request to the Claude Code session, and the agent carries it out with
the skills.

A request goes through these steps:

1. The page POSTs the request to a local server.
2. The server checks it, adds an `id` and a `time`, and writes it as one JSON line to its stdout.
3. The mod (the plugin's hooks module), which started the server, queues the request and submits it as a prompt that
   names the workspace skill (`studio:images` or `studio:videos`) and carries the request JSON verbatim.
4. The agent follows that skill, writes new files into the project directory, and reports with the tools `note`
   (progress) and `post` (answers).
5. The server sees the changed files and sends an event; the page reads the project again and redraws.

The project files are the only state. The agent does all generation through the skills; the server and the page read
files, check requests and write small edits (settings, the storyboard, uploads). Neither the mod nor the server calls a
skill CLI.

## Pieces

| Piece | Location | Role |
|---|---|---|
| Mod | `plugins/studio/hooks/register.ts` | `/studio` command; starts the server; queues requests and submits them as prompts; Stop; tools `post` and `note`; sends the agent's log to the page |
| Server | `plugins/studio/server/` (uv project `studio_server`, wrapper `studio-server.sh`) | serves the page and project files on `127.0.0.1`; checks requests and relays them to the mod; sends events to the page |
| Page | `plugins/studio/server/page/` | shared shell (`index.html`, `studio.css`, `shell.js`) and one module per workspace skill (`images.js`, `videos.js`) |
| Skills | `plugins/studio/skills/<skill>/SKILL.md` | the project format of a workspace and how the agent answers each action |

The server is a standard-library Python program whose only dependency is `plugin-settings`; its environment lives in
the plugin data directory like every skill wrapper's. The page loads nothing from another host.

## Kinds of project

| `id` | Label | Directory | Skill |
|---|---|---|---|
| `short-video` | Short videos | `short-video` | `videos` |
| `slide` | Slide decks | `slides` | `images` |
| `image` | Images | `images` | `images` |
| `infographic` | Infographics | `infographics` | `images` |

The kinds are `KINDS` in `server/studio_server/projects.py`. A kind's skill answers its requests, and the page module
of that skill draws its workspace, so `images.js` serves three kinds.

## Projects

`STUDIO_DIR` (default `~/Documents/Studio`) holds one directory per kind. A project is
`<root>/<directory>/<project>/` with a `project.json`. The folder name is the creation time (`YYYYMMDD-HHMMSS`), so
renaming a project moves no files. Every request carries the project's absolute directory, so the skills read no
setting.

`project.json` has `name`, `brief`, `kind`, `created`, `autonomy` and `settings` (the fields of the last request
that made the project's content). `autonomy` is `step` (the agent does what the request asks and stops) or `auto`
(the agent goes on to the finished result). The agent names a new project from its brief; once the user renames it,
`named` is true and the agent keeps the name. The server and the agent both write `project.json`; each reads it again
right before writing and changes only its own keys.

Versions are never overwritten: every new result gets the next number.

### Images and infographics

| File | Content |
|---|---|
| `v<N>.png`, `v<N>.json` | version N and its sidecar: the prompt, what the image shows, refs, style, brand, model, shape, the action, the change and its source version; the JSON is written after the PNG, so a listed version is complete |
| `refs/` | reference images uploaded by the user |
| `marks/v<N>-marked-<k>.png`, `v<N>-mask-<k>.png` | the marked copy and edit mask of one change request on version N, written by the page |

A change marks regions of a version (box, point or freehand loop, each with a comment) and may add a general note.
The page draws the marks in red on a copy of the image and builds an edit mask: opaque outside the marks, transparent
inside. A model that takes a mask changes the image only where the mask is transparent; on a model without one,
the agent edits from the image and the marked copy alone.

### Decks

A deck (kind `slide`) has its content and speaker notes in `slides.md` (`media:pptx-author`'s format) and a `deck.json`
listing the slides in order, so the server needs no Markdown parser. Each slide k is a directory `slide-<k>/` laid out
like an image project, with versions and marks; `refs/` is shared at the deck level. `project.json` adds `chosen`
(the version of each slide that goes into the PowerPoint) and `assembly`: `images` (each slide as a full-slide
picture, fast, not editable) or `native` (`media:pptx-author`'s editable rebuild). Assembled decks are `deck-<N>.pptx`
with a `deck-<N>.json` sidecar.

### Short videos

A short-video project is a `media:short-video` project directory that also holds Studio's `project.json`. The agent
makes the film with `media:short-video`'s commands; the server only reads the results.

| File | Content | Written by |
|---|---|---|
| `storyboard.json` | the film's scenes (below) | page, agent |
| `settings.yaml` | `media:short-video` settings derived from `film` in `project.json`, written before each command | agent |
| `status.json` | the per-scene result of `media:short-video`'s status command | agent |
| `refs/`, `sources/` | the user's reference pictures and videos (MP4, MOV, WebM), sources and own music tracks; the agent's research sources and generated tracks; `media:short-video`'s `refs` output (frames, `refs.json`) in `refs/` | page, agent |
| `reference.md` | the description of the reference videos the storyboard is written from | agent |
| `images/<scene>/v<N>.png`, `.json` | the pictures of a scene, as image versions; for a drawn scene, sidecars only, each naming a still of its page (`page_version`, `still`, `t`, `page_style`) | agent; page for the user's own picture |
| `voice/<scene>/v<N>/`, `scenes/<scene>/v<N>/`, `music/v<N>/`, `film/v<N>/` | `media:short-video`'s recordings, scene versions (a page `index.html`, and a rendered clip once `meta.json` exists), music and MP4 films; a recording, render or music version is complete once its `meta.json` (a film: `manifest.json`) exists | `media:short-video` |
| `worlds/<world>/v<K>/` | the page of a shared world (`index.html`, `world.json` with each scene's `start` and `duration`), rendered or not | `media:short-video` |
| `film/html/v<N>/film.html` | an HTML film: one standalone page that plays every scene, with its `manifest.json` | `media:short-video` |
| `music/v<N>/studio.json`, `film/v<N>/studio.json`, `film/html/v<N>/studio.json` | Studio's notes on a track (made or own, its brief) and on an MP4 or HTML film (what changed since the previous one) | agent |
| `film/v<N>/review.json` | the film critic's findings on film N that the agent verified | agent |
| `samples/voice-<k>/` | voice samples for the voice picker | agent |
| `comments/<scene>/v<N>-t<t>-<k>.png` | the marked still of a `mark-scene` comment: the frame of the render of page version N at scene time t with the mark | page |
| `comments/<scene>/comments.json` | the scene's `mark-scene` comments, `{"request", "t", "mark", "ids", "text", "marked", "state"}`, `state` `open`, `done` or `stopped` | server |

`project.json` adds `film` (the film settings below), `style` (the film's picture style, possibly invented, with
`page_style` for the pages of drawn scenes: palette, light, typography, 2D or 3D, camera), `scene_styles` (scenes
with their own style), `samples` (three sample pictures or page stills while the user picks a style) and, in a
phone version, `origin`.

The user's workflow: a prompt in step 1, the storyboard written from it and refined in the page, three style samples
on one key scene iterated with "Choose others", "Invent others" or the catalogue until one is right, the chosen style
applied to every scene, then the voice, the music and the film. Where a scene with a picture gets its picture, a
drawn scene gets its page (`scaffold`, the page written from its brief in the film's page style) and one still from
`media:short-video`'s `stills`. Before the voice is recorded, a narrated drawn scene's page is timed from its words
at 2.5 words per second (`scaffold --estimate`, which writes `estimated` into the version's `timing.json`);
`make-film` records the voice and scaffolds the page again on the recording. The still is a picture version whose
sidecar names the PNG in `<page version>/stills/`; the server lists it with the scene's pictures (`image` the still)
and gives the newest as the scene's `still`. Every page version that becomes a drawn scene's latest gets a still and
its sidecar. A still is posted as soon as it is taken, without short-video's Brief check, motion check or stills
critic loop; then one critic subagent views it in the same request and its defects are posted as a message, with
nothing fixed and no second round. A page version a still names is never edited: every fix scaffolds a new version.
Feedback on a still is a `change`, which starts from that still's page version and makes a new page version and a
new still; "Use this still" (`use-still`) makes an older still's page the latest page version again. `variations`
and `other-styles` of a still are refused. In `make-film` each scene gets at most one stills critic round and one
remake after a failed motion check. The key scene is the first scene with
a picture that is not a template; with none (an HTML film), the first drawn scene, whose three samples are stills of
its page in three page styles. In a mixed film the pages take their palette from the picture style.

`storyboard.json` is the structure `media:short-video` parses `storyboard.md` into, plus per-sentence voice settings.
Each scene has an `id` that names its directories and never changes; a new scene never reuses the id of a deleted one,
so it inherits none of its files. A scene has `narration` (its sentences), `beats` (what is on screen during each
sentence), optionally per-sentence `speakers` and `voices`, and the keys of its form: a template scene (`title`,
`summary`, `end`), an HTML scene with a picture, a drawn scene (an HTML scene without `image`, whose page draws a
diagram or text), a `manim` scene, a `video` scene (the config task `video` animates its picture from its
`brief`), a `presenter` scene (the config task `presenter` makes the person in its picture speak its narration
recording; `brief` optional) or a `clip` scene. The page sets a scene's `engine` (`html`, `manim`, `video` or
`presenter`; the last two only for a scene with a picture). A scene's picture is the version its `image` names.
An HTML scene without narration has `length` (seconds) instead. HTML scenes with the same `world` (`[a-z0-9_]+`)
share one page; they follow each other in the storyboard and have no `template` or `image`.

The film settings, `film` in `project.json`:

| Key | Value | Default |
|---|---|---|
| `voice` | `model` (a speech model id; null: the `speech` model of `config.yaml`), `name` (null: the model's default voice), `speed`, `style`; a stored voice without `model` reads as the default | `speech` model, no name |
| `music` | `mode` (`made`, `own`, `none`), `brief`, `volume`, `version` (the track to use, or the newest) | `made` |
| `shape` | `16:9` or `9:16`, fixed once the storyboard has scenes | `16:9` |
| `length` | 30, 60, 120 or 180 seconds; a length the brief names (such as "40 seconds") takes its place in the storyboard and `settings.yaml` | 60 |
| `author` | names for the creator credit | from the `AUTHOR_NAME` setting |
| `brand` | brand name or null | null |
| `review` | whether `export-mp4` runs the film critic on the MP4 | true |
| `silent` | a film without narration: every scene is a silent HTML scene with `length`, or a clip; no voice is recorded | false |

Each scene shows one of three states: `ready` (recording and clip match the scene), `voice` (it needs a new
recording, then a render) or `render` (it needs a new render only). The agent writes `status.json` after every request
that changes a scene, recording what the status command reported and the scene it ran on. The server compares each
scene with that record and shows the state, so an edit in the page changes the state at once. The state is only
displayed; `make-film` and `remake-scene` run the status command, which decides what is remade.

A project that holds `storyboard.md` instead of `storyboard.json` is shown with an error and accepts only messages, a change of autonomy, a rename and a delete.

## Server

The mod starts the server, which listens on a free port of `127.0.0.1` and writes JSON lines to stdout: `ready` with
its URL, `request` for each accepted request, `stop` when the user stops one. stderr is a log. The server exits when
no heartbeat from the mod arrives for 20 s or the process that started it is gone.

The page's endpoints. A POST body names its `project` (absolute, inside the root); a deck body names its `slide`,
a short-video body its `scene` where the endpoint acts on one. Errors answer `{"error": <message>}`.

| Endpoint | Body | Answer |
|---|---|---|
| `GET /`, `GET /static/<file>` | | the page; nothing outside `page/` |
| `GET /api/config` | | `{"root", "kinds": [{"id", "label", "directory", "skill", "ready"}], "film": <defaults of a new film>}` |
| `GET /api/models` | | `{"tasks": {<task>: <provider>:<model> or null}, "tiers": [{"id", "model", "ref_model"}]}`, read from `config.yaml` on each call (below) |
| `GET /api/projects?kind=` | | `[{"dir", "name", "brief", "updated", "versions"}]`, newest first; a deck adds `slides` |
| `GET /api/project?dir=` | | `{"dir", "project": <project.json>, "versions", "refs"}`; a deck adds `deck` (slides, chosen versions, assembled decks), a short video `video` (storyboard, scene states, pictures, recordings, clips, pages, music, films, HTML films, samples) |
| `GET /api/catalogue` | | `{"styles": [{"name", "description", "tags", "suits", "sample"}], "brands"}`; `loading` true until loaded, `error` when the brand plugin or its catalogue is missing |
| `GET /file?path=[&download=1]` | | a file inside the root or a catalogue sample image, with byte ranges (`accept-ranges: bytes`, 206, 416) so audio and video can seek; `content-security-policy: sandbox`, and `sandbox allow-scripts` for the `film.html` of an HTML film, so its player runs in an opaque origin |
| `GET /events` | | server-sent events, `data: <JSON>` per event |
| `POST /api/request` | a request | 202 `{"id", "project"}` (a phone version adds `target`); `project` null creates the project first |
| `POST /api/stop` | `{"id"}` | 202 `{"id"}`; 409 for a request neither running nor queued |
| `POST /api/new` | `{"kind", "autonomy"}` | `{"project"}`: an untitled project, for a file added to a blank workspace |
| `POST /api/name` | `{"project", "name"}` | `{"name"}`; sets `named` true |
| `POST /api/autonomy` | `{"project", "autonomy": "step" \| "auto"}` | `{"autonomy"}` |
| `POST /api/chosen` | `{"project", "slide", "version"}` | `{"chosen": <map>}`, a deck's chosen version per slide |
| `POST /api/assembly` | `{"project", "assembly": "images" \| "native"}` | `{"assembly"}` |
| `POST /api/film` | `{"project", "film": <keys to replace>}` | `{"film"}` |
| `POST /api/scene-style` | `{"project", "scene", "style": <name or null>}` | `{"scene_styles"}` |
| `POST /api/storyboard` | `{"project", "storyboard", "base": <storyboard_mtime read>}` | `{"storyboard_mtime"}`; 409 with the current `storyboard` and `storyboard_mtime` |
| `POST /api/refs` | `{"project", "name", "data": <data URL>}` | `{"path"}`: the absolute path of `refs/<name>`, PNG, JPEG or WebP; in a short-video project also MP4, MOV or WebM of at most 45 MB (413 above). `refs` of `/api/project` lists only the pictures and videos of `refs/` |
| `POST /api/sources` | `{"project", "name", "data"}` | `{"path"}`: the absolute path of `sources/<name>`, a source or music file |
| `POST /api/picture` | `{"project", "scene", "name", "data": <PNG data URL>}` | `{"version", "path"}`: the user's own picture as the scene's next version |
| `POST /api/marked` | `{"project", "version", "png", "mask"}` (`mask` optional) | `{"path", "mask"}`: `marks/v<N>-marked-<k>.png` and `v<N>-mask-<k>.png` |
| `POST /api/scene-marked` | `{"project", "scene", "version", "t", "png"}` | `{"path"}`: `comments/<scene>/v<N>-t<t>-<k>.png`; `version` must be the scene's latest page version, with a render, and `t` within it |
| `GET /scene/<token>/<directory>/<project>/(scenes\|worlds)/<name>/v<N>/<file>` | | a file of a scene or world version, for the scene player's iframe; `<token>` is random per server run and given out only in `page_url` of `/api/project`, another token is 404; `index.html` with `page/scene-player.js` inlined before `</body>` (the file on disk is unchanged); other files with byte ranges as `/file`, so a `<video data-start>` in the page can seek; headers `x-content-type-options: nosniff`, `content-security-policy: sandbox allow-scripts` and `access-control-allow-origin: *`; no symbolic link, hidden part or `..` |
| `POST /api/delete` | `{"project"}` | `{"trash"}`: the project moved to the user's Trash; 409 while a request works on it |

`/api/models` resolves image-gen's tiers as `media:image-gen` does: `fast` takes the task `image`, `image_edit` with
reference images; `best` takes `image_best` and `multi-ref` `image_multi_ref`, with and without them. `tasks` also
holds `speech`, `music` (made music), `video` (the `video` scene engine) and `presenter` (the
`presenter` scene engine). A task that
`config.yaml` does not name, or a missing or broken `config.yaml`, gives null. The page labels each choice with its model
and disables a choice without one. `speech` (`models.speech_models`) lists the voice picker's models: the rows of
`media:voiceover`'s routes for the task `speech` (`ai_models.routes`), the default first, each with its `when` and
`why` and what `ai_models.speech` says it takes (default voice, speed range, style, cloning); the server depends on
`ai-models` for it. `POST /api/request` adds the same `tasks` to each request as `models`, and the
agent records the model id that made a picture in its sidecar (`model_id`).

The mod's endpoints are `POST /event` (send an event to the pages) and `POST /heartbeat`.

The server checks every request before relaying it: the action belongs to the kind's skill, the project is inside its
kind's directory, and the versions, slides and scenes it names exist. It refuses a write that would conflict with a
running request, such as deleting a project in use or uploading a picture for a scene the agent is drawing. Its own
writes of `project.json` and `storyboard.json` hold one lock and replace the file atomically.

`/api/storyboard` carries the modification time of the storyboard the page last read. When the file changed since then
(the agent wrote it), the server answers 409 with the current file and the page shows it. The server then applies the
same structure check as `media:short-video`; `tests/unit/short_video/storyboard_cases.json` holds cases that both
checks are tested against. A page write made between the agent's read and write of the storyboard is lost.

The server answers only the page itself: it requires a `Host` of `127.0.0.1` or `localhost`, refuses POSTs from other
origins and cross-site fetches, and resolves every path and requires it to be inside the root. So no other web page
can send prompts to the session or read files. `/file` answers are sandboxed. The sandboxed scene page has an
opaque origin, so its own scripts load as cross-site: a GET under `/scene/<token>/` is the one exception to the
cross-site refusal, and its POSTs (Origin `null`) are refused. The token keeps another web page from naming a scene
file (for example `timing.js` with the narration) in a `<script src>`. For the same opaque origin, CORS-mode loads of
the scene page (`@font-face`, three.js textures with `crossOrigin`) need `access-control-allow-origin: *` on `/scene/`
answers; it opens nothing more than the cross-site exception, since only a holder of the token can name a file.

In `/api/project`, a scene's `clip` (its newest render) has `page` and `page_url` (the HTML page it was rendered
from: its own `index.html`, or for a cut of a world render the world's `worlds/<world>/v<K>/index.html` named in its
`world.json`; null for other engines), `start` (0, or the scene's start in its world), `world` and `narration` (the
recording it was rendered with).

A scene's `page` is its latest page, rendered or not; null for a scene of another engine or one with no page. For a
plain HTML scene it is the newest `scenes/<scene>/v<N>/` holding `index.html`; for a world scene the newest
`worlds/<world>/v<K>/` holding `index.html` and a `world.json` that names the scene. Fields: `n` (N or K), `page`,
`page_url`, `created` (the `index.html` time), `start`, `duration` (the render's `meta.json`, else the root's `data-duration`, else `timing.json`; for a
world scene `world.json`), `world`, `narration` (the recording of the page's `voice_version`), and `video` (the
`scene.mp4` rendered from that version, or null). `html_films` lists the HTML films, newest first, each
`{"n", "path", "duration", "created", "scenes", "changes"}`: `path` the `film.html`, `duration` the end of its last
segment, `created` and `changes` from the version's `studio.json` (`created` the file's modification time without
one), `scenes` one `{"id", "source"}` per scene of the manifest's segments, `source` the page version directory or
the `scene.mp4` the film plays (null for a card). The page compares `scenes` with each scene's latest page or clip to
show what changed since the newest film.

The server watches the project directories by polling modification times about once a second and sends `changed`
(a project's files changed) and `projects` (a project appeared or went).

The style catalogue and brands come from the brand plugin, which the server finds with `claude plugin list --json`,
else in the repository checkout. It reads `brand:style`'s `catalogue.json` and the brand folders of `brand:brand` and
`BRAND_PATH`, then sends `catalogue`.

## Events

Each event is a JSON object whose `kind` is one of:

| `kind` | Meaning | Sent by |
|---|---|---|
| `request` | a request was accepted | server |
| `state` | `busy`, the `current` request, the `queued` ones, and when the running turn `started` | mod |
| `agent`, `note` | an answer or a progress line from the `post` and `note` tools | mod |
| `turn-start`, `turn-end`, `agent-start`, `tool`, `tool-end`, `text` | the agent's log: turns, subagents, tool calls and text, of the main loop and every subagent | mod |
| `ask`, `ask-done`, `answer` | a tool call waits for approval in Claude Code, and its outcome | mod |
| `stopped` | a request was stopped; the server marks the request's open comment `stopped` in `comments.json` | mod |
| `done` | the turn of a request ended with the agent's answer; the server marks the request's open comment `done` in `comments.json` | mod |
| `changed`, `projects`, `catalogue` | files changed, projects changed, the catalogue loaded | server |
| `ended` | the session ends | mod |

Log events carry the `request` they belong to (null for a turn typed in the terminal or a task notification), the
subagent's `agent` id and a `time`. A subagent belongs to its spawner's request. The server keeps recent log events
and replays them to a page that connects, so a reloaded page shows the conversation and the work in progress.

## Requests

A request has `action`, `kind`, `skill`, `project` and the action's fields. Its `refs` and `sources` are absolute
paths of files in the project's `refs/` and `sources/`, as `/api/refs` and `/api/sources` answer them. The SKILL.md of the workspace skill
defines what the agent does for each action.

Actions of `images`:

| Action | Effect |
|---|---|
| `generate` | new versions from a brief, refs, brand, shape, model (an image-gen tier: `best`, `fast`, `multi-ref`), count and style; a deck: the whole deck, or versions of one slide |
| `change` | a new version from a version, its marks and a note |
| `variations` | variations of a version |
| `other-styles` | a version redrawn in other styles |
| `assemble` | a deck's PowerPoint from the chosen version of each slide |
| `message` | free text to the agent |

A style is a catalogue name, `auto` (the agent picks three suitable styles) or `invent` (the agent makes up three);
the last two make one image in each.

Actions of `videos`:

| Action | Effect |
|---|---|
| `storyboard` | runs `media:short-video`'s `refs` and writes `reference.md` for each reference video (optional for every engine; an HTML film needs only the prompt), writes the storyboard from the brief, sources and references, then the pictures; with `auto` or `invent` style in `step` autonomy, three style samples instead; `make_film` goes on to the film |
| `use-style`, `style-samples` | sets the film's style from a sample (one of the current samples, or an earlier style sample of the key scene: a still with a `page_style`) or the catalogue and redraws the pictures and drawn scenes' pages and stills, or makes three new samples (pictures, or stills of a drawn key scene's page) |
| `change`, `variations`, `other-styles` | as for images, on a scene's picture |
| `use-still` | `scene`, `version` (a still of a drawn scene); a new page version copied from that still's page, with its still: the still's page becomes the film's |
| `add-scene` | writes a new scene and its picture |
| `remake-scene` | redoes one scene as the status command reports: a recording, an HTML scene's page and still (no render), or a manim, video or presenter render |
| `mark-scene` | a comment on a paused frame of an HTML scene's latest page version: `scene`, `version` (that page version), `t` (scene time), `world` and `world_t` (set by the server from the page; null without a world), `mark` (`{point: {x, y}}` or `{rect: {x, y, w, h}}` in frame pixels), `ids`, `marked` (null when the version has no render), `text`; the agent makes the marked still with `stills --mark` when `marked` is null, snapshots the scene with `scaffold`, edits the page, renders only a version that had a render, and posts the still at `t`; the server appends it to `comments.json` |
| `music`, `own-music` | a new track made with `media:music`, or the user's own track, as the next music version |
| `voice-sample` | one sentence in a voice, for the voice picker |
| `make-film` | records the scenes that need it, builds and checks their pages (renders only manim, video and presenter scenes, imports clips), makes music if needed, and writes the next HTML film `film/html/v<N>/film.html`; nothing is assembled |
| `export-mp4` | renders every HTML scene without a render, assembles and checks the next MP4 `film/v<N>/film.mp4` from the current scenes; with `film.review` true, runs the film critic and writes the verified findings, which `auto` autonomy then fixes in one more MP4 |
| `review` | runs the film critic on an MP4 and writes its findings |
| `fix` | the next MP4 and HTML film with chosen findings and a note fixed |
| `phone` | a 9:16 version of an MP4 as a new project, sharing its style and music; it ends with its own HTML film and MP4 |
| `message` | free text, optionally about one scene |

For requests that need the film settings (`remake-scene`, `music`, `make-film`, `export-mp4`, `fix`), the server adds a copy of
`film` taken when the request was accepted.

## Mod

`/studio` starts the server once per session, opens the page and shows its URL in the status line. The mod sends a
heartbeat every 5 s.

The mod runs one request at a time. It submits the next prompt only when the session is idle, and reports the order as
`state`. A turn whose prompt contains a request's prompt makes that request current; a turn typed in the terminal has
no current request.

Stop ends the running turn with `$.turn.abort`, or removes a queued request. An abort does not stop background
subagents or background commands, and each one's completion starts a new main-loop turn with a task notification. After
a stop the mod therefore also ends those turns until the next real prompt. The next prompt it submits names the
stopped requests, since an aborted turn leaves no marker in the conversation. Files that background work wrote stay
as new versions.

The mod sends the log events from hooks on `turn.start`, `turn.complete`, `agent.spawn`, `tool.call` and
`session.append`, and attributes each subagent's events to the request of the agent that spawned it. It sends `ask`
when a tool call shows a permission dialog to the user; the page shows that approval is waiting in Claude Code and
cannot answer it. When a main-loop turn that ran a request ends, the mod sends `done` only for `reason` `answer`;
any other end sends a `note` that the turn ended without finishing, unless the user stopped the request. Such a
comment stays `open`, since no event names a failed request. The server finds the `comments.json` of a request it
did not append in this run by scanning `short-video/*/comments/*/comments.json`, so a `done` or `stopped` after a
server restart still reaches its comment. Events go to the server in order; while the server does not answer, they are dropped and `post` and
`note` fail.

Mod tests: `plugins/studio/tests/register.test.ts`, run by `claude plugin test plugins/studio`.

## Page

The page has three columns. The left column lists the kinds, the current kind's projects, "New project" and Settings.
The centre column is the workspace module of the current kind. The right column is the Claude column: one group per
request with its log, notes and answers, the running request with Stop, approval notices and an input box that sends
`message`. The side columns can be resized and folded. The page always opens a blank workspace ready to type into; the
first request creates the project.

A workspace module registers with `Studio.register` and uses the shell's helpers, both documented at the top of
`shell.js`. The shell's version detail view, with marking and change requests, is shared by every kind.

The workspaces are numbered steps that fold to a one-line summary. The step being worked on opens by itself as the
project advances, and a finished step shows a check.

The image workspace (`images.js`) has the brief, then the style, then the results. A deck adds its slides, the
versions of the selected slide with the choice of the one used, and "Make the PowerPoint".

The short-video workspace (`videos.js`) has two views. The storyboard view has seven steps: what the film is about
(brief, sources, film settings), the picture style, the storyboard (scenes in order, reorderable, with their
pictures), the voice, the music, the scenes (recording, clip or page, and state of each), and the films, newest first:
the newest HTML film plays in an `<iframe sandbox="allow-scripts">` from `/file` with an Export MP4 button, older
HTML films open in a tab; MP4 films have a player, Download, review findings, Fix and Phone version. Review and phone
version exist only on an MP4; before the first export they are not shown. The brief's drop zone takes pictures,
sources and reference videos, which go to `/api/refs`. The storyboard rows and strip show each scene's picture, a
drawn scene's newest still, or the "Drawn scene" placeholder before it has one. The scene view edits one scene: its
picture (a drawn scene: the stills of its page versions, with Send, "Use this still" for a still of an older page, "Use as reference" and Download), its sentences with what is on screen and
optional per-sentence voices, its movement and timing, and a message about the scene. The page writes storyboard edits
directly with `/api/storyboard` and film settings with `/api/film`. Before a storyboard write the page checks the
rules its edits can break (a sentence per scene, filled sentences and briefs, a picture for `video` and
`presenter`, `length` only on an HTML scene without narration, a `world` scene HTML only without a picture, the
scenes of a world next to each other) and shows the problem instead of writing; a refusal shows the server's
error text. A button is disabled while a pending request of
the project would conflict with the one it sends.

The scene player opens below step 6 for a scene with a `page`, with or without `scene.mp4`; other scenes play their
`scene.mp4`. The page loads `page_url` in an `<iframe sandbox="allow-scripts">` and owns time: playing, `t` is the
narration's `<audio>` time, or a `performance.now` clock for a silent scene. Messages (`postMessage`, times in
seconds, marks in frame pixels):

| Message | Direction | Content |
|---|---|---|
| `sv:seek` | page to player | `t`: `start + t`; the player seeks `window.__timelines[<root id>]`, dispatches `hf-seek` and sets each `<video data-start>` |
| `sv:ready` | player to page | `width`, `height`, `duration` of the root `[data-composition-id]`, `errors`; sent on load, after which the page seeks to its `t` |
| `sv:query` | page to player | `qid` and `point: {x, y}` or `rect: {x, y, w, h}` |
| `sv:hits` | player to page | `qid`, `t`, `ids`: the visible elements with an id under the mark, innermost first, without the full-frame layers `root`, `bg-fill`, `bg-image`, `bg-video`, `anchored` |

Paused, the user marks a point or a box (the shell's `drawMarks`). Send stays disabled until `sv:hits` arrives or
1 s passes (then `ids` is empty). When the page version has a `video`, Send draws its frame at `t` with the mark from a
hidden `<video>` and writes it with `/api/scene-marked`; without one it sends no still (`marked` null). Then it sends
`mark-scene`. Open comments of the scene show Stop. When the scene gets a newer page version, the player loads it and
seeks to the same `t` after `sv:ready`; a new render of the same version only sets `video`.

## Skills

`studio:images` defines the image, infographic and deck project formats and the answer to each action. An
`infographic` is made with `media:infographic`'s design rules and a deck with `media:pptx-author`'s bespoke design path
(content in `slides.md`, one `media:image-gen` image per slide, images-only or native assembly), while the files and
versions stay Studio's.

`studio:videos` defines the short-video project format and the answer to each action. It loads `media:short-video` for
the storyboard, recordings, scenes, music import, assembly and the phone version; `media:image-gen` for the scene
pictures; `media:voiceover` for recordings and samples; `media:music` for tracks; and `brand:style` and `brand:brand`
for styles and brands.
