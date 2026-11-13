# Storyboard format

`storyboard.md` in the project root is the story of the film. The user
reviews and edits it in any text editor or in Obsidian, and may change it in
any way. `validate` checks the format below; parse errors give their line.
Author, voice, music and all other settings are in `settings.yaml`.

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
Brief: Start wide on the arm and syringe. Label the spike proteins when
named, then push in slowly on the dendritic cell on the right.

<a href="images/1_vaccine.png"><img src="images/1_vaccine.png" width="30%"></a>

| Narration | On screen |
|---|---|
| A vaccine teaches your immune system to recognise a virus before you ever meet it. | Wide shot, still. Title fades in at the top. |
| The injection delivers a harmless piece of the virus, its spike protein. | Highlight the syringe; label "spike protein" on "spike". |
| Nearby, a dendritic cell picks it up and carries it away. | Slow push-in; label "dendritic cell" on "dendritic". |

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

- Image scene: `Image:` (a file under `images/`) and `Brief:` (the
  animation idea), both required.
- Template scene: `Template:` and an optional `Image:` (see "Template
  scenes").
- Manim scene: `Engine: manim`, `Brief:` and an optional `Image:` (see
  "Manim scenes"). `Engine: html` is the same as no `Engine:` line.
- Clip scene: `Engine: clip`, an optional `Brief:` and an optional `Image:`
  (see "Clip scenes").

Below the keys and above the table, a scene with an image has a preview line:
`<a href="images/1_vaccine.png"><img src="images/1_vaccine.png" width="30%"></a>`
(width: `storyboard.preview_width`). Markdown `![](images/x.png)` also works,
at full size. `validate` warns when the preview is missing or shows another
file; commands ignore it otherwise.

Then the table: the header `| Narration | On screen |`, the line `|---|---|`,
and one row per sentence, spoken in row order. Every scene has a table
except a clip scene, which may have none. No blank line inside the
table, one table per scene, nothing after it in the section. Neither cell may
be empty; a literal `|` in a cell is written `\|`. On screen is what the
viewer sees while that sentence plays. Name the word an event lands on, in
quotes (`label "spike protein" on "spike"`), so the scene author can key it
with `W()`.

A field's value continues on the following lines up to a blank line. A line
that starts with a capitalised word and a colon (`Note: ...`) starts a new
field. Headings other than `#` and `##`, YAML front matter and text outside a
field are errors. Whitespace inside a value collapses to one space, so
reflowing the text changes nothing.

## Speakers

Every sentence is spoken in the `voice:` of the settings unless its scene
names a speaker. Speakers are defined in one header table, after
`Topic:`/`Source:` and before the first scene:

```markdown
| Speaker | Backend | Voice | Speed | Style |
|---|---|---|---|---|
| host | kokoro | bm_george | 1.0 | |
| guest | kokoro | af_heart | 1.1 | |
```

Speaker names are `[a-z0-9_]+` and unique. The other columns follow the rules
of `voice:`: a speed other than 1.0 needs a backend in `voice.speed_backends`,
a style a backend in `voice.style_backends`. An empty Voice is the backend's
default (`voice.names`; for `speech`, the default of the configured provider,
as voiceover records it in `timing.json`), an empty Speed 1.0, an empty Style
none.

A scene table may then start with a Speaker column:

```markdown
| Speaker | Narration | On screen |
|---|---|---|
| host | Welcome to the show. | Host on the left |
| guest | Thank you for having me. | Guest on the right |
| | Here is what they discussed. | Both fade out |
```

Each Speaker cell names a speaker of the header table; an empty cell is the
default voice. When the speaker changes inside a scene, `script` writes one
script per run of sentences with one speaker (`p1/script.txt`,
`p2/script.txt`, ...) and prints each named speaker's voice under its path;
`voice` joins the voiced parts with `voice.speaker_gap` seconds at each
change. Two speakers in one sentence and overlapping speech are not
possible.

## Template scenes

A scene with `Template: title`, `summary` or `end` starts from the suggested
page `assets/<name>.html`, which the scene author restyles to match the film.
It takes no `Brief:`; an `Image:` is used as the background. Its On screen
cells are the text shown, word for word, so keep them short. Position, row
limit, hold and whether the page shows the author are under `templates:` in
the settings; `validate` warns when a scene breaks the position or row
limit.

- `title`: row 1 is the title, further rows lines under it; the page adds
  the byline (`credit.byline`).
- `summary`: each row is one point.
- `end`: row 1 is the closing line (a decision, an ask, a next step), an
  optional row 2 a line under it; the page adds the credit line
  (`credit.text`) after the last sentence.

Each row appears with its sentence (`references/scenes.md`).

## Manim scenes

`Engine: manim` makes the scene a Manim Community Edition `scene.py`
(`references/manim.md`). A template scene takes no `Engine:`.

```markdown
## growth

Engine: manim
Brief: Axes with time and cell count. Draw the exponential curve as it is
named, then mark the doubling time with a brace.

| Narration | On screen |
|---|---|
| A culture of bacteria doubles every twenty minutes. | Axes drawn; label "x2" on "doubles" |
| After five hours, one cell has become thirty thousand. | Curve drawn on "five"; brace "20 min" on "thirty" |
```

## Clip scenes

`Engine: clip` makes the scene a video made outside short-video and imported
with `clip --scene ID FILE`, such as a `media:video-effects` effect from one
image to another. `Brief:` says what the clip shows, for the critic and the
reader; `Image:` names the image it starts from or shows. A template scene
takes no `Engine:`.

Without a table the scene is silent and lasts its clip. This is the
transition between two image scenes, made from the previous scene's image to
the next scene's image:

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

## Suggested structure

`init` writes a conclusion-first film for a busy senior audience:

1. `title`: the main result as the title, and what the film covers.
2. `summary`: the two to four points to take away.
3. The image scenes, the evidence: one per PNG given to `init`, or per image
   made for the story.
4. `end`: the one thing to do or remember.

A teaching film for a general audience may instead open with the question and
put the `summary`, as a recap, just before `end`; a short film may drop the
summary or the end scene. `validate` only warns about the structure.

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
  without a table, and warns outside `length:` in the settings. The real
  length is known after `voice` and `clip`.

## What an edit needs

Compare each scene with its latest `voice/<scene>/v<N>/script.txt`,
`voice/<scene>/v<N>/meta.json` (`speakers`: each sentence's speaker and voice)
and `scenes/<scene>/v<N>/brief.md`.

- Narration, a Speaker cell, a speaker's row or `voice:` changed: `script
  --scene ID`, voice it with `media:voiceover`, `voice --scene ID`, then
  `scaffold`, update the page and `render`.
- `Brief:`, `Image:` or an On screen cell changed: `scaffold`, update the
  page, `render`; the voice is kept.
- `Engine:` changed: `scaffold` starts from the other engine's starting
  page; write the page and `render`. Changed to `clip`: make the clip and
  run `clip`.
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
- `manim:` starting-page keys changed: they apply only to a new `scene.py`.
- A preview line or whitespace only: nothing.
