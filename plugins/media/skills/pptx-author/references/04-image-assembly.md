# 4. Images-only assembly

Bespoke design path, alternative to the [native backport](04-native-backport.md). Each
approved slide image (phase 3) is placed full-slide on a blank slide, in deck order, with
the slide's speaker notes. The result is one `.pptx` that is fast to make and not
editable: every slide is one picture, and its text cannot be changed in PowerPoint.

## When

Only when the user has chosen images-only for this deck. That choice is the confirmation:
a request that states it (for example a Studio request asking for an images-only deck)
needs no further question. Without it, the bespoke design path ends in the native
backport.

The choice is per deck. The same approved images can give both deliverables, an
images-only deck first and a native backport later; each has its own deliverable path.

## Inputs

- The approved images, one per slide, in `<name>/images/`. Every slide needs one; a slide
  without an approved image stops the assembly.
- The slide order and the speaker notes from phase 2: the `notes:` block of each slide in
  `slides.md`, or the notes-only text in the working doc when the deck has no `slides.md`.
- The deck size: 16:9 (13.333 x 7.5 in) unless the deck says 4:3 (10.0 x 7.5 in).

Check each image's pixel size (`identify -format "%wx%h\n" <image>`). An image whose
aspect ratio differs from the slide's by more than 2% would be visibly stretched; say so
and regenerate it at the deck's aspect rather than placing it.

## Build

All four steps are `docs:pptx` operations; its `SKILL.md` gives the commands and the
JSON formats.

1. `new-deck` with N slides at the deck's size, at `<deliverable>.pptx`.
2. Write `<name>/images.json`: one `image` shape per slide, keyed `slide-0` to
   `slide-(N-1)` in `slides.md` order, each at `left` 0, `top` 0 and the slide's full
   `width` and `height`, with `path` the absolute path of that slide's image. Give both
   `width` and `height` so the picture covers the slide exactly.

   ```json
   {"slide-0": [{"type": "image", "path": "/abs/path/<name>/images/slide1_v2.png",
                 "left": 0, "top": 0, "width": 13.333, "height": 7.5}],
    "slide-1": [{"type": "image", "path": "/abs/path/<name>/images/slide2_v1.png",
                 "left": 0, "top": 0, "width": 13.333, "height": 7.5}]}
   ```

3. `add-shapes` of `images.json` onto `<deliverable>.pptx`, in place, in one call.
4. `add-notes` of `<name>/notes.json` onto `<deliverable>.pptx`, in place: one plain-text
   string per `slide-N`, the notes of that slide, paragraphs split with `\n`.

## Check

From the file at the deliverable path:

1. `export-slides` into `<name>/renders/` at 150-200 DPI, and compare each render with
   its source image side by side at one height
   (`magick <image> <render> -resize x800 +append compare.png`). Each slide shows its own
   image, edge to edge, in the right order.
2. Read each slide's notes back (the `slide-N/notes` read of `docs:pptx`) and confirm
   every slide with notes in phase 2 has them.

Tick the phase 4 box in `checklist.md`. The [consistency pass](05-consistency-pass.md)
still applies; on this path a fix is a regenerated image, approved again, then the
assembly rerun.

## Next: [05-consistency-pass.md](05-consistency-pass.md)
