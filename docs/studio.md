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
| `refs/`, `sources/` | the user's reference pictures, sources and own music tracks; the agent's research sources and generated tracks | page, agent |
| `images/<scene>/v<N>.png`, `.json` | the pictures of a scene, as image versions | agent; page for the user's own picture |
| `voice/<scene>/v<N>/`, `scenes/<scene>/v<N>/`, `music/v<N>/`, `film/v<N>/` | `media:short-video`'s recordings, rendered scene clips, music and films; complete once their `meta.json` (a film: `manifest.json`) exists | `media:short-video` |
| `music/v<N>/studio.json`, `film/v<N>/studio.json` | Studio's notes on a track (made or own, its brief) and on a film (what changed since the previous one) | agent |
| `film/v<N>/review.json` | the film critic's findings on film N that the agent verified | agent |
| `samples/voice-<k>/` | voice samples for the voice picker | agent |

`project.json` adds `film` (the film settings below), `style` (the film's picture style, possibly invented),
`scene_styles` (scenes with their own style), `samples` (three sample pictures while the user picks a style) and, in a
phone version, `origin`.

`storyboard.json` is the structure `media:short-video` parses `storyboard.md` into, plus per-sentence voice settings.
Each scene has an `id` that names its directories and never changes; a new scene never reuses the id of a deleted one,
so it inherits none of its files. A scene has `narration` (its sentences), `beats` (what is on screen during each
sentence), optionally per-sentence `speakers` and `voices`, and the keys of its form: a template scene (`title`,
`summary`, `end`), an HTML scene with a picture, a drawn scene (an HTML scene without `image`, whose page draws a
diagram or text), a `manim` scene, a `video` scene (the config task `video` animates its picture from its
`brief`) or a `clip` scene. The page sets a scene's `engine` (`html`, `manim` or `video`). A scene's picture is the version its `image` names.

The film settings, `film` in `project.json`:

| Key | Value | Default |
|---|---|---|
| `voice` | `backend` (`kokoro`, `speech` for the configured online speech model, `chatterbox` for the user's cloned voice), `name` (null: the backend's default voice), `speed`, `style` | `kokoro`, no name |
| `music` | `mode` (`made`, `own`, `none`), `brief`, `volume`, `version` (the track to use, or the newest) | `made` |
| `shape` | `16:9` or `9:16`, fixed once the storyboard has scenes | `16:9` |
| `length` | 30, 60, 120 or 180 seconds | 60 |
| `author` | names for the creator credit | from the `AUTHOR_NAME` setting |
| `brand` | brand name or null | null |
| `review` | whether `make-film` runs the film critic | true |

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
| `GET /api/project?dir=` | | `{"dir", "project": <project.json>, "versions", "refs"}`; a deck adds `deck` (slides, chosen versions, assembled decks), a short video `video` (storyboard, scene states, pictures, recordings, clips, music, films, samples) |
| `GET /api/catalogue` | | `{"styles": [{"name", "description", "tags", "suits", "sample"}], "brands"}`; `loading` true until loaded, `error` when the brand plugin or its catalogue is missing |
| `GET /file?path=[&download=1]` | | a file inside the root or a catalogue sample image, with byte ranges so audio and video can seek |
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
| `POST /api/refs` | `{"project", "name", "data": <data URL>}` | `{"path"}`: `refs/<name>`, PNG, JPEG or WebP |
| `POST /api/sources` | `{"project", "name", "data"}` | `{"path"}`: `sources/<name>`, a source or music file |
| `POST /api/picture` | `{"project", "scene", "name", "data": <PNG data URL>}` | `{"version", "path"}`: the user's own picture as the scene's next version |
| `POST /api/marked` | `{"project", "version", "png", "mask"}` (`mask` optional) | `{"path", "mask"}`: `marks/v<N>-marked-<k>.png` and `v<N>-mask-<k>.png` |
| `POST /api/delete` | `{"project"}` | `{"trash"}`: the project moved to the user's Trash; 409 while a request works on it |

`/api/models` resolves image-gen's tiers as `media:image-gen` does: `fast` takes the task `image`, `image_edit` with
reference images; `best` takes `image_best` and `multi-ref` `image_multi_ref`, with and without them. `tasks` also
holds `speech` (the online voice), `music` (made music) and `video` (the `video` scene engine). A task that
`config.yaml` does not name, or a missing or broken `config.yaml`, gives null. The page labels each choice with its model
and disables a choice without one. `POST /api/request` adds the same `tasks` to each request as `models`, and the
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
can send prompts to the session or read files. `/file` answers are sandboxed.

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
| `stopped` | a request was stopped | mod |
| `changed`, `projects`, `catalogue` | files changed, projects changed, the catalogue loaded | server |
| `ended` | the session ends | mod |

Log events carry the `request` they belong to (null for a turn typed in the terminal or a task notification), the
subagent's `agent` id and a `time`. A subagent belongs to its spawner's request. The server keeps recent log events
and replays them to a page that connects, so a reloaded page shows the conversation and the work in progress.

## Requests

A request has `action`, `kind`, `skill`, `project` and the action's fields. The SKILL.md of the workspace skill
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
| `storyboard` | writes the storyboard from the brief and sources, then the pictures; with `auto` or `invent` style in `step` autonomy, three style samples instead; `make_film` goes on to the film |
| `use-style`, `style-samples` | sets the film's style from a sample or the catalogue and redraws the pictures, or makes three new samples |
| `change`, `variations`, `other-styles` | as for images, on a scene's picture |
| `add-scene` | writes a new scene and its picture |
| `remake-scene` | records and renders one scene as the status command reports |
| `music`, `own-music` | a new track made with `media:music`, or the user's own track, as the next music version |
| `voice-sample` | one sentence in a voice, for the voice picker |
| `make-film` | records and renders the scenes that need it, makes music if needed, assembles and checks the next film; with `film.review` true, runs the film critic and writes the verified findings, which `auto` autonomy then fixes in one more film |
| `review` | runs the film critic on a film and writes its findings |
| `fix` | the next film with chosen findings and a note fixed |
| `phone` | a 9:16 version of a film as a new project, sharing its style and music |
| `message` | free text, optionally about one scene |

For requests that need the film settings (`remake-scene`, `music`, `make-film`, `fix`), the server adds a copy of
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
cannot answer it. Events go to the server in order; while the server does not answer, they are dropped and `post` and
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
pictures), the voice, the music, the scenes (recording, clip and state of each), and the films (player, review
findings, Fix, phone version). The scene view edits one scene: its picture, its sentences with what is on screen and
optional per-sentence voices, its movement and timing, and a message about the scene. The page writes storyboard edits
directly with `/api/storyboard` and film settings with `/api/film`. A button is disabled while a pending request of
the project would conflict with the one it sends.

## Skills

`studio:images` defines the image, infographic and deck project formats and the answer to each action. An
`infographic` is made with `media:infographic`'s design rules and a deck with `media:pptx-author`'s bespoke design path
(content in `slides.md`, one `media:image-gen` image per slide, images-only or native assembly), while the files and
versions stay Studio's.

`studio:videos` defines the short-video project format and the answer to each action. It loads `media:short-video` for
the storyboard, recordings, scenes, music import, assembly and the phone version; `media:image-gen` for the scene
pictures; `media:voiceover` for recordings and samples; `media:music` for tracks; and `brand:style` and `brand:brand`
for styles and brands.
