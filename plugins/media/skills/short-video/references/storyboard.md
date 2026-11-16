# Storyboard format

`storyboard.md` in the project root is the story of the film. The user
reviews and edits it in any text editor or in Obsidian, and may change it in
any way. `validate` checks the format below; parse errors give their line.
Author, voice, music and all other settings are in `settings.yaml`.

A project may keep `storyboard.json` instead (see "storyboard.json"); every
command reads whichever of the two files the project has, and refuses a
project with both.

## Example

```markdown
# How a vaccine trains the immune system

Topic: A one-minute explainer for a general audience: a vaccine delivers a
harmless piece of a virus, immune cells learn its shape, and memory cells let
the body respond fast to the real infection later.

Source: sources/notes.md

## title

Template: title

| Narration | On screen |
|---|---|
| A vaccine lets your body stop a virus in days instead of weeks. | Vaccines cut the immune response from weeks to days |
| Here is how one harmless protein trains the immune system. | From injection to immune memory |

## injection

Image: 1_vaccine.png
Brief: The camera travels across the picture with the story and never rests:
from the whole arm into the injection site, then along the path of the
protein to the dendritic cell. Drawn particles stream out of the needle and
drift through the tissue; labels ride with the camera.

<a href="images/1_vaccine.png"><img src="images/1_vaccine.png" width="30%"></a>

| Narration | On screen |
|---|---|
| A vaccine teaches your immune system to recognise a virus before you ever meet it. | The camera glides from the whole arm towards the needle; faint particles drift through the tissue. |
| The injection delivers a harmless piece of the virus, its spike protein. | Particles stream out of the needle tip on "delivers" and spread; the label "spike protein" rides in with them on "spike". |
| Nearby, a dendritic cell picks it up and carries it away. | The camera pans with the particles to the dendritic cell on "dendritic"; they flow into it, and a dotted path draws from the cell to the frame edge on "carries". |

## end

Template: end

| Narration | On screen |
|---|---|
| Check that your vaccinations are up to date. | Check your vaccinations |
```

Lines between `<!--` and `-->` are comments and are ignored.

## Header

- `# <title>`: the first line, exactly once.
- `Topic:` (required): one paragraph, what the film explains and to whom.
- `Source:` (optional): the source text, a path under `sources/`.
- The speakers table (optional, see "Speakers"). The header holds no other
  table.

## Scenes

One `## <scene id>` section per scene, in film order. The id is `[a-z0-9_]+`
and unique. It names the scene's directories, so keep it when reordering or
editing a scene; a new id starts again at version 1.

The keys of a scene:

- HTML scene: `Brief:` (how the scene moves: where the camera travels,
  what is drawn, what moves across the picture), required, and an optional
  `Image:` (a file under `images/`), the picture the scene moves over. A
  scene without `Image:` draws everything on screen in its page: a diagram,
  chart, map or text built with the speech on a plain or drawn background
  (`references/scenes.md`, "Scenes without a picture").
- Template scene: `Template:` and an optional `Image:` (see "Template
  scenes").
- Manim scene: `Engine: manim`, `Brief:` (what moves and transforms) and
  an optional `Image:` (see
  "Manim scenes"). `Engine: html` is the same as no `Engine:` line.
- Video scene: `Engine: video`, `Image:` (the picture a video model
  animates) and `Brief:` (the motion), both required, and an optional
  `Ambience: off` (see "Video scenes").
- Presenter scene: `Engine: presenter`, `Image:` (the portrait of the person
  who speaks), required, and an optional `Brief:` (see "Presenter scenes").
- Clip scene: `Engine: clip`, an optional `Brief:` and an optional `Image:`
  (see "Clip scenes").
- Silent HTML scene: an HTML scene with `Length: <seconds>` and no table
  (see "Silent HTML scenes").

An HTML scene's `Brief:` is a shot list precise enough to build the page
without guessing: the palette as hex colours, the fonts (font families
under the SIL Open Font License installed on this machine, which the page
embeds: `references/scenes.md`, Fonts), the light over time, camera keyframes (time, position or framing, target, easing), and
for each element where it sits and when it enters, moves and leaves, keyed
to sentences or words. The agent writes this detail from the user's short
request; the user need not give it. Inside a Brief, a line that starts with
a capitalised word and a colon starts a new field and fails as an unknown
key: write such labels in lowercase (`palette: #0f1420 ...`) or inside a
sentence (`The palette is ...`). A key matches in any case after its capital first
letter (`ENGINE:`, `Show Author:`); `Show author:` is the only key of two words.

Any HTML scene without `Template:` and without `Image:` may have
`World: <name>`, which joins it to the consecutive scenes with the same name
in one page (see "Shared worlds").

Any scene may have `Show author: false` or `Show author: true` (case
insensitive; any other value, an empty one included, is an error). With
`false` the film's creator caption ("Created by <author>",
`references/post-production.md`) is not drawn over the scene. Without the
key a scene follows its template's `show_author` rule (`false` for `title`
and `end`), and a scene without a template is captioned. Set `false` on a
scene whose picture already shows the author's name, for example a title or
closing slide taken from the user's deck.

Below the keys and above the table, a scene with an image has a preview line:
`<a href="images/1_vaccine.png"><img src="images/1_vaccine.png" width="30%"></a>`
(width: `storyboard.preview_width`). Markdown `![](images/x.png)` also works,
at full size. `validate` warns when the preview is missing or shows another
file; commands ignore it otherwise.

Then the table: the header `| Narration | On screen |`, the line `|---|---|`,
and one row per sentence, spoken in row order. Every scene has a table
except a clip scene, which may have none, and a silent HTML scene, which has
none. No blank line inside the
table, one table per scene, nothing after it in the section. Neither cell may
be empty; a literal `|` in a cell is written `\|`. On screen says what
moves or changes on screen while that sentence plays, as actions: the camera
travels to a part of the picture, a curve grows, an arrow draws, particles
flow, a number counts. A cell that only names a picture or a label describes
a slide; every cell has movement. Name the word an event lands on, in quotes
(`the label "spike protein" rides in on "spike"`), so the scene author can
key it with `W()`. A template scene's cells are its text (see "Template
scenes"), and its page gives each one its own movement, so every cell has
movement there too.

A field's value continues on the following lines up to a blank line. A line
that starts with a capitalised word and a colon (`Note: ...`) starts a new
field. A heading is `# ` or `## ` with the space; a line such as `#0f1420`
is text. Headings other than `#` and `##`, YAML front matter and text outside a
field are errors. Whitespace inside a value collapses to one space, so
reflowing the text changes nothing.

## Speakers

Every sentence is spoken in the `voice:` of the settings unless its scene
names a speaker. Speakers are defined in one header table, after
`Topic:`/`Source:` and before the first scene:

```markdown
| Speaker | Model | Voice | Speed | Style |
|---|---|---|---|---|
| host | | bm_george | 1.0 | |
| guest | | af_heart | 1.1 | |
```

Speaker names are `[a-z0-9_]+` and unique. Model is a speech model id
`<provider>:<model>` of `config.yaml`; an empty Model is its `speech` model.
A speed other than 1.0 needs a model with a speed setting, a style a model
that takes one; the voiceover skill refuses others when it voices. An empty
Voice is the model's default voice, as voiceover records it in
`timing.json`, an empty Speed 1.0, an empty Style none.

A scene table may then start with a Speaker column:

```markdown
| Speaker | Narration | On screen |
|---|---|---|
| host | Welcome to the show. | The camera pans left onto the host as "show" is said |
| guest | Thank you for having me. | The camera swings right to the guest on "Thank" |
| | Here is what they discussed. | The camera pulls back to show both; the topics draw in between them on "discussed" |
```

Each Speaker cell names a speaker of the header table; an empty cell is the
default voice. When the speaker changes inside a scene, `script` writes one
script per run of sentences with one speaker (`p1/script.txt`,
`p2/script.txt`, ...) and prints each part's voice under its path;
`voice` joins the voiced parts with `voice.speaker_gap` seconds at each
change. Two speakers in one sentence and overlapping speech are not
possible.

## Voice settings per sentence

After On screen, a scene table may have any of the columns Model, Voice,
Speed and Style, in any order:

```markdown
| Speaker | Narration | On screen | Speed | Style |
|---|---|---|---|---|
| host | Welcome to the show. | The camera pans left onto the host on "show" | | |
| host | And now, the result. | The result counts up to its value on "result" | 0.9 | |
```

A set cell overrides that field of the sentence's voice: its speaker's, or
`voice:` when it has no speaker. An empty cell keeps it. A Model other
than the speaker's, without a Voice, uses that model's default voice. The
resolved voice follows the rules of `voice:`. `script`
writes one part per run of consecutive sentences with the same speaker and
resolved voice, so a change of settings starts a new part, and prints each
part's voice when it is not `voice:`; `voice` checks every recording against
its sentences' resolved voice.

## storyboard.json

`storyboard.json` holds the same storyboard as one JSON object, the structure
`storyboard` prints for either file:

```json
{
  "title": "Interview",
  "topic": "Two people talk.",
  "source": "sources/notes.md",
  "speakers": {"host": {"model": null, "name": "bm_george", "speed": null, "style": null}},
  "scenes": [
    {"id": "title", "template": "title", "narration": ["Welcome."], "beats": ["Interview"]},
    {"id": "talk", "image": "a.png", "brief": "The camera swings between the two faces.",
     "narration": ["Hello.", "Hi."], "beats": ["The camera pushes in on the host on \"Hello\"", "The camera swings to the guest on \"Hi\""],
     "speakers": ["host", null], "voices": [null, {"speed": 1.2}]}
  ]
}
```

- Top level: `title`, `topic`, optional `source` and `speakers` (name to
  `model`, `name`, `speed`, `style`, each optional or null), and `scenes`.
- A scene: `id`; `template`, `image`, `brief`, `engine` as the `Template:`,
  `Image:`, `Brief:`, `Engine:` keys, under the same rules; `narration` and
  `beats` (the On screen cells), lists of one string per sentence (a clip
  scene may leave both out, which makes it silent, and a scene with `length`
  leaves both out); `length` (a number of seconds) and `world` (a name) as
  the `Length:` and `World:` keys; `show_author` (true or false; null is an
  error, leave the key out instead) as the `Show author:` key; optional
  `speakers` (a speaker name or null per sentence), `voices` (null or an
  object with any of `model`, `name`, `speed`, `style` per sentence) and
  `preview` (the image preview path of a storyboard.md; unused otherwise).
- No other keys. The author is not stored: it comes from `author:` in the
  settings. Whitespace inside a string collapses to one space.

`validate` names the scene and field of each problem, and gives no image
preview warning. `init --json` writes a starting `storyboard.json`.

## Template scenes

A scene with `Template: title`, `summary` or `end` starts from the suggested
page `assets/<name>.html`, which the scene author restyles to match the film.
It takes no `Brief:`; an `Image:` is used as the background. Its On screen
cells are the text shown, word for word, so keep them short. Position, row
limit, hold and whether the creator caption is drawn over the scene
(`show_author`; a scene's own `Show author:` overrides it) are under
`templates:` in the settings; `validate` warns when a scene breaks the position or row
limit.

- `title`: row 1 is the title, further rows lines under it; the page adds
  the byline (`credit.byline`).
- `summary`: each row is one point, arriving with an element drawn in the
  page and tied to it (a shape, icon, counter or chart mark;
  `references/scenes.md`).
- `end`: row 1 is the closing line (a decision, an ask, a next step), an
  optional row 2 a line under it; the page adds the credit line
  (`credit.text`) after the last sentence.

Each row appears with its sentence, and each sentence, and a hold after the
narration, gets its own movement with a new target (`references/scenes.md`).

## Manim scenes

`Engine: manim` makes the scene a Manim Community Edition `scene.py`
(`references/manim.md`). A template scene takes no `Engine:`.

```markdown
## growth

Engine: manim
Brief: Cells divide on screen, again and again, then shrink into the first
point of a growth curve that climbs while a counter runs up with the
narration.

| Narration | On screen |
|---|---|
| A culture of bacteria doubles every twenty minutes. | One cell splits in two on "doubles", then each of those splits, the cells pushing apart |
| After five hours, one cell has become thirty thousand. | The cells shrink onto axes that draw in; the curve grows from "five" and the counter runs to 30,000 on "thirty" |
```

## Video scenes

`Engine: video` makes the scene the scene's image animated by a video model
from a motion prompt (`references/video-model.md`). `Image:` is the first
frame, made with `media:image-gen`; `Brief:` is the motion and the first
`prompt.txt`. The model sees no word times, so the On screen cells describe
what moves during each sentence without keying an event to a word. A
template scene takes no `Engine:`.

```markdown
## culture

Engine: video
Image: 3_culture.png
Brief: The bacteria in the dish drift and divide slowly; the camera pushes
in on the cluster at the centre.

| Narration | On screen |
|---|---|
| In a warm dish, the bacteria never stop moving. | The cells drift across the dish while the camera pushes in on the central cluster |
```

The scene is narrated like any other. `render` asks the model for the
narration's length; a shorter clip holds its last frame until the narration
ends, a longer one is cut there.

A model that generates a sound track with the clip gives the scene that
track as ambience under the narration (`references/video-model.md`,
"Ambience"). `Ambience: off` above the table keeps it out; `Ambience: on`
is the default. Only a video scene takes `Ambience:`. In `storyboard.json`
the key is `"ambience": false` (or `true`).

## Presenter scenes

`Engine: presenter` makes the scene the person in the scene's image speaking
the scene's narration recording, made by a presenter model
(`references/video-model.md`, "Presenter scenes"). `Image:` is a portrait,
made with `media:image-gen`; `Brief:` is optional and, when given, replaces
the model's own prompt. In `storyboard.json` the scene has `"engine":
"presenter"` and `image`, and `brief` only when given. A template scene takes
no `Engine:`; a presenter scene takes no `Ambience:`.

```markdown
## host

Engine: presenter
Image: 1_host.png

| Narration | On screen |
|---|---|
| Welcome to the harbour at night. | The host speaks to the camera |
```

## Clip scenes

`Engine: clip` makes the scene a video made outside short-video and imported
with `clip --scene ID FILE`, such as a `media:video-effects` effect from one
image to another. `Brief:` says what the clip shows, for the critic and the
reader; `Image:` names the image it starts from or shows. A template scene
takes no `Engine:`.

Without a table the scene is silent and lasts its clip. This is the
transition between two scenes with an image, made from the previous scene's
image to the next scene's image:

```markdown
## morph

Engine: clip
Brief: The pencil drawing of the lab turns into the photograph of it.
```

With a table the scene is narrated like any other: `script` and `voice` make
its voice version, and `clip` holds the clip's last frame until the
narration ends, or pads the narration with silence when the clip is longer.
`script` and `voice` skip clip scenes without a table. The clip's audio is
not used; `clip` warns when the file has an audio stream. The imported file
is kept in the version as `clip.<ext>`; `meta.json` records its source path,
sha256 and length, and `brief.md` the sentence and word times of a narrated
clip scene.

`validate` warns when a clip scene's latest version:

- has no imported clip;
- is not at the `video:` size and fps;
- belongs to a narrated scene that has no voice version yet;
- was imported without narration, but the scene now has a table;
- was muxed with an older voice version than the scene's latest one;
- was muxed with a voice, but the scene now has no table.

`validate`'s length estimate and `length` count a clip scene as the longer
of its narration and its imported clip; a clip scene without a table and
without an imported clip counts as `length.clip_seconds`.

## Silent HTML scenes

`Length: <seconds>` (a number above 0, `6` or `6s`) on an HTML scene without
a table makes it silent: it lasts that long, `script` and `voice` skip it, and
`render` gives it a silent sound track. Only an HTML scene without a template
takes `Length:`; a scene with a table lasts its narration and takes none. The
page keys its tweens to plain seconds; it has no sentences, so `S(1)` fails
the static check. In `storyboard.json` the key is `"length": 6`.

```markdown
## opening

Brief: Night over the harbour; the lights of the ships come on one by one.
Length: 6
```

A silent film (no narration at all) makes its title and end cards this
way, as plain HTML scenes with `Length:`, starting from
`assets/techniques/title/`: the `title`, `summary` and `end` templates need a
narration table.

## Shared worlds

`World: <name>` (`[a-z0-9_]+`) on consecutive HTML scenes puts them in one
world: one page, `worlds/<name>/v<N>/index.html`, that the HTML film plays
once across the scenes (and that `render`, for an MP4, renders once and cuts
into one clip per scene at the scene boundaries). The camera and the light then run
on from scene to scene without a cut. Each scene keeps its own narration,
`brief.md` entry, stills, review and comments (and, when rendered,
`scene.mp4`, frames and contact sheet), in scene time. A world scene may be narrated or silent (`Length:`).

```markdown
## harbour

Brief: The camera drifts over the harbour at dusk toward the cranes.
World: port

| Narration | On screen |
|---|---|
| Every container starts here. | the camera glides toward the cranes on "starts" |

## cranes

Brief: The camera rises along a crane as the light turns to night.
World: port
Length: 4
```

`validate` refuses a world whose scenes are not consecutive, and a world scene
with `Template:`, `Image:` or an engine other than html. It warns about a
world of one scene. In `storyboard.json` the key is `"world": "port"`.

## Suggested structure

`init` writes a conclusion-first film for a busy senior audience:

1. `title`: the main result as the title, and what the film covers.
2. The evidence: scenes each built on one movement that shows a point (a
   process running, a quantity growing, two things compared side by side as
   they change). `init` writes one draft image scene per PNG it is given.
   Images are material: one image may carry several shots or scenes. A
   scene that a picture would not help (a diagram, chart, process or text
   built with the speech) has no `Image:` and is drawn in its page, or is
   a manim scene for mathematics and plots. A picture whose own content
   moves (water, smoke, cells, a crowd) can be a video scene.
3. `end`: the one thing to do or remember.

A film may add a `summary` scene, as a recap just before `end`, whose points
each arrive with a drawn element tied to the point. A teaching film
for a general audience may open with the question; a short film may drop the
end scene. `validate` only warns about the structure.

## Writing the narration

- One sentence per row. Write for the ear: short sentences, numbers as they
  should be spoken (`1995` alone reads as a year), no abbreviations the voice
  would spell out. Narrate what is on screen.
- A word the voice misreads (a brand name, a domain) keeps its spelling in
  the storyboard; `pronounce:` in the settings gives its spoken form
  (`{"ACME-AI": "Acme A I"}`). `script` writes the spoken form into
  `script.txt`; `voice` accepts it and stores `timing.json` with the
  storyboard's text, the spoken words of each written word merged into one
  word, so `W(n, "ACME-AI")` finds it.
- `validate` estimates the length from the word count, plus the clip scenes
  without a table and the `Length:` of silent HTML scenes, and warns outside `length:` in the settings. The real
  length is known after `voice` and `clip`.

## Scene status

`status` prints, as JSON, `{"scenes": [...]}` with one object per scene in
film order:

- `id`: the scene id. `narrated`: false for a scene without a table (a
  clip scene, or a silent HTML scene).
- `voice_version`: the latest voice version (`v3`), or null.
- `needs_voice`: true when a narrated scene has no voice version, or the
  latest one does not match the storyboard: a sentence differs, or a
  sentence was voiced in another voice than its resolved voice (its
  speaker's, or `voice:`, with its own settings over it). `voice_reasons`:
  one line per mismatch.
- `scene_version`: the latest rendered scene version, or null.
- `needs_render`: for an HTML scene, judged on its latest page version
  (the version the HTML film plays), rendered or not: true when it has no
  page version, or that version differs from the storyboard as listed below
  (voice version, image, `brief.md`, `card.js`). A page with no render is not
  stale for lack of a render. For a world scene: true when the world has no
  version, or the world's scenes, voice versions, lengths, Briefs or On
  screen text changed since its latest world version; every scene of the
  world is then stale. For any other scene: true when it has no rendered version; a newer
  version is scaffolded and not rendered; the render used another engine,
  or another voice version than the latest; the image differs from the
  rendered `background.png`, or the render has a `background.png` and the
  scene no longer has an image; the rendered `brief.md` differs from what
  `scaffold` writes now (brief, On screen text, image name, frame size); or,
  for a template scene, `card.js` differs (On screen text, author). For a
  clip scene: any of the `validate` warnings under "Clip scenes".
  `render_reasons`: one line per cause.
- `rendered`: true when the scene's current version has a render: for an
  HTML scene its latest page version (a world scene: the latest world
  version) has a `scene.mp4`. Before `assemble`, `render` every scene whose
  `rendered` is false.

A scene that needs a voice needs a render only once the new voice version is
imported; the two are reported separately.

## What an edit needs

`status` reports the scenes that need a new voice or a new version. Compare each
scene with its latest `voice/<scene>/v<N>/script.txt`,
`voice/<scene>/v<N>/meta.json` (`speakers`: each sentence's speaker and voice)
and `scenes/<scene>/v<N>/brief.md`. Every scene made again gets the motion
check of `references/scenes.md` (`references/manim.md` for a manim scene,
`references/video-model.md` for a video scene). Below, `render` applies to an
HTML scene only when the film is made as an MP4; otherwise the HTML scene is
checked with `check` and `stills`. After the edits, run `html` again.

- Narration, a Speaker cell, a voice settings cell, a speaker's row or `voice:` changed: `script
  --scene ID`, voice it with `media:voiceover`, `voice --scene ID`, then
  `scaffold`, update the page and `render`.
- `Brief:`, `Image:` or an On screen cell changed: `scaffold`, update the
  page, `render`; the voice is kept.
- `Engine:` changed: `scaffold` starts from the other engine's starting
  page (a video scene: `prompt.txt` from `Brief:`); write the page and
  `render`. Changed to `clip`: make the clip and run `clip`.
- A clip scene: a new clip, a changed `Image:` it is made from, a changed
  `Brief:`, or a narration change after `voice`: make the clip again if it
  no longer fits and run `clip --scene ID FILE`. An image change in a scene
  next to a transition: make the transition clip again from the new image.
- `author:`, `credit.byline` or `credit.text` changed: `scaffold` and
  `render` the title and end scenes.
- `templates.<name>.hold_seconds` changed: `scaffold` and `render` the
  scenes of that template.
- `video:` changed: `scaffold` and `render` every scene; make every clip
  again at the new size and fps and run `clip`.
- `manim.background_color` changed: it applies only to a new `scene.py`.
- A scene that fails the motion check: `scaffold`, add movement to the page,
  `scene.py` or `prompt.txt` where it stands still, or change its method,
  and `render`;
  for a clip scene, make the clip again and run `clip`.
- A preview line or whitespace only: nothing.
