---
name: brand
description: "Finds, shows and copies brand folders: logos, colours, fonts, guidelines, PowerPoint templates. TRIGGER when: user names a brand or asks for a branded deck, document or video, a logo, brand colours, fonts or brand guidelines."
allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/brand.sh:*)
---

# Brand

A brand is a folder `<name>/` holding `brand.yaml`, the files it names, and
`guidelines.md` with the rules for each medium. The two tables below define
what a brand folder contains.

## brand.yaml

Every top-level key is optional; a brand has the keys that apply to it and no
others. Paths are relative to the brand folder.

| Key | Type | Meaning |
| --- | --- | --- |
| `logo` | path, SVG or PNG | the logo for pages and documents |
| `logos` | mapping: variant name to path, SVG or PNG | further logos; `guidelines.md` says where each is used |
| `raster` | path, PNG | the logo drawn over video |
| `raster_on_dark` | path, PNG, the aspect ratio of `raster` | the logo drawn over video where the background is dark; without it `raster` is used on every background |
| `caption` | mapping: `height`, `gap` (numbers) | logo beside a video caption: `height` is logo height over the caption's cap height, `gap` is the ink gap between text and logo over the caption font size |
| `colors` | mapping: name to `#RRGGBB` | theme colours |
| `fonts` | mapping: role to font family name | theme fonts |
| `pptx` | mapping: template name to `{pptx: path, json: path}` | PowerPoint templates; the `.json` describes every slide and placeholder of the `.pptx` |
| `styles` | list of style names | the styles of the `style` skill (brand plugin) the brand allows, in order of preference |

## Keys per medium

| Medium | Keys |
| --- | --- |
| Video caption (logo beside a credit text) | `raster`, `raster_on_dark`, `caption` |
| Video title and end pages | `logo` |
| Slides | the `pptx` entry of the template, e.g. `pptx.presentation.pptx` and `pptx.presentation.json` |
| Generated images | `styles`; the palette is `colors` `accent1`, `accent2`, `accent3`, `dk1` and `lt1` |

A file is located through its key, never by a fixed path inside the folder.
`colors` and `fonts` apply to every medium. Every bundled brand has the
`colors` keys `accent1`, `accent2`, `accent3`, `dk1` and `lt1`.

Run every command with `${CLAUDE_SKILL_DIR}/scripts/brand.sh <command> [args]`.

## Lookup

Brands are searched in the bundled `brands/` directory of this skill, then in
each directory of `BRAND_PATH` (colon-separated), in order. Empty entries and
directories that do not exist are skipped. The first folder `<name>/` with a
`brand.yaml` wins. `BRAND_PATH` is a setting.

Bundled brand: `neutral`, with no logo. It holds colours, fonts, layout rules
and a 16:9 PowerPoint template for a deck or figure without a brand. Add other
brands (for example `acme`) in a directory on `BRAND_PATH`.

## Commands

| Command | Output |
| --- | --- |
| `list` | every brand name and the folder it resolves to |
| `show <name>` | the resolved folder on the first line, then the text of its `brand.yaml` |
| `copy <name> <dest> [--force]` | copies the brand folder to `<dest>/<name>/` and prints that path; refuses an existing target unless `--force` |

Errors go to stderr with exit status 1 and name the directories searched.

## Use

1. `show <name>` to get the folder (first line) and its `brand.yaml`.
2. Read `<folder>/guidelines.md` before producing anything for that medium.
3. Use each file in place, at `<folder>/<path>` for the path under its key,
   read-only. Callers keep no copy of the folder.
4. `copy <name> <dir>` starts a new brand from an existing one: copy into a
   directory on `BRAND_PATH`, rename the folder (a bundled brand of the same
   name is found first) and edit its files.

Do not edit the files of a bundled brand.
