# 3. Image design

Generate each slide **whole, as one image**, via the `media:image-gen` skill. This settles the
visual design and catches wording problems fast: an image-gen iteration takes minutes, a
native pptx iteration takes much longer. The image is a design reference, not
the deliverable. It never ships as-is.

## Process

1. Build the prompt from the [design library](design-library/README.md): take the base
   frame ([`infographic.md`](design-library/infographic.md))'s skeleton, the phase-1
   **style** ([`style-minimal.md`](design-library/style-minimal.md) /
   [`style-editorial.md`](design-library/style-editorial.md) /
   [`style-colorblock.md`](design-library/style-colorblock.md)) header, subtitle, closing
   and negative lines, and one **layout** (A to E inline in the frame, or F to I in
   `layout-*.md`). The first line of the prompt is the style line of the style's
   catalogue style from `brand:style` (for example the `minimal-enterprise` style), then
   the palette: the `accent1`, `accent2`, `accent3`, `dk1` and `lt1` hex values of the
   deck's brand from `brand:brand`, of the `neutral` brand when the deck has none. The style's `.png` guide is the target look.
2. Prompt `media:image-gen` with: that prompt, the slide's approved content (phase 2), the
   shared design spec locked in phase 1 (colors by hex, type hierarchy, logo treatment),
   and a reference image (`--ref`) to anchor the visual family (the design-library `.png`
   guide, or the prior slide once one exists).

   Ask `media:image-gen` (loaded with the Skill tool, see "What this is" in `SKILL.md`)
   for one image from that prompt and the reference image, aspect 16:9, size 2K, written
   to the absolute path of `<name>/images/slide1_v1.png`.

3. **Present the result and stop.** Wait for explicit approval, by name, before touching
   anything else. Don't pre-emptively move to the next slide or start backporting.
4. **If not approved**, regenerate with the specific feedback. Don't skip ahead on a
   partial approval: "the layout is right but the copy is wrong" still means regenerate,
   not patch around it in phase 4.
5. Once approved, tick that slide's image boxes in `checklist.md`, then move to
   [04-native-backport.md](04-native-backport.md) for *that slide only*. Keep the gate
   per slide, not per batch: approving three slides at once hides that slide 2's header is
   a different size from slide 1's.

## What to keep off every slide

Anything checkable but inflammatory belongs in the speaker notes (phase 2), never in a
generated image: a dismissive claim about a competing product, an overpromised timeline, or
anything that frames a decision-maker's call as a mistake. Once it's rendered
onto a slide it's quotable and hard to walk back; keep it to the talking track.

## Why the design starts as an image

A slide assembled directly from native pptx primitives (rects, ovals, lines, textboxes
placed by coordinate guessing) from a text spec, with no visual feedback loop, reads as
clip art: square corners, no shadow softness, icons reduced to crude
primitives.

Phase 3 therefore uses an image model, trained on real design, to get the *design* right
fast. Phase 4 then treats the approved image as ground truth to
measure from, rather than trying to invent placement from imagination a second time.

## Next: [04-native-backport.md](04-native-backport.md)
