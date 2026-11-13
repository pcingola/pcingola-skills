---
name: style
description: "Lists visual styles, each with a colour-free style line, a default palette, tags and a sample image. TRIGGER when: choosing, listing or comparing a visual, art or illustration style or look for slides, infographics, video scenes or icons."
allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/style.sh:*) Read Skill
---

# Style

A style is how an image looks, independent of the medium (slide, infographic,
video scene, icon, poster). Each style is one file `references/<name>.md` and
one sample image `assets/<name>.png`: an existing image made in that style, of
any scene (for a style harvested from a deck, one of the deck's images). A
style with no such image has a sample generated from its style line, its
default palette and a scene without text that suits the style.
A style may have no sample image yet.
Colour is not part of a style: a style file has a `Style line` without colours
and a `Default palette` line.

## Style file

YAML front matter, then sections:

| Part | Content |
| --- | --- |
| `name` | the style name, equal to the file stem |
| `title` | optional: the display name, for example `Wowbagger: Dark card` |
| `description` | one line on the look |
| `tags` | values from the technique, mood, colour and detail groups below |
| `suits` | media the style suits, from the `suits` group below |
| `links` | optional: label to URL of the original work the style comes from, for more information |
| `## Style line` | the style text, one line, put verbatim at the start of an image prompt |
| `## Default palette` | the colours used when there is no brand, one line |
| `## Result` | what generated images look like |
| `## Avoid` | content or treatments that did not work in this style |
| `## Suits` | the kind of content the style suits and why, as generic advice |

`## Result`, `## Avoid` and `## Suits` say `No record.` when no
source records anything for them. `## Suits` names no project, deck,
film or audience the style was made for.

## Choosing a style

1. A brand whose `brand.yaml` (from `brand:brand`) has a `styles` key allows
   only the styles listed there, in order of preference. Without the key every
   style is allowed.
2. `references/index.md` has one line per style: name, tags, suits and
   description. Search it by tag and medium, for example
   `grep 'slide' ${CLAUDE_SKILL_DIR}/references/index.md` or
   `grep 'calm.*muted' ${CLAUDE_SKILL_DIR}/references/index.md`.
3. Read the style files of the candidates and their sample images
   (`${CLAUDE_SKILL_DIR}/assets/<name>.png`, when it exists) to compare the looks.
4. When the user has not named a style, offer several. The caller renders the
   same content in each offered style and shows the results together, so the
   user compares the styles on their own content.

## Building the prompt

The image prompt is three parts in this order:

1. The style line, verbatim, without its trailing period.
2. The palette. With a brand: the brand's colours from `brand:brand`
   (`brand.yaml` `colors`), the keys `accent1`, `accent2`, `accent3`, `dk1`
   and `lt1`, written for example as
   `palette of #1B1B4B, #8064A2 and #6AD0DC, dark tone #33333B, light tone #FFFFFF`.
   Without a brand: the style's default palette, verbatim.
3. The caller's scene description: subject, composition, and whether the image
   may contain text.

Example: `<style line>. <palette>. <scene description>`.

## Index

`references/index.md` and `references/catalogue.json` are generated from the
front matter of the style files. `catalogue.json` is a JSON array, sorted by
name, of `name`, `description`, `tags`, `suits`, `sample` (the sample
image's path relative to the skill directory, or `null` for a style without
a sample image) and, when the style file has them, `title` and `links`.
After adding, renaming or removing a style, or changing a `name`, `title`,
`description`, `tags`, `suits` or `links`, regenerate both:

```bash
${CLAUDE_SKILL_DIR}/scripts/style.sh index
```

## Tags

Every value in a style's `tags` and `suits` comes from this list. A style
that needs another value adds it here.

- technique: vector, 3d, clay, paper, watercolour, ink, print, collage, photographic, isometric, blueprint, comic, painting, html, typographic, glow, glass
- mood: calm, playful, serious, technical, warm, satirical
- colour: monochrome, pastel, muted, saturated, dark, natural
- detail: minimal, moderate, dense
- suits: slide, infographic, video-scene, icon, poster
