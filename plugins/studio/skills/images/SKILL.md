---
name: images
description: "Carries out Studio page requests on image, infographic and slide deck projects: generation in chosen, auto-picked or invented styles, marked changes, variations, PowerPoint. TRIGGER when: a prompt carries a Studio request JSON naming studio:images."
allowed-tools: Skill Read Write Glob
metadata:
  version: "0.1.0"
---

# Studio Images

The Studio page in the user's browser sends each action on an image, infographic or slide deck project as a request JSON
inside a prompt that names `studio:images`. This skill defines the project format and how to carry out each request
`action`. The images are made by loading `media:image-gen`; styles come from `brand:style` and brand colours from
`brand:brand`. Every answer goes to the page through the `mcp__studio__note` and `mcp__studio__post` tools.

## Kinds

The request's `kind` decides how the image is made:

- `image`: as this skill describes.
- `infographic`: one image that explains one concept. Load `media:infographic` with the Skill tool and follow it for
  choosing the one concept, what the image shows and how it explains, the facts and text on the image (taken only
  from the request's `brief` and the reference files it names or holds) and its checks of the result. Everything
  else is this skill's: the project files, version numbers, sidecars, paths, actions and answers. The output
  directory, file names and `notes.md` of `media:infographic` do not apply; the post lists each fact on the image
  with where in the brief or which reference file it came from.
- `slide`: a slide deck, made with `media:pptx-author`'s bespoke design path: the project is a deck and each slide is
  an image with versions, as [Slide decks](#slide-decks) describes. Everything this skill says of an image project
  applies to each slide inside its `slide-<k>/` directory.

## Project files

A project is the request's `project` directory (absolute). Every file this skill writes is inside it.

| File | Content |
|---|---|
| `project.json` | `name`, `brief`, `kind` (absent means `image`), `created`, `autonomy` (`step` or `auto`), `settings` (the fields of the last `generate`: `brief`, `refs`, `brand`, `shape`, `model`, `count`, `style`) |
| `v<N>.png` | version N, numbered from 1 in the order made |
| `v<N>.json` | `prompt` (the text sent to the model), `scene` (what the image shows, without style line and palette; a `change` copies it from its source), `refs` (absolute paths of the user's reference images and the brand logo, if used; the source version and the marked copy excluded; later versions made from this one keep them), `style` (style name), `brand` (name or null), `model`, `shape`, `action` (the request action that made it), `change` (`{"note", "marks"}` of a `change`, else null), `source` (N of the version it came from, else null), `created`, `invented` (`name`, `description`, `style_line`, `palette` of an invented style; absent otherwise; versions made from it keep it), `kind` (the request's `kind`) |
| `refs/` | reference images, written by the page |
| `marks/v<N>-marked-<k>.png` | a marked copy of version N, one per change request, written by the page |
| `marks/v<N>-mask-<k>.png` | the edit mask of that change request (same k): version N's pixel size, transparent inside the marks, written by the page |

- `created` is the request's `time` field (ISO 8601, set by the Studio server).
- `kind` in every `v<N>.json` is the request's `kind`; `project.json`'s `kind` is written by the Studio server and
  kept as found.
- `model` is the request's image-gen tier (`best`, `fast`, `multi-ref`); `shape` is `1:1`, `4:3`,
  `16:9` or `9:16`.
- Numbering: find the existing `v*.json` and `v*.png` with Glob in the project directory; the next N is one more than
  the highest N among them (1 when there is none). A request that makes several images reserves consecutive numbers
  before the first generation starts.
- `v<N>.json` is written only after `v<N>.png` exists, since the page shows a version as soon as its JSON appears. A
  generation that failed leaves no `v<N>.json`.
- `project.json` is read and rewritten whole; every field not being changed keeps its value. The page may change
  `autonomy` at any time, so `project.json` is read again right before it is written.

## Building a prompt

The prompt is built as `brand:style` defines it: the style line, the palette (the brand's colours when the request
names a brand, else the style's default palette), then the scene. For a version with `invented`, the style line and
default palette are its `style_line` and `palette`. Load `brand:style` for a style's style line,
default palette and tags, and `brand:brand` for a brand's colours, its allowed `styles` and its logo files.

The scene is the request's `brief` turned into a description of subject and composition, stating whether the image
may contain text and quoting any text it must contain. For an infographic, the scene is written as
`media:infographic` says: the concept sentence, the dominant element and its parts with where each sits, every text
string in quotes with its place, and what to avoid. It is stored as `scene` in the sidecar, so a later request
rebuilds a prompt from `scene`, a style and a palette.

Every `'` in the prompt is replaced with `’` before it is passed to `media:image-gen`, which takes the prompt in
single quotes; the sidecar stores the prompt as sent.

The request's fields map to the generation task given to `media:image-gen` like this:

| Request field | Task for `media:image-gen` |
|---|---|
| `shape` | the aspect ratio, unchanged (`1:1`, `4:3`, `16:9`, `9:16`) |
| `model` | image-gen's tier of the same name (`best`, `fast`, `multi-ref`), which picks a model of image-gen's config; a legacy value maps as the Studio server maps it (`gpt-image-2` to `best`, `nano-banana-pro` to `multi-ref`, `nano-banana-2` to `fast`). Ask image-gen for that tier and for no model id; record the field in `v<N>.json` as given |
| `count` | that many separate generations of the same prompt, each with its own output path `v<N>.png` |
| `refs` | reference images, passed as given |
| `brand` | colours in the prompt; the logo is passed as a reference image only when the brief asks for it (a PNG `logo`, else `raster`); a brand with no PNG logo (for example `neutral`, or an SVG `logo` only) gets none, and the post says so |
| `style` | style line and palette in the prompt |

Each image is written straight to its absolute path `<project>/v<N>.png`, one path per image, so no file has to be
renamed afterwards. The format is PNG. Several images are several image-gen commands, one per image, all issued in
the same message as parallel tool calls; never one shell command with `&` and `wait`, which the pre-approved
wrapper rule does not cover.

## Actions

Every request is carried out exactly as given: the fields are the user's choices and are not second-guessed. Before
the first generation, read `project.json` for `autonomy`. Send a `note` at each step that takes time (styles chosen,
generation started, each image done).

### generate

Fields: `brief`, `refs`, `brand`, `shape`, `model`, `count`, `style`. The first `generate` of a new project comes
with a `project.json` the Studio server created (name from the brief, the autonomy chosen in the page, empty
`settings`); the project may already hold reference images in `refs/`.

1. Update `settings` in `project.json` to exactly these fields.
2. Choose the styles:
   - a style name: that style, `count` images in it;
   - `"auto"`: three styles that fit the brief, one image in each (`count` does not apply). A brand whose `styles`
     key lists three or more styles: pick three of them, in its order of preference. A brand listing fewer: use
     every listed style and fill up to three from the catalogue. Otherwise compare the catalogue's tags, media
     (`suits`) and descriptions with the brief and pick three that differ from each other. For an infographic,
     every style taken from the catalogue is one whose `suits` includes `infographic`. Note the three names and
     one line on why each fits.
   - `"invent"`: three styles made up for this image, one image in each (`count` does not apply). They are new:
     no catalogued style is loaded or used as a reference, and nothing is compared with the catalogue or with
     styles invented before. The three differ clearly from each other. Each has a `name` (a few words, kebab-case),
     a `description` (one line on the look), a `style_line` (one line, without colours) and a `palette` (one line).
     For an infographic, each suits an infographic: the picture and its text stay easy to read.
     The brand's colours replace `palette` in the prompt when the request names a brand. Invented styles are used
     for this request only and are not saved anywhere else.
3. Build one prompt per style and generate. Every image of the request shares `brand`, `shape`, `model` and `refs`.
4. Write each `v<N>.json` with `scene`, `refs` (the request's `refs`, plus the logo when one was passed),
   `action: "generate"`, `change: null`, `source: null`. For an invented style, `style` is its `name` and `invented`
   holds its six fields.

### change

Fields: `version` (N), `marks`, `note`, `marked` (abs path of `marks/v<N>-marked-<k>.png`), `mask` (abs path of
`marks/v<N>-mask-<k>.png`, transparent inside the marks; null when `marks` is empty).

1. Read `v<N>.json` of the version; the new version keeps its `scene`, `refs`, `style`, `invented` (when present),
   `brand`, `model` and `shape`.
2. Write the edit instruction. It lists each mark by number with its place in the image, as percentages of width and
   height, and its comment:
   - box: `x` to `x+w` across, `y` to `y+h` down;
   - point: at `x` across, `y` down;
   - loop: the area enclosed by `points`, given as its bounding box;

   then the general `note` (when not empty), then: "Change only the marked areas as described; keep everything else
   in the image exactly as it is: composition, style, colours, text and every unmarked element. The red marks and
   numbers in the second image only show where to change; do not draw them."
3. Generate with two reference images: `v<N>.png` first (the image to edit), then `marked`. Use the version's model
   and shape. When `mask` is not null, also give image-gen `mask` as the edit mask of the first reference image.
   When image-gen answers that the model takes no mask, generate again without it, from the two references alone.
4. Write the new `v<M>.json` with that instruction as `prompt`, the source's `scene` and `refs`,
   `action: "change"`, `change: {"note", "marks"}` as received, `source: N`.

### variations

Fields: `version` (N), `count`.

1. Read `v<N>.json`.
2. Build the prompt fresh from the version's style line (its `invented` `style_line` when present), the palette
   (its `brand`, else the style's default palette or `invented` `palette`) and its `scene`,
   never from its `prompt` (which for a `change` is an edit instruction), adding: "Same subject, content and style
   as the last reference image, in a new composition and framing."
3. Generate `count` images with the version's model and shape, its `refs` and then `v<N>.png` as reference images.
4. Write each sidecar with the prompt as sent, the version's `scene`, `refs`, `style` and `invented` (when
   present), `action: "variations"`,
   `change: null`, `source: N`.

### other-styles

Fields: `version` (N), `styles` (names, or empty).

1. Read `v<N>.json` for its `scene`, `refs`, `brand`, `model` and `shape`.
2. Styles: the names given, or, when empty, three styles other than the version's, chosen as in `generate` with
   `"auto"` (the brand's allowed styles when it lists some).
3. For each style, build a prompt from its style line, the palette (the version's brand, else the style's default
   palette) and the version's `scene`, adding: "Keep the content and composition of the last reference image and
   render it entirely in this style." Generate with the version's `refs` and then `v<N>.png` as reference images,
   and the version's model and shape.
4. Write each sidecar with the version's `scene` and `refs`, `action: "other-styles"`, `change: null`, `source: N`.

### message

Field: `text`; `project` may be null.

The text is a message typed in the page. Answer it with `post`. When it asks for work on the project (a new image, a
change, a question about a version), carry it out with the rules of the action it matches, inside `project`. When
`project` is null and the message asks for project work, post that a project has to be opened first.

## Answering

- Progress: `mcp__studio__note` with one short line.
- Result: `mcp__studio__post` with `text` (what was made: per image its version number and style, for `auto` styles
  the reason each was chosen, for `invent` each invented style's description) and `images` (the absolute paths of
  the new PNGs).
- Failure: when a generation fails, post the error text and which versions were not made; the versions that
  succeeded are kept and posted.
- Questions: the agent never asks in the terminal. When a request cannot be carried out as given (a version that does
  not exist, a style or brand that is not found, a reference file missing), it posts the question or the problem
  with `post` and ends the turn.

## Autonomy

`autonomy` in `project.json`:

For an infographic, in both modes, each new image is viewed (Read) and checked as `media:infographic` says, every
word and number on it against the prompt included.

- `step`: make what the request asked, post it (for an infographic, with every defect the check found), and end the
  turn.
- `auto`: after making what was asked, read `project.json` again (the page may have changed `autonomy` meanwhile);
  when it is still `auto`, view each new image (Read). An image that clearly fails the request (wrong
  subject, garbled or misspelt required text, red marks left in a changed image, the marked change not made) is
  generated once more from the same inputs as the failed one (for a `change`: the source `v<N>.png` and the same
  marked copy), as a new version with the same `action` and `source`; the post names the failed version and what was
  wrong. Nothing else is added: no further styles (with `style: "auto"` or `"invent"` exactly three
  images), variations or changes the request did not ask for.

## Slide decks

A request of kind `slide` acts on a deck. Load `media:pptx-author` with the Skill tool for every request that writes
the deck's content, designs a slide image or assembles the PowerPoint, and follow its bespoke design path (never its
template path): phases 1 and 2 for the content, phase 3 (image design) for each slide image, phase 4 for the
assembly and phase 5 for the consistency pass. Slide images are made with `media:image-gen` as phase 3 says, each in
16:9. Where media:pptx-author and this skill differ, the Studio files below and this skill's actions hold.

### Deck files

The deck directory is the request's `project`.

| File | Content |
|---|---|
| `project.json` | as for an image project, plus `assembly` (`images` or `native`, set by the page) and `chosen` (`{"<k>": N}`: the version of slide k that goes into the PowerPoint, set by the page; a slide not in it uses its newest version). `settings` holds the fields of the last `generate` with `slide` null |
| `slides.md` | the deck's content and speaker notes in media:pptx-author's `slides.md` dialect: one `## Slide <k>: <title>` section per slide, in deck order, with the on-slide text keys (`title:`, `body:`, `colN.head:`, ...) and `notes:`; no `layout:` key |
| `deck.json` | the slides in deck order as `[{"k": 1, "title": "..."}, ...]`, k from 1 without a gap, each `title` the title of its `slides.md` section; rewritten whenever `slides.md` changes the slides or a title. The page reads the slides from this file |
| `slide-<k>/` | slide k's image files, exactly those of an image project: `v<N>.png`, `v<N>.json` (with `kind: "slide"`), `marks/v<N>-marked-<j>.png`, `marks/v<N>-mask-<j>.png`; versions are numbered within the slide's directory |
| `refs/` | the deck's reference images, for every slide |
| `deck-<N>.pptx` | assembled deck N, numbered from 1, never overwritten |
| `deck-<N>.json` | written after `deck-<N>.pptx` is checked: `assembly`, `versions` (the request's `{"<k>": N}`), `created` (the request `time`) |
| `checklist.md`, `working.md` | media:pptx-author's checklist and working doc |
| `work/deck-<N>/` | media:pptx-author's working files of assembly N: `images.json`, `notes.json`, `renders/`, backups, and a native backport's crops and regenerated icons and logos |

media:pptx-author's own layout maps onto the deck like this:

| media:pptx-author | Studio deck |
|---|---|
| the deck folder `<name>/` | the deck directory |
| `<name>/slides.md` (the content and notes) | `<deck>/slides.md`, with `deck.json` next to it |
| the approved image of slide k, `<name>/images/slide<k>_v<N>.png` | `<deck>/slide-<k>/v<N>.png` with N the slide's chosen version (an `assemble` request's `versions`), read in place, never copied |
| `<name>/checklist.md`, `<name>/working.md` | `<deck>/checklist.md`, `<deck>/working.md` |
| the deliverable `<name>.pptx` next to the folder | `<deck>/deck-<N>.pptx` inside the deck, N decided before the build starts |
| `renders/`, `images.json`, `notes.json`, `backups/` and backport files | `<deck>/work/deck-<N>/` |

media:pptx-author's approval gates are answered by the page's requests, and the agent asks nothing more: a `generate`
approves the content it writes and the images it asks for; a slide's chosen version is its approved image; an
`assemble` request is the approval to build and its `assembly` is the user's choice of the images-only assembly
(`images`) or the native backport (`native`). The deck's design spec (media:pptx-author phase 1) is the request's style and
brand: colours, fonts and type sizes of the request's brand, else of the `neutral` brand, from `brand:brand`.

### Deck actions

`project.json`'s `chosen` is changed by the page at any time, so it is read again right before each write, like
`autonomy`.

**generate with `slide` null** (fields as for images, `shape` always `16:9`, `count` the number of slides or null):
makes the deck, or rewrites it from the brief when it has slides.

1. Update `settings` to the request's fields and set `chosen` to `{}`.
2. Write the content as media:pptx-author's phases 1 and 2 say, from the `brief` and the reference images only: audience,
   ask and narrative arc in `working.md`, then `slides.md` with every slide's on-slide text and speaker notes, then
   `deck.json`. The number of slides is `count`, or, when null, the number media:pptx-author's phase 1 judges right for
   the brief. A rewrite replaces `slides.md` and `deck.json`; the `slide-<k>/` directories and their versions stay.
3. Choose one style for the whole deck: a style name is that style; `"auto"` is one catalogue style whose `suits`
   includes `slide` that fits the brief (the brand's `styles` first, when it lists some); `"invent"` is one style
   invented as for images (`name`, `description`, `style_line`, `palette`), kept in each slide's `invented`.
4. Make one image per slide as media:pptx-author's phase 3 says, each written to `<deck>/slide-<k>/v<N>.png` (the next N
   in that slide's directory), all slides in parallel as for images, then each `v<N>.json` with `scene` (what the
   slide shows: its layout and every text string on it), `action: "generate"` and the other fields as for images.
5. Post the slides made, each with its number, title and version.

**generate with `slide` k** (`count` images of slide k; `brief` may be empty; `style` is `"auto"`):

1. With an empty `brief`, slide k keeps its content. Otherwise the `brief` says what to change in the slide's
   content, or, for k one past the last slide, what the new slide shows: update its section of `slides.md` (append
   a section for a new slide) and `deck.json`.
2. The style is the deck's current style, whatever `style` says (the page sends `"auto"`): the `style`, and
   `invented` when present, of the `v<N>.json` of the other slides' chosen versions (for a deck's only slide, its
   own chosen version; for a deck with no image yet, a style chosen as for `"auto"` on the whole deck).
3. Make `count` images of slide k as in step 4 above, and remove `"<k>"` from `chosen`, so the new version is used.

**change, variations, other-styles** with `slide` k: as for images, inside `<deck>/slide-<k>/`: `version`, `marked`
and `mask` are files of that directory, and the new versions are written there. A change that alters the words on the
slide also updates its section of `slides.md` (and its title in `deck.json`), so the speaker notes and a native
backport match the image. `chosen` is not changed.

**assemble** (`assembly`: `images` or `native`; `versions`: `{"<k>": N}`, each slide's chosen version, filled in by
the Studio server):

1. N is one more than the highest `deck-<N>` among the deck's `.pptx` and `.json` files (1 when there is none); the
   deliverable is `<deck>/deck-<N>.pptx` and the working files go in `<deck>/work/deck-<N>/`.
2. Follow media:pptx-author's phase 4 with the image of slide k at `<deck>/slide-<k>/v<versions[k]>.png` and the speaker
   notes from `slides.md`: `images` is the images-only assembly; `native` is the native backport of every slide,
   then the deck assembled with its notes. Then its checks from the deliverable, and the phase 5 consistency pass;
   a finding that needs a new slide image is reported in the post and not fixed, since a new image needs the user's
   choice of version.
3. Write `deck-<N>.json` with `assembly`, `versions` and `created`.
4. Post the deck's path, its assembly, the version used per slide and every finding of the checks, with the rendered
   slides of the deliverable as `images`.

`message` on a deck is answered as for images, with these actions' rules for work on the deck; its `slide`, when present, is the slide the message is about. In `auto` autonomy
the check of each new image applies to each new slide image too, every word on it against `slides.md`.

## Rules

- Writes go only inside the request's `project` directory; reference images, brand files and style samples are read
  in place.
- `v<N>.png` is never overwritten; every result is a new version.
- The skills loaded here are given a task in prose: what to make, the inputs and the output path.
