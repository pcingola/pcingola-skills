# style

`brand:style` is a catalogue of visual styles for generated images. A style is one file `references/<name>.md` and one
sample image `assets/<name>.png`; the file format, the tag vocabulary and the prompt composition are in the skill's
`SKILL.md`.

## Style and colour

A style file has a `Style line` without colours and a separate `Default palette` line, used only when there is no
brand. Colour comes from the brand, so one style serves every brand and a brand's images keep its colours whatever
style is chosen. A brand can restrict and order the styles it allows with the `styles` key of its `brand.yaml`.

## Index and checks

`references/index.md` holds one line per style (name, tags, suits, description) and is generated from the front matter
of the style files by `style.sh index`, so callers search the catalogue without reading every style file. The same
command writes `references/catalogue.json` from the same front matter: a JSON array sorted by name, one object per style
with `name`, `description`, `tags`, `suits` and `sample` (`assets/<name>.png`, relative to the skill directory, or `null`
when the style has no sample image yet), plus
the optional `title` (display name) and `links` (label to URL of the original work) when the style file has them, for
programs that read the catalogue such as Studio. Studio shows a placeholder for a style with a null sample. The style
unit tests check the index and the catalogue against a fresh render, that every PNG has a style file, and the style
files against the format and vocabulary in `SKILL.md`. The brand unit tests check that a bundled brand's `styles`, when set, is a non-empty list of unique names,
each with a style file.

## Samples

A style's sample is an existing image made in that style, of any scene, so samples differ in content as well as in
style. A style harvested from a deck or film takes one of its images: copied, converted to PNG and scaled so its long
edge is 768 pixels. From the repository root:

```bash
name=clay-miniature
dir=plugins/brand/skills/style
sips -s format png "/path/to/source-image.png" --out "$dir/assets/$name.png"
sips -Z 768 "$dir/assets/$name.png"
```

A style with no existing image gets one generated from its style line without the trailing period, its default
palette and a scene description, joined by `. `; the scene is any scene without text that suits the style:

```bash
name=clay-miniature
dir=plugins/brand/skills/style
file=$dir/references/$name.md
style=$(awk '/^## Style line$/{getline; getline; print; exit}' "$file")
palette=$(awk '/^## Default palette$/{getline; getline; print; exit}' "$file")
scene='<a scene that suits the style>. No text, letters, numbers or logos.'
plugins/media/skills/image-gen/scripts/image-gen.sh generate \
  --model azure:gpt-image-2 --aspect 4:3 --size 1K --quality medium \
  --prompt "${style%.}. ${palette}. ${scene}" \
  --out "$PWD/$dir/assets/$name.png"
sips -Z 768 "$PWD/$dir/assets/$name.png"
```

`sips` (macOS only) converts and scales the image. `azure` is the provider
of the model config that serves `gpt-image-2` in the example config (`setup:settings`); use the name of yours. The samples of the eleven styles the catalogue started with were generated with one shared scene
(a field research station in a meadow) and scaled to a long edge of 1024 pixels.

## Adding a style

A style is added as a file `references/<name>.md` in the format of `SKILL.md` and a sample `assets/<name>.png`. A tag
or `suits` value outside the `## Tags` section of `SKILL.md` fails the style tests until it is added there. The index
and `catalogue.json` are stale, and the style tests fail, until `style.sh index` is run.

The repository is public, so a style file holds no history of the work it came from. The `## Suits` section gives
generic advice on the content the style suits and why. It names no project, deck, film, employer or audience, and it
records no trial, choice or rejection. Subjects in every section are neutral (engineers, a city map, a bar chart), not
the subject of the source work. No test checks this.

## Renaming and removing a style

A style name also appears in the index and `catalogue.json`, in the `styles` key of any `brand.yaml`, and in other skills' `SKILL.md` and
`references/` files that name it as an example. The style file, its PNG and its `name` change together, else the style
tests fail. A rename or removal leaves the index and `catalogue.json` stale and fails the style tests until `style.sh index` is run; a
bundled brand still naming the old style fails the brand tests.

## Untested

- Style names are kebab-case; no test enforces it.
- A `brand.yaml` under `BRAND_PATH` naming a renamed or removed style.
- Mentions of a renamed or removed style in other skills' files.
