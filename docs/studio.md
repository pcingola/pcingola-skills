# studio

The `studio` plugin is a web page in the user's browser for making images, infographics and slide decks (later short
videos) with Claude. The page, a local server and a mod (the plugin's hooks module) pass every action in the page to
the Claude Code session as a request; the agent carries it out with the skills. The mod and the server call no skill
CLI.

## Pieces

| Piece | Location | Role |
|---|---|---|
| Mod | `plugins/studio/hooks/register.ts` | `/studio` command; starts the server; turns requests into prompts; tools `post` and `note`; busy and queue state; permission asks; heartbeat |
| Server | `plugins/studio/server/` (uv project, package `studio_server`, wrapper `studio-server.sh`) | serves the page and project files on `127.0.0.1`; relays requests to the mod and events to the page |
| Page | `plugins/studio/server/page/` | shared shell (`index.html`, `studio.css`, `shell.js`) and one workspace module per workspace skill (`images.js`) |
| Skills | `plugins/studio/skills/<skill>/SKILL.md` | project format of a workspace and how the agent answers each request action (`studio:images`) |

## Kinds of project

The left column of the page lists kinds of project. Each kind has a projects directory under the root and a
workspace skill, `studio:<skill>`, which answers its requests and whose page module draws its workspace:

| `id` | `label` | `directory` | `skill` | `ready` |
|---|---|---|---|---|
| `image` | Images | `images` | `images` | true |
| `infographic` | Infographics | `infographics` | `images` | true |
| `slide` | Slides | `slides` | `images` | true |
| `short-video` | Short videos | `short-video` | `short-video` | false |

The kinds are `KINDS` in `server/studio_server/projects.py`.

The server is a standard-library Python program; its only dependency is `plugin-settings` (git source on branch
`main`), with which it reads `STUDIO_DIR` and the brand plugin's `BRAND_PATH`. The wrapper sources `plugins/studio/lib/uv_env.sh` and calls `plugin_env`
like every skill wrapper, so its environment lives in the plugin data directory. Every page asset is served by the
server; the page loads nothing from another host.

## Projects root

`STUDIO_DIR` (default `~/Documents/Studio`, `~` expanded; a relative path is refused) holds the directory of each
kind: `images`, `infographics`, `slides`, `short-video`. A project is `<root>/<directory>/<project>/` with a
`project.json`; a project of kind `slide` is a deck (Decks below). The server creates the root and the kinds' directories when missing. An empty `<root>/infographic/`
left by earlier versions is neither created nor read. Every request the page sends carries the project's absolute
directory, so the skills read no setting.

## Server

Started by the mod with `$.process.spawn` as `studio-server.sh`; listens on `127.0.0.1` at a free port.

stdout carries one JSON object per line to the mod:

| Line | When |
|---|---|
| `{"type": "ready", "url": "http://127.0.0.1:<port>"}` | listening |
| `{"type": "request", "request": {...}}` | the page sent a request; `request` as in Requests below, with `id` and `time` added |

The style catalogue is a committed file of the brand plugin, `skills/style/references/catalogue.json`, written by
`brand:style`'s `index` command with `references/index.md`: per style `name`, `description`, `tags`, `suits` and
`sample` (path relative to the style skill's directory). After `ready`, in a thread, the server finds the brand
plugin's folder with `claude plugin list --json` (`claude` found with `shutil.which`, so `claude.cmd` on Windows;
10 s timeout): entries with `enabled: false` ignored, the `brand@<marketplace>` entry of the marketplace of the
listed `studio@<marketplace>` entry, else the first `brand@*` entry; its `readFromFolder`, else its `installPath`. When the command
is missing, fails or lists no brand plugin, the folder is the `brand` directory next to the studio plugin (the
repository checkout). The server reads the file, makes each `sample` absolute and allows exactly those paths in
`/file`; a style without a string `name` and `sample` is left out. The brand names, listed whenever the brand plugin is found, whatever the state of the file, are the folders holding a
`brand.yaml` in the brand skill's `brands/`, then in each directory of `BRAND_PATH` (colon-separated, `~` expanded,
first folder of a name wins), as the brand CLI lists them; `BRAND_PATH` is the setting of `config.yaml`, else the
process environment (`plugin_settings.get`), as the brand CLI reads it. When loading
ends the server broadcasts `{"kind": "catalogue"}`. Claude takes no part.

stderr is a log. The server exits when no heartbeat arrived for 20 s, counted from start, and, on macOS and Linux,
as soon as the process that started the wrapper is gone (the spawn closes stdin from the start, so stdin EOF says
nothing). `uv run` keeps Python as its child, so the wrapper passes `--parent-pid "$PPID"`; the server checks that
process with `os.kill(pid, 0)` and its own parent id.

HTTP endpoints of the page:

| Method and path | Answer |
|---|---|
| `GET /` | `page/index.html` |
| `GET /static/<file>` | a file of `page/`; nothing outside it |
| `GET /api/config` | `{"root": <abs>, "kinds": [{"id": "image", "label": "Images", "directory": "images", "skill": "images", "ready": true}, ...]}`, the kinds in the order of Kinds of project; `ready` is false for kinds whose phase is not done |
| `GET /api/projects?kind=<id>` | `[{"dir": <abs>, "name", "brief", "updated": <ISO time>, "versions": <number of complete versions>}]`, newest first, from each `project.json` under `<root>/<directory of the kind>/`; for a deck `versions` counts the complete versions of its slides and `slides` is its number of slides |
| `GET /api/project?dir=<abs>` | `{"dir", "project": <project.json>, "versions": [<v<N>.json> + {"n": N, "image": <abs path of v<N>.png>}], "refs": [<abs paths in refs/>]}`, versions newest first; a version whose PNG is missing or whose JSON is not an object is left out. A deck's `versions` is empty and it has `deck`: `{"slides_md": <text of slides.md or null>, "slides": [{"k", "title", "dir": <abs slide-<k>>, "versions": [as above, of slide-<k>/], "chosen": N or null, "error": <message, only for a slide-<k> link out of the deck>}], "decks": [<deck-<N>.json> + {"n": N, "path": <abs deck-<N>.pptx>}]}`, slides in deck order, decks newest first; `chosen` is `chosen["<k>"]` of `project.json` when that version exists, else the newest version, else null; a deck whose `.pptx` or sidecar is missing is left out |
| `GET /api/catalogue` | `{"styles": [{"name", "description", "tags": [...], "suits": [...], "sample": <abs path>}], "brands": [<name>, ...]}`; `{"styles": [], "brands": [], "loading": true}` until loading ends; empty lists with an `error` when the brand plugin was not found; `styles` empty with an `error`, `brands` still listed, when its file is missing or not a JSON list |
| `GET /file?path=<abs>[&download=1]` | the file, when it is inside the root or is a sample image of the catalogue; 403 otherwise; `download=1` adds `content-disposition: attachment` |
| `GET /events` | server-sent events, `data: <JSON>` per event (below) |
| `POST /api/request` | body: a request; the server checks `action` and `project` (inside the root), adds `id` and `time` (ISO 8601 local time with offset), broadcasts it as a `request` event, writes it to stdout; 202 with `{"id", "project"}`; 400 with a message otherwise; 503 when it cannot be written to stdout |
| `POST /api/marked` | `{"project", "version": N, "png": <data URL>, "mask": <data URL>}` (`mask` optional; for a deck also `slide`, required, and every path below is in that slide's `slide-<slide>/` instead of the project): writes a new `marks/v<N>-marked-<k>.png` in the project (k numbered from 1, never overwritten, so a queued change keeps its own marks); answers `{"path": <abs>}`. With `mask`, a PNG of the pixel size of `v<N>.png` (both read from the PNG header), it also writes `marks/v<N>-mask-<k>.png` with the same k (replacing a mask left with that k by a deleted marked copy) and answers `{"path": <abs marked copy>, "mask": <abs mask>}`; a mask that is not a PNG or not of that size is a 400 and nothing is written |
| `POST /api/refs` | `{"project", "name", "data": <data URL>}`: writes `refs/<name>` (name reduced to a safe file name, numbered when taken); answers `{"path": <abs>}` |
| `POST /api/new` | `{"kind", "autonomy"}` (autonomy optional, `step` by default): creates an untitled project (`name` "Untitled", empty `brief`, `kind`, for a deck `assembly` `images` and `chosen` `{}`, folder `<root>/<directory of the kind>/untitled`, `-2`, `-3` when taken) for a reference image added to a blank workspace; answers `{"project": <abs>}`. The first `generate` on it sets `name` (from the brief's first words) and `brief` in `project.json`; the folder keeps its name |
| `POST /api/autonomy` | `{"project", "autonomy": "step" \| "auto"}`: sets `autonomy` in `project.json` (read, change, atomic replace); the agent reads `project.json` again right before each write and keeps `autonomy` as found, so the two writers lose at most a change made in that short window |
| `POST /api/chosen` | `{"project", "slide": k, "version": N}` (a deck; k a slide of the deck with an existing directory, N an existing version of it): sets `chosen["<k>"]` to N in `project.json` the same way; answers `{"chosen": <the map>}`. `chosen` has two writers like `autonomy`: the page through this endpoint, and the agent, which sets it to `{}` on a `generate` that rewrites the deck and removes `"<k>"` on a `generate` of slide k, reading `project.json` again right before writing |
| `POST /api/assembly` | `{"project", "assembly": "images" \| "native"}` (a deck): sets `assembly` in `project.json` the same way; answers `{"assembly"}` |

The server's own changes of `project.json` (these three endpoints and the naming of an untitled project) each hold one
lock across the read, the change and the atomic replace, so two requests at once both land.

Endpoints of the mod:

| Method and path | Effect |
|---|---|
| `POST /event` | broadcasts the JSON body to the pages as one event |
| `POST /heartbeat` | resets the 20 s timeout |

Every path in a request body or query is resolved (symbolic links followed) and checked before use. Every request
needs `Host` `127.0.0.1:<port>` or `localhost:<port>` (DNS rebinding), and a POST needs no `Origin` (the mod) or the
server's own origin, so no other web page in the browser can send prompts to the session; a request whose
`Sec-Fetch-Site` is present and neither `same-origin` nor `none` is refused too, so no other web page can open
`/events` or probe `/file`; 403 otherwise. `/file`
answers carry `content-security-policy: sandbox` and `nosniff`. Errors are `{"error": <message>}`: 400 for a bad
field or a project path not of the form `<root>/<directory of a kind>/<name>` (of the request's kind, for
`/api/request`), 404 for a missing project or `project.json`, 413
for a body over 64 MiB. `/api/refs` accepts PNG, JPEG and WebP and makes the suffix match the type. A version named
in `change`, `variations`, `other-styles` or `/api/marked` must exist (in a deck, in the slide's directory); `generate`
refs must be files inside the root; `message` is accepted for every kind, the other actions for the kinds whose skill
is `images`, and `assemble` for decks only. A `slide` is refused outside decks, on `assemble` and on a `message`
without a project; wherever else a deck request or body carries it (`change`, `variations`, `other-styles`,
`message`, `/api/marked`, `/api/chosen`), it must be k from 1 to the number of slides with an existing `slide-<k>/`,
and a `generate` may also name a listed slide without a directory yet or k one past the last (a slide to add, with a
non-blank `brief`). A `slide-<k>` that is a symbolic link, dangling included, must resolve to a directory directly
in the deck; otherwise every request and write naming that slide is a 400. In `/api/projects`, `updated` is the
newest file time in the project (UTC) and an unreadable `project.json` lists the project under its directory name.

The server watches each project's top level, `refs/` and `marks/`, and in a deck each `slide-<k>/` and
`slide-<k>/marks/` (polling modification times about once a second, from after `ready`; links not followed) and
broadcasts `{"kind": "changed", "project_kind": <kind id>, "project": <abs dir>}` when a file in a project changed and
`{"kind": "projects", "project_kind": <kind id>}` when a project appeared or went (`kind` names the event, so the kind
of project is `project_kind`).

## Decks

A project of kind `slide` is a deck: its content and speaker notes are `slides.md` (`media:pptx-author`'s dialect) and
each slide is an image with versions. The agent writes `deck.json`, the slides in deck order as
`[{"k": 1, "title": ...}, ...]`, so the server reads the slides without parsing Markdown. The number of slides is the
length of the list in `deck.json` (0 for an empty list, whatever `slide-<k>/` directories remain), or, without a
`deck.json` holding a list, the number of directories `slide-1`, `slide-2`, ... without a gap; a slide's title is
`""` when its entry has none. A slide whose `slide-<k>` is a link not resolving to a directory directly in the deck
is listed by `/api/project` with an `error` message, no versions and `chosen` null, and `assemble` is refused while
the deck has one. Slide k's directory `slide-<k>/` holds exactly the files of an image project
(`v<N>.png`, `v<N>.json`, `marks/`); `refs/` stays at the deck level. `project.json` also has `assembly` (`images`,
the default, or `native`) and `chosen` (`{"<k>": N}`, written by the page and the agent, see `/api/chosen`); a new
deck's `project.json` (made by a `generate` with `project` null or by `/api/new`) has `assembly` `images` and
`chosen` `{}`. Assembled decks are `deck-<N>.pptx` with a
`deck-<N>.json` sidecar (`assembly`, `versions`, `created`), numbered and never overwritten. The full file list is in
`studio:images`.

## Events to the page

| `kind` | Fields | Sent by |
|---|---|---|
| `request` | `request` | server, on each accepted request |
| `agent` | `text`, `images` (abs paths, optional) | mod, from the `post` tool |
| `note` | `text` | mod, from the `note` tool |
| `state` | `busy` (bool), `current` (request id or null), `queued` (request ids) | mod, whenever one of them changes |
| `ask` | `tool`, `text` (what waits for approval) | mod, when a tool call waits for approval in Claude Code |
| `ask-done` | | mod, when that call was answered |
| `turn` | `reason` | mod, at `turn.complete` |
| `changed`, `projects` | as above | server |
| `catalogue` | | server, when the style catalogue finished loading (`/api/catalogue` has it or its error) |
| `ended` | | mod, before the session ends, when it can |

The server keeps the session's `request`, `agent`, `note`, `turn` and `ended` events (the last 1000) and the last `state` and any open `ask` (cleared by `ask-done` or `ended`; `ended` also sets `busy` false), and sends them, in order and followed by `{"kind": "replayed"}`, to a page when it connects to `/events`, so a reloaded page shows the conversation and the work in progress.

## Requests

A request is a JSON object with `action`, `kind`, `skill` and `project` (absolute project directory) plus the
action's fields. The page sends it with `skill` the kind's workspace skill; the server fills in a missing or null
`skill` from `kind`, refuses one that is not the kind's, refuses a `project` outside the kind's directory, and adds
`id` and `time`; the mod wraps it in a prompt that names the workspace's skill (`studio:<skill>`) and carries the
JSON verbatim. Actions of `images` (kinds `image`, `infographic`, `slide`):

| `action` | Fields |
|---|---|
| `generate` | `brief`, `refs` (abs paths), `brand` (name or null), `shape` (`1:1`, `4:3`, `16:9`, `9:16`), `model` (an image-gen tier: `best`, `fast`, `multi-ref`; the older names `gpt-image-2`, `nano-banana-pro`, `nano-banana-2` are accepted), `count`, `style` (a style name; `"auto"`: the agent picks three catalogue styles that suit the brief and makes one image in each; `"invent"`: the agent makes up three styles for this image, clearly different from each other, without using or checking the catalogue, each with a name, a one-line description, a style line and a palette, and makes one image in each; they are not saved anywhere). `project` null starts a new project, with a non-blank `brief` and optional `autonomy` (`step`, the default, or `auto`): the server creates `<root>/<directory of the kind>/<slug>` from the brief's first words (slug: NFKD to ASCII, lower case, each run of other characters `-`, trimmed, at most 40 characters; `-2`, `-3` when taken) with a `project.json` (`name`: those words, `brief`, `kind`, `created`, `autonomy`, `settings: {}`, and for a deck `assembly: "images"` and `chosen: {}`), fills in `project`, and answers it in the 202 body as `{"id", "project"}`; when the request cannot be written to stdout (503), the new directory is removed |
| `change` | `version` (N), `marks` (below), `note` (general change note), `marked` (abs path of an existing `marks/v<N>-marked-<k>.png` of that version; null only when `marks` is empty), `mask` (abs path of the existing `marks/v<N>-mask-<k>.png` with the k of `marked`; null only when `marks` is empty); at least one mark or a note |
| `variations` | `version`, `count` (3) |
| `other-styles` | `version`, `styles` (names; empty: the agent picks three other styles) |
| `assemble` | decks only: `assembly` (`images`: each slide's chosen image full-slide, not editable; `native`: `media:pptx-author`'s native backport, editable); the server adds `versions`, `{"<k>": N}`, the chosen version of every slide when the request is accepted, and refuses a deck without slides, with a slide without a version or with a slide listed with an `error` |
| `message` | `text`; `project` may be null; in a deck optionally `slide`, the slide it is about |

In a deck, `change`, `variations` and `other-styles` carry `slide` (k) and act within `slide-<k>/`. A deck's
`generate` has `shape` `16:9` and `slide`: null makes or rewrites the whole deck (the agent writes `slides.md` and
`deck.json` from the brief and refs, then one image per slide, in one style for the deck; `count` is the number of
slides, or null for the agent to decide); k makes `count` images of slide k (`brief` empty: the slide as `slides.md`
has it; else what to change, or for k one past the last what the new slide shows) with `style` `"auto"`, required:
the slide is made in the deck's current style, which the agent reads from the sidecars of the slides' chosen
versions.

A mark is `{"n": <1-based number>, "kind": "box" | "point" | "loop", "comment"}` with, as fractions of the image's
width and height, `x`, `y`, `w`, `h` for a box, `x`, `y` for a point and `points` (`[[x, y], ...]`) for a loop. The
marked copy is the version's image with every mark drawn in red with its number. The edit mask is a PNG of the
version image's pixel size, opaque black except inside the marks, where alpha is 0: a box's rectangle, a loop's
filled polygon, a circle of radius 8% of the image's shorter edge around a point, each grown by 2% of the shorter
edge on every side (rounded at corners). Every pixel has alpha 0 or 255. A model that takes a mask (gpt-image-2,
local `diffusers` models with an inpaint pipeline) may change the image only where alpha is 0; the mask guides the model and nothing is
composited afterwards. On a model without a mask, the agent edits from the image and the marked copy alone.

The `model` field is an image-gen tier, chosen in the page's "Quality" selector. The agent passes it to image-gen as
`--tier`, and image-gen takes the model of the tier's task in its config: `best` takes `image_best`, `multi-ref` takes
`image_multi_ref`, `fast` takes `image` (`image_edit` with reference images). The page and the server accept the older
names `gpt-image-2`, `nano-banana-pro` and `nano-banana-2` from saved settings, and the page shows them as their tiers
(`best`, `multi-ref`, `fast`). The server refuses any other value.

"Use as reference" and "Download" act in the page only.

## Mod

`/studio` starts the server once per session (later calls reuse it), opens the page (`open` on macOS,
`cmd /c start "" <url>` on Windows, `xdg-open` on Linux), shows the URL in the status line, posts a heartbeat every
5 s with `$.clock.every`, and turns each `request` line into a `$.prompt.submit`. `$.prompt.submit` queues a prompt
until the session is idle; the mod keeps the order of the requests it submitted and reports it as `state`: `busy`
holds from the main loop's `turn.start` to its `turn.complete` (subagent turns change nothing). A `turn.start`
whose text contains a pending request's prompt makes that request current; a turn matching none (typed in the
terminal) has `current` null. While idle, `current` is the first pending request and `queued` the rest. A submission
the engine drops or refuses leaves the order. `/studio` waits up to 5 s for `ready`, since a hook has 10 s and the first build of the server's environment
can take longer; after that it answers that Studio is starting and opens the page when `ready` arrives. A request
whose `skill` is not `[a-z0-9-]+` is skipped. The prompt names the request's `skill`, so every kind of `images`
goes to `studio:images`, with `kind` in the JSON.

Events go to the server through one serial chain, each POST bounded to 2 s; hooks do not wait on it except the two tools. Tools, each served by a `tool.call` hook on the exact name `$.tool.register` returned (`mcp__studio__<name>`), refused while the server is not running or does not accept the POST:

| Tool | Input | Effect |
|---|---|---|
| `post` | `text`, `images` (abs paths, optional) | an `agent` event: an answer in the Claude column |
| `note` | `text` | a `note` event: a progress line |

A `tool.check` hook records each call whose settled verdict is `ask`; a `classic.PermissionRequest` hook, when nothing
beneath it decided (so the dialog is shown to the person, not settled by a classifier or a settings hook), matches
the recorded call by tool and input and sends `ask` with the tool and a short description of the call, and
`ask-done` when the call's `tool.call` settles (after the tool ran or the approval was refused) or the main turn ends;
with several asks open, one `ask-done` follows the last. The page shows "waiting for your approval in Claude Code"
and does not answer it. The platform for opening the page: `OS=Windows_NT` is Windows, else `uname -s` (`Darwin`
macOS, other Linux). Mod tests: `plugins/studio/tests/register.test.ts`, run by `claude plugin test plugins/studio`.

## Page

One shell for every kind: the left column (the kinds of `/api/config`, those not ready or without a module shown
as "soon"; the projects of the current kind; "New project"; Settings with appearance light, dark or system), the Claude column on the right (requests, notes, answers, the
waiting-for-approval notice, the queue notice, the input box, ⌘ Enter or Ctrl Enter sends a `message`), the version
detail view with marking (box, point, freehand loop; a comment per mark; a general change note), the server
connection (`/events`, reconnecting) and one stylesheet with a light and a dark colour scheme for all three columns.
A workspace module registers with the shell under its workspace skill and draws the centre column for each kind
with that skill; the shell gives it the kind, and every request it sends carries the current `kind` and its `skill`.
It reuses the shell's detail view, so every kind marks and edits the same way. The page never waits on the user to
get started: it always opens a blank workspace of the current kind ready to type into; previous projects are in the left column, and "New project" opens a
blank workspace at once. Its first `generate` creates the project; a reference image added before that first creates
an untitled project with `POST /api/new`, which the first `generate` names. The theme choice and the last kind are kept in `localStorage`. The module interface
(`Studio.register`) and the helpers the shell gives modules are documented at the top of `shell.js`. The marked copy
is drawn at the image's natural size in one fixed red, whatever the theme; the edit mask is drawn at the same size
from the same mark shapes.

The image workspace (`images.js`) serves the kinds `image`, `infographic` and `slide` and looks and behaves the same
for each, except:

| Kind | Step 1 asks | Styles listed in step 2 | Default shape |
|---|---|---|---|
| `image` | what the image should show | every catalogue style | Photo (4:3) |
| `infographic` | what the infographic should explain (one concept) and from which facts | styles whose `suits` includes `infographic` | Photo (4:3) |
| `slide` | what the deck is about (audience, message, facts), and the number of slides or "Let Claude decide" | styles whose `suits` includes `slide` | Slide (16:9), fixed |

The "Let Claude choose" and "Invent new styles" cards are shown for every kind; for a deck they choose or invent one
style for the whole deck. An opened project keeps the shape of its last `generate`.

A deck adds, below step 2, once it has slides or its first `generate` is pending: 3, its slides (the chosen
version's thumbnail, number, title and number of versions, a card for the deck's pending `generate`, and "+ Add a
slide"); 4, the versions of the selected slide in the results step, with the chosen one marked "In the PowerPoint",
a box and button for a new version of that slide (`generate` with `slide`) or, for the added slide, what it should
show (the page sends `count` 1 and `style` `"auto"`, whatever step 2 shows); and "Make the PowerPoint", numbered 5
while a slide is selected and 4 otherwise (step 4 is then hidden): the choice "Images only (fast, not editable)" or "Editable PowerPoint (slower)"
(saved with `/api/assembly`), the button sending `assemble` (disabled while a slide has no image) and the assembled
decks with their assembly, versions, time and Download. A slide listed with an `error` shows "Cannot be read". The detail view of a slide version carries the `slide` in its
change, variations and other-styles requests and its `/api/marked` body (`changeFields`), is titled "<deck> · slide
k · vN", and has "Use this version" (`/api/chosen`) when the version is not the chosen one. The action bar's
"Generate the deck" asks for confirmation before rewriting a deck that has slides. An opened deck scrolls to its
slides.

## Skills

`studio:images` defines the project format of the kinds `image`, `infographic` and `slide` and how the agent
answers each action. The request's `kind` decides how the image is made: `image` as `studio:images` describes;
`infographic` with `media:infographic`, loaded with the Skill tool, for the one concept, what the image shows and
how it explains, the facts and text on the image (from the brief and the reference files only) and its checks of
the result, while the project files, versions, sidecars, paths and actions stay those of `studio:images` and
`media:infographic`'s output directory and `notes.md` do not apply; with style `"auto"` an infographic's catalogue
styles are among those whose `suits` includes `infographic`; `slide` with `media:pptx-author`'s bespoke design path
(content in `slides.md`, one `media:image-gen` image per slide, images-only assembly or native backport), whose
working layout maps onto the deck as `studio:images` states: `slides.md`, `checklist.md` and `working.md` at the deck
level, the approved image of slide k its chosen `slide-<k>/v<N>.png` read in place, the deliverable `deck-<N>.pptx`
inside the deck, and the assembly's working files in `work/deck-<N>/`; the page's requests answer `media:pptx-author`'s
approval gates. Project files of an image or infographic project (a deck's are in `studio:images`):

| File | Content |
|---|---|
| `project.json` | `name`, `brief`, `kind` (written by the server; absent in projects made before kinds, all under `images/`), `created` (the request `time`), `autonomy` (`step` or `auto`), `settings` (the last `generate` fields) |
| `v<N>.png` | version N, numbered from 1 in the order made |
| `v<N>.json` | `prompt` (sent to the model), `scene` (what the image shows, without style line and palette; a `change` copies it from its source), `refs` (abs paths of the user's reference images and the brand logo, if used; the source version and the marked copy excluded; later versions made from this one keep them), `style`, `brand`, `model`, `shape`, `action`, `change` (`note` and `marks`, or null), `source` (N of the version it came from, or null), `created` (the request `time`), `invented` (`name`, `description`, `style_line`, `palette` of an invented style, else absent; versions made from it keep it), `kind` (the request's `kind`) |
| `refs/` | reference images |
| `marks/v<N>-marked-<k>.png` | a marked copy of version N sent with a change, one per change request |
| `marks/v<N>-mask-<k>.png` | the edit mask of a change of version N, one per change request with marks, written by the page with the k of its marked copy |

The agent writes `v<N>.json` after `v<N>.png`, so a version the server shows is complete.
