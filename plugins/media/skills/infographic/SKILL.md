---
name: infographic
description: "Designs infographics: one beautiful image that explains one concept clearly, made with media:image-gen in a style suited to infographics. TRIGGER when: user asks for an infographic, or a picture or figure explaining a concept, process or result."
allowed-tools: Read Write Skill
compatibility: "Images are made with media:image-gen."
metadata:
  version: "0.2.0"
---

# Infographic

An infographic is one image that explains one concept clearly to a reader who
has not read the sources, and that is beautiful enough for people to stop and
look at it. It is made with `media:image-gen`, in a style suited to
infographics, from a prompt this skill helps write. An image that is hard to
understand or unattractive is ignored, whatever its accuracy, so these two
qualities are judged first at every check and review.

Boxes joined by arrows are the opposite of an infographic. A row of labelled
boxes with arrows between them, or a grid of cards each holding a bullet list,
is a boring slide. An infographic shows the thing itself: the place, the
object, the mechanism, the journey, the quantity, drawn so that the picture
carries the explanation and the words only name its parts.

The guidance below consists of defaults. A medium, a brand or the user's request
can override any of them; when a default makes a particular image worse, depart
from it and say why.

## The one concept

Write the concept as one sentence before anything else, in the reader's words
("A vaccine trains the immune system with a harmless copy of the virus").
It usually becomes the subtitle. Everything on the image supports that sentence;
content that does not is left out, however true. Sources that hold several
concepts make several infographics, and the user chooses which to make first.
When the sources leave the concept ambiguous, ask before generating.

## What the image shows

Choose the picture that makes the concept obvious, then the few words on it.

| The concept is | The image can show |
|---|---|
| How something works | The object or mechanism itself, in a cutaway or exploded view, with its parts named where they are |
| A process or a flow | A journey through real places (a sample travelling from a clinic to a lab to a screen), a landscape the reader follows from one end to the other, numbered stops along a path |
| Change over time | A path, road or river with the events as places along it; past drawn finished, planned drawn lighter or under construction |
| A comparison | One scene split into two matched halves, drawn the same way so the differences stand out; each side gets the same level of detail, and the order is neutral unless the subtitle says the image argues for one |
| A quantity or result | One large number with its unit and what it compares to, or a drawn proportion (a crowd with one figure in ten highlighted) |
| A structure or system | A building, a city, a machine or a map in which each part is a recognisable place |

- One dominant element the eye meets first, a few secondary ones, then detail
  for readers who look longer. One entry point and a reading order that follows
  the story, usually left to right or top to bottom.
- Concrete pictures are understood faster than abstract symbols: a doctor, a
  hospital, a sequencer, a form with its fields. A metaphor (a moon for
  "nightly") carries a word next to it.
- Even density, generous whitespace, a restrained palette. Past about seven
  elements the image usually reads better as two infographics.
- Each colour has one meaning, and a colour that carries meaning is paired with
  a label or shape, so the image still reads in greyscale and for colour-blind
  readers.
- Quantities drawn by the image model are approximate. A number that matters is
  written as text, and a drawn proportion that the reader will count (one in
  ten) is checked by counting. A headline number carries its n, date and
  source.
- A trend, a distribution or a comparison of many measured values needs a chart
  drawn from the data, which an image model cannot draw to scale. Show one or a
  few numbers as text instead, or tell the user that the concept needs a chart.

## Facts and text

- Every statement, name and number on the image comes from a source the user
  gave or pointed to. Keep a list of each fact and the file it came from, in the
  output directory's `notes.md`.
- Do not invent facts, actors or numbers to fill a gap. An unknown is left out
  or written as "not recorded"; keep the source's status words ("not granted" is
  not "denied", planned is not done).
- A path, journey or connection drawn between two parts claims that something
  moves between them. Draw only movements a source describes, and draw planned
  or partial ones as such.
- Do not generalise a fact that holds for one case, and do not show an example
  or a test case as if it were part of the design.
- A mechanism that is hypothesised or partly known is labelled as such, in the
  source's words; a simplification a domain reader could take as a claim (one
  pathway drawn where several exist) is noted in the footer or in `notes.md`.
- Name roles rather than people, unless the user asks for names. Each system has
  one name and appears once.
- Abbreviations are expanded at first use or in a footer glossary line.
- Text is short: a title, a one-line subtitle, labels of one to four words, at
  most a short line per part. Every string goes into the prompt verbatim, in
  quotes, so the model writes exactly it. Image models can misspell or alter
  text, names and numbers most often, so every word on the result is checked
  against the prompt.
- Sources and credits go in a short footer line when the user wants them on the
  image; otherwise they stay in `notes.md`.

## Style and brand

- Load `brand:style` and ask for the styles suited to infographics, or a style
  by name. To offer a choice, generate the same image in three or more styles.
- When the image follows a brand, load `brand:brand` and ask for the brand's
  folder; take the colours from its `brand.yaml` and the rules from its
  `guidelines.md`. The palette is then the brand's `accent1`, `accent2`,
  `accent3`, `dk1` and `lt1`, else the style's default palette.

## The prompt

In this order: the style's style line; the palette as hex codes with each
colour's role; the image's shape and medium (a 16:9 slide, a 4:5 post); the
scene, describing the dominant element, its parts and where each sits; every
text string in quotes with its place ("title at the top: '...'"); what to
avoid ("no boxes joined by arrows, no bullet lists, no text other than the
quoted strings"). When a style line forbids text, that clause is dropped; the
quoted strings are the only text. Load `media:image-gen` and ask for the image
with that prompt, the aspect, size 2K (4K for print) and the absolute output
path of the version, with image-gen's tier `best` (the `image_best` model of
its config), for text in the image. A gpt-image model renders text best; the Nano Banana and local models render it
less reliably, so tell the user when the text needs checking. Reference images (an earlier
version, a product photo, a brand illustration) are passed with it. For a set
of infographics, the first approved image is passed as a reference for each
later one, with the same style line and palette.

## Workflow

1. Read the sources; write the one-sentence concept and the fact list.
2. Choose what the image shows and write it out in words: the dominant
   element, its parts, the reading order, the text strings.
3. Choose the style and, when there is one, the brand.
4. Write the prompt and generate.
5. Look at the result whole, at the size it will be shown: whether the concept
   is clear within a few seconds and whether it is beautiful. Then check every
   word and number against the prompt, and every drawn proportion. Fix with a
   new prompt or an edit of the image through `media:image-gen` until no defect
   is left. A mask (gpt-image-2 and the local models) confines an edit
   mostly to a region; the model may still change the rest slightly, so every
   word is checked again after an edit.
6. Review as described in `references/review.md`.
7. Give the user the path of the final version. When the infographic goes into
   a document, it is embedded with alt text that states the concept and what the
   image shows.

## Outputs

The infographic lives in a directory of the user's choice, else
the absolute path of `figures/<name>/` under the current directory: `<name>_v01.png`, `<name>_v02.png`,
... for every version the user sees, never overwritten, and `notes.md` with the
concept, the fact list with sources, and each version's prompt, style and
model. When another skill loads this one for what the image shows and how it
explains, that skill's output paths and project files hold instead.
