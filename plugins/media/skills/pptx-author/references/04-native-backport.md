# 4. Native backport

This is the phase that takes real time. The approved image (phase 3) becomes the exact
visual spec: every color, position, and font size gets measured off it, then rebuilt as
real, independently editable PowerPoint objects via the `docs:pptx` skill's `add-shapes`. No
full-bleed picture of the whole slide — text must stay text.

**Everything in this phase uses `magick` (ImageMagick) via Bash, or the `docs:pptx`/`media:image-gen`
skills. No hand-written Python.** Every operation below — grid overlay, cropping, color
sampling, background-run detection, icon-sheet splitting, background flattening, image
stacking — has a plain `magick` one-liner. Reach for a script only if you find a genuine
gap `magick` can't cover, and treat that as worth surfacing, not silently working around.

The `docs:pptx` operations below (`new-deck`, `add-shapes`, `add-notes`, `export-slides`,
`list-images`, `extract-images`) are tasks for the `docs:pptx` skill, and image generation
is a task for the `media:image-gen` skill, both loaded with the Skill tool (see "What this
is" in `SKILL.md`). Their `SKILL.md` files give the commands and the `add-shapes` JSON format.
The `jq` recipes for merging pptx JSON payloads are in this file ("Assembling the deck").

## Exception: icons and logos

Small multi-color icon glyphs and logos with no flat-fill vector equivalent (a company
logo, a product mark with a gradient) are the one thing allowed to stay raster. Even
so — **never crop them from the slide PNG.** See
[Icons and logos: never crop, always regenerate](#icons-and-logos-never-crop-always-regenerate)
below; this is the single most consequential rule in this phase.

## Setup: pixel-to-inch scale

The slide canvas is a known physical size (standard 16:9 = 13.333in × 7.5in). The
approved PNG has a known pixel size — check it, don't assume:

```bash
identify -format "%wx%h\n" source.png   # e.g. 1376x768, ~103dpi for a 13.333x7.5in canvas
```

Compute the scale factors (plain arithmetic, no tool needed):

```
sx = canvas_width_in / image_width_px   # e.g. 13.333 / 1376
sy = canvas_height_in / image_height_px # e.g. 7.5 / 768
```

Every measured pixel position gets multiplied by the matching scale factor to become
an `add-shapes` coordinate. Keep `sx` and `sy` separate — they're usually close but not
identical, and conflating them introduces a small compounding error across a slide with
many measured elements.

## Measuring the image

### Grid-overlay reads (fast, use this first)

For most positions, draw a labeled pixel grid onto a copy of the source image and read
coordinates off it visually — far faster than programmatic scanning, and it's how you
actually see what an element is, not just where its edges are.

```bash
# always read the actual image's own dimensions — never assume/hardcode a size
read W H < <(magick source.png -format "%w %h" info:)

STEP=40   # gridline spacing in px; use a finer step on a cropped sub-region
DRAW=""
for x in $(seq 0 $STEP $W); do DRAW="$DRAW line $x,0 $x,$H"; done
for y in $(seq 0 $STEP $H); do DRAW="$DRAW line 0,$y $W,$y"; done

ANNOTATE=()
for x in $(seq 0 $((STEP*2)) $W); do ANNOTATE+=(-fill red -pointsize 10 -annotate "+${x}+10" "$x"); done
for y in $(seq 0 $((STEP*2)) $H); do ANNOTATE+=(-fill blue -pointsize 10 -annotate "+2+${y}" "$y"); done

magick source.png -fill none -stroke red -strokewidth 1 -draw "$DRAW" "${ANNOTATE[@]}" grid.png
```

Crop to the region you're measuring first (`magick source.png -crop WxH+x+y +repage
region.png`) before gridding it at a finer step — a full-slide grid at fine spacing is
unreadable. Label gridlines in **original image pixel units**, not any display-scaled
units — whatever you read off the rendered grid should already be the right number.

### Programmatic scans (for precise edges)

For exact boundaries — card edges, row bands, accent bar thickness — use `-trim -fuzz`
to find where content starts and ends, rather than eyeballing a grid to the pixel.

```bash
# bounding box of non-background content within a region (crop to the region first,
# narrow enough to avoid unrelated borders/lines — see the bug note below)
magick source.png -crop WxH+x+y +repage -fuzz 8% -trim +repage -format "%wx%h%O\n" info:
# -> e.g. "218x110+180+50": content is 218x110px, starting at (180,50) within the crop
```

`-fuzz N%` sets the background-match tolerance (higher = more forgiving of anti-aliasing
noise); `-trim` finds the tight bounding box of everything that *isn't* background.

Two bugs bit repeatedly here — check for both before trusting a result:

1. **Cropping a region that includes an unrelated border or connector line.** If your
   crop for "find where card1's text starts" happens to include card1's own left
   border, or a connector line running through the middle, `-trim` will report a
   bounding box that includes that border/line, masking the real answer. Narrow the
   crop to the specific element, away from any border/line pixels.
2. **Wrong `-fuzz` reference.** `-trim` matches against the crop's own corner pixel by
   default — if the crop spans a boundary between two different fills (e.g. white card
   on cream page), trim's notion of "background" can lock onto the wrong one. Crop
   tightly enough that the corner pixel is unambiguously the fill you want treated as
   background (the white card interior, not the page).

If a result looks suspicious (e.g., a boundary found somewhere a nearby crop clearly
shows it isn't), don't trust it — narrow the crop or re-verify against a gridded crop.
Several rounds of wrong measurements traced back to one of these two bugs and cost real
time to unwind.

### Color sampling

Crop tightly to the fill you want (avoiding anti-aliased edges), then collapse to its
average color:

```bash
magick source.png -crop WxH+x+y +repage -resize 1x1! txt:-
# -> "0,0: (90,96,103)  #5A6067  srgb(...)" — the average color of that region
```

Crop small and centered on solid fill (e.g. the middle of an accent bar, not its edge)
so the average isn't diluted by anti-aliasing or adjacent colors.

### Font sizes

Don't derive point sizes from pixel height via raw dpi math — antialiasing overshoot,
ascender/descender assumptions, and font-metric differences make this unreliable (a
"53pt" pixel-derived estimate was often actually an 18-20pt element). Instead:

- If the deck's brand has a documented type scale (e.g. the `neutral` brand's
  `guidelines.md` listing title 30 pt, card title 18 pt, body 12.5 pt), **trust that
  over pixel math.** Use pixel measurement only to confirm relative hierarchy (this text
  is clearly bigger than that text), not to derive an exact number.
- Otherwise, start from a reasonable guess matching the visual weight, build, render,
  and adjust in the verify loop (below) rather than trying to nail it analytically
  up front.

## Icons and logos: never crop, always regenerate

The whole-slide PNG is low resolution relative to how large an icon needs to render in
the final deck. A typical slide canvas exports around 1376×768px for a 13.3×7.5in
slide — about 103dpi for the *entire slide*. An icon that's visually ~1in square in the
deck is therefore only ~100px in the source PNG. Crop that out and place it at 1-1.5in
in PowerPoint and it is **visibly pixelated at actual scale and zoom**, even though it
looks fine in an `export-slides` preview. The low-DPI self-check does not show
this defect, so do not crop icons from the slide image:

- **Generic icons** (a gear, a folder, a speech bubble, a magnifying glass): describe
  the exact shape, style, and color to `media:image-gen` and generate standalone at 2K
  resolution. This reproduces close to pixel-identical for simple flat-line icon
  styles. Batch several into one image-gen call as a labeled row (cheaper than one call
  per icon), then split with the icon-sheet command below.
- **Brand-specific marks** (a real product logo, a recognizable trademark): pass the
  cropped low-res source as the reference image and ask for "same composition and colors, just
  crisper, higher resolution" — never let the model freehand-reinterpret a trademark
  from a text description alone, and never fabricate one from imagination.
- **If a canonical high-res asset already exists in the project** (a shared logo/icon
  file), use that directly instead of regenerating or cropping — it's both higher quality
  and more consistent with any other deck using the same brand mark.
- **If you are re-backporting a deck that already has a built `.pptx`** (rebuilding it,
  or fixing it), its icons/logos are already embedded at full resolution — pull them out
  with `docs:pptx` (`list-images`, then `extract-images` of `<deck.pptx>` into a
  directory) and reuse them,
  rather than regenerating. Faster and pixel-identical to what was approved. Only
  regenerate an icon that doesn't already exist somewhere.

### Splitting an icon sheet

```bash
magick sheet.png -fuzz 5% -morphology Dilate Disk:5 \
  -define connected-components:verbose=true -connected-components 8 -auto-level null:
```

Reports each disjoint region's bounding box, centroid, area, and mean color in one
call. `-morphology Dilate` merges each icon's separate strokes into one blob first — the
dilated image is only used to *find* the regions; crop each reported bounding box out of
the **original** (non-dilated) file, padded a little:

```bash
magick sheet.png -crop WxH+x+y +repage sheet.png -bordercolor white -border 15 icon_1.png
```

Filter out tiny noise components by area before trusting the list (a stray anti-aliasing
speck can register as its own component).

### Autocrop and flatten

```bash
# tight crop to content, with padding added back
magick icon.png -fuzz 8% -trim +repage -bordercolor white -border 20 icon_cropped.png

# flatten near-white background noise the model introduced to true white
magick icon.png -fuzz 5% -fill "#FFFFFF" -opaque "#F9FAFE" icon_clean.png
```

Check the corner pixel color before deciding a flatten pass is needed
(`magick icon.png -format "%[pixel:p{0,0}]" info:`) — if it's not exactly the intended
background (e.g. `srgb(249,250,254)` instead of pure white), flatten it so it doesn't
show as a faint box against the slide background.

## Building the shapes

Once positions/colors/sizes are measured, write them as a `docs:pptx` `add-shapes` JSON
payload — `rounded_rect` for cards, `rect` for flat bars/backgrounds, `textbox` for
every piece of copy (with `font_name`/`font_size`/`bold`/`color`/`alignment` per run),
`line` for connectors, `image` for the icon/logo assets from above. Full schema: the
format `docs:pptx` documents for `add-shapes`.

**One `add-shapes` paragraph is a single run** — one font/size/color/weight for the whole
line. There is no mixed-run-within-a-line. For a two-color line (a bold title word next
to a grey label, or a colored keyword mid-sentence), place
**two adjacent textboxes**, one per color, and position them side by side — don't expect
one textbox to carry both.

`add-shapes` takes a flat JSON list. For fixed-position shapes (cards, bars, backgrounds,
connectors, logos) **author the file directly** — one block per shape at its measured
coordinates, even for a repeated grid of 15-20+ shapes. No loop, no template, no `jq`
templating: this is authoring, not generation.

**Two derived-position cases are handled by `add-shapes` directly — do not compute them by
hand:**

- **A row of pills/chips** (tag lists, data-source labels) whose widths depend on their
  text: use the `chip_row` type. It sizes each pill to its own rendered text and packs the
  row for you. Never hand-compute chip widths from character count.
- **An icon followed by a label** whose offset depends on the icon's aspect ratio: use the
  `icon_label` type. It derives the icon width from the source image and places the label
  at the icon's real right edge. Never hardcode the icon width or a fixed text offset.

`docs:pptx` documents both alongside the other `add-shapes` shape types.
Everything else on the slide is still hand-placed `rounded_rect`/`rect`/`textbox`/`line`/
`image` at measured coordinates.

For JSON assembly across files, use one-liner `jq` calls on the `slide-N`-keyed payloads.
The merge of single-slide files is in "Assembling the deck" below. A shift of slides 0 to 2
by 3 is `jq '{"slide-3": ."slide-0", "slide-4": ."slide-1", "slide-5": ."slide-2"}' a.json > b.json`.
A splice of a header fragment `header.json` into every slide of `deck.json` is
`jq --slurpfile h header.json 'with_entries(.value += $h[0]["slide-0"])' deck.json > out.json`.

## Assembling the deck

Build each slide as its own fragment keyed `slide-0`, so you can iterate it on a throwaway
one-slide deck (`docs:pptx` `new-deck` with one slide, `scratch.pptx`). Once the fragments are approved,
combine them into the real deck in one pass — don't `add-shapes` each fragment onto the
same file in sequence hoping the indices line up:

1. `new-deck` with N slides at `<deliverable>.pptx`: the real N-slide canvas.
2. Merge the fragments into one payload, remapping each `slide-0` to its real slide index.
   Merge single-slide files with `jq`:
   `jq -s '{"slide-0": .[0]["slide-0"], "slide-1": .[1]["slide-0"], "slide-2": .[2]["slide-0"]}' s1.json s2.json s3.json > deck.json`
3. `add-shapes` of `deck.json` onto `<deliverable>.pptx`, in place, in one call for the whole deck.
4. `add-notes` of `notes.json` onto `<deliverable>.pptx`, in place, with the notes from phase 2.

Remap the keys with `jq` as above, not `sed`: GNU-only address forms like `sed '0,/re/'`
silently no-op on macOS/BSD `sed`, so every fragment stays `slide-0` and all your shapes
pile onto slide 0. If a deck comes out with one crammed slide and the rest blank, that's
this bug.

## Verify loop

After every build:

1. `export-slides` the result **at 150 to 200 DPI** (`export-slides` default 150):
   pixelation and small misalignments genuinely don't show at low DPI. Write these into
   the deck's `renders/` subfolder (and generated icons/images into `images/`) per the
   one-folder-per-deck layout in [01-deck-outline.md](01-deck-outline.md#file-layout-one-folder-per-deck),
   not loose next to the `.pptx`.
2. Stack the source PNG and the new render for a direct side-by-side comparison:
   `magick source.png render.png -append compare.png` (vertical) or `+append`
   (horizontal).
3. Fix what's off, rebuild, re-render, re-compare. Expect 1-3 rounds per slide for a
   reasonably complex layout — that's normal, not a sign something's wrong with the
   approach. When a slide matches its source, tick its backport boxes in `checklist.md`
   before starting the next slide.
4. Before calling a slide done, **export from the actual deliverable file at its real
   target path**, not just the last intermediate scratch build. A stale intermediate
   copy can silently diverge from what actually got saved to disk — verifying the
   scratch copy and then blindly `cp`-ing it over is not the same as verifying the file
   you're about to hand over.
5. Second opinion (on by default; skip when the user asks to): load
   `ai:second-opinion` with the Skill tool and ask it to review each source PNG with
   its render from `renders/`, with this brief: the render must match the source in
   layout, positions, colours, font sizes and text; no pixelated icons or logos, no
   text bleed or ghost text, no icon distortion or icon/text collisions. Verify each
   finding against the render before acting on it; drop the ones that do not hold
   and tell the user which were dropped. When second-opinion reports no review model,
   skip the review and tell the user.

## Common first-pass bugs (expect these, don't panic)

- **Icon aspect-ratio distortion.** If an icon's on-slide width and height are both
  hardcoded independently rather than one derived from the source asset's own aspect
  ratio, resizing/re-cropping the source later (e.g. tightening a crop to remove text
  bleed) silently changes its aspect and the placed icon renders stretched. Always
  compute the unused dimension from the source image's actual pixel aspect ratio
  (`identify -format "%wx%h\n" icon.png` gives you both): `width = height *
  (source_px_width / source_px_height)`.
- **Text bleeding into an icon crop.** If an icon crop's bottom edge sits too close to
  the row below it (a title, a label), the crop can pick up a sliver of that text,
  which then renders as a faint ghost duplicate under the real native text box. Crop
  with a generous safety margin, and verify by directly reading the cropped file itself
  — not just a composited contact sheet, which can visually hide a thin sliver.
- **Icon/text collision from a uniform gap.** If several bullet rows use icons of very
  different width (e.g. a wide "key" icon next to a narrow "book" icon) with one fixed
  gap constant before the text starts, the wide icon's text will collide with it while
  the narrow icon's text sits with an awkward extra gap. Compute each row's text left
  offset dynamically — icon's own right edge plus a fixed gap — rather than one
  constant per slide.

## Next: [05-consistency-pass.md](05-consistency-pass.md)
