# Reference video and reference images

When the user gives a reference video or reference images, the film copies
their look and motion. A short prompt says little about either. You first
write `reference.md` in the project: a description of the reference detailed
enough that another agent could rebuild it without seeing it. The storyboard
Briefs are written from `reference.md`, the Brief check compares stills
with reference frames, and the stills critic reviews them against the same frames.

## 1. Extract the measurable part

    short-video.sh refs -p <project> --src FILE_OR_DIR [--fps 4]

It writes into `<project>/refs/`:

- per video, a folder named after the file: `t<sec>.png` frames at `--fps`,
  `cut<sec>.png` frames at scene changes, `sheet_<nn>.png` contact sheets of
  12 frames with their times;
- per image source, `images/` (or `images_<folder>/`): the images and their
  sheets;
- `refs.json`: duration, size, fps, the frame list with each frame's median
  colour, the scene-change times (`cuts`), the motion curve (`motion.values`,
  pairs of seconds and mean frame difference from 0 to 1), and the dominant
  colours (`palette`, hex and share) per sheet and per source.

Run it once per source. Each run adds its source to `refs.json` and keeps
the sources of earlier runs. Reference images that are frames of the
reference video add nothing new: read them as frames of the video, at
their times when the user gives them. A fast or dense passage needs more frames: run it
again with `--fps 8` or 12, or extract single frames with
`ffmpeg -ss T -i FILE -frames:v 1 out.png`.

## 2. Look before writing

1. Read every sheet in time order. Note what each passage shows and its
   times.
2. Read the motion curve. Peaks are cuts or fast moves, flat stretches near 0
   are holds, a steady level is a continuous camera move. Each scene change
   time in `cuts` is a hard cut unless the frames show a fast move.
3. Open full-size frames at each cut, at the start and end of each move, and
   wherever text or numbers are on screen. Sheets are too small to read type
   sizes or exact positions.
4. Measure on full-size frames. Positions and sizes are fractions of the
   frame: x from the left edge (0) to the right edge (1), y from the top (0)
   to the bottom (1), font sizes as fractions of the frame height H. Sample
   colours of specific elements from pixels (a median of a few pixels, not
   one pixel). The `refs.json` palette gives the overall colours; element
   colours come from your samples.
5. Find the parts of the reference that are not the film: editor UI, player
   controls, cursors, comments, captions of the video it was cut from. List
   them under "Not part of the film".

## 3. Write `reference.md`

Write it in the project root. One section per heading below, in this order.
State what you see as fact. Mark every statement you did not see as
**(inferred)**. Give numbers wherever the frames give them.

1. **Purpose and format.** What the reference is, its audience if known,
   aspect ratio, size, fps, duration, sound if any, chapters or parts with
   their boundary times.
2. **What each reference shows.** A table: source file, its times, what it
   shows, and anything that changes its speed (a recording played faster, a
   paused hold). Then a timeline table: time, part, event, with a pointer to
   the section that details it.
3. **Global style.** Rendering style (flat, low-poly, toon, photographic),
   texture or its absence, shading, line work.
4. **Palette.** Each colour with its hex and its role: background, each
   accent, text, each material, each state (full, empty, highlighted). Start
   from the sampled palette, then name the colour of each element.
5. **Type.** Family (or the closest Google Font, marked inferred), weight,
   case, letter spacing, size as a fraction of H, colour, for each text
   style: titles, labels, numbers, captions.
6. **Layout.** Per flat element (cards, labels, charts, legends): its box as
   fractions of the frame, fill, border, corner radius, shadow, its text
   positions and baselines.
7. **The 3D world**, when there is one. Units and axes. Each kind of object:
   shape, sizes, count and spacing, material and colour. Ground, sky, water,
   fog. Light over time: a table of time, sun direction and colour, ambient
   colour, median frame colour. Shadows (direction, softness, opacity).
   Depth of field (which band of the frame is sharp). Glow and bloom (on
   what).
8. **Camera.** A table of keyframes: time, position or framing, target,
   field of view, ease. Add a framing check per row: where two or three
   named things sit in the frame at that time. The framing checks matter
   more than the coordinates, which are estimates.
9. **Elements and their timings.** Per element: when it enters, how
   (fade, grow, draw, slide, pop), duration, ease, stagger and order, what
   it does while visible (counts, value swaps, pulses), when and how it
   leaves. Use numbered steps with times.
10. **Transitions.** Each change between parts: cut, crossfade, morph,
    camera move, mask expand. Its times and what stays fixed through it.
11. **Motion style.** The eases in use, typical durations of an entrance and
    a move, speeds of moving objects, overshoot, how long holds last, how
    numbers change (count up, hard swap).
12. **Data.** Every number and text on screen, with its source (seen, or
    from the prompt).
13. **Not part of the film.** The elements of step 2.5.
14. **Unseen parts (inferred).** Where the reference does not show a stretch
    of the film, what fills it, from the prompt and from the parts seen.
15. **Reference stills.** A table of the frames that best show each part,
    with their file names in `refs/`. The Brief check uses them.

Aim for the detail of a rebuild brief: a few hundred lines for a 30 to 60 s
reference. A section that has nothing to say gets one line that says so.

## 4. Style reference: a different subject

Usually the user wants a new subject in the style of the reference. Then add
a section **Mapping** to `reference.md` before you write the storyboard:

- A table with one row per element of the reference: the reference element,
  its role (establishing map, counter, label, hero object, empty state,
  summary card), and the element of the new subject that takes that role.
  Example: bike station disc → berth at the quay; riders drawing routes →
  ships queuing on lanes; "Empty at 8:15" label → "Crane down 23:40".
- What carries over unchanged: palette roles, type, layout boxes, camera
  grammar (framings, moves, eases), light over time, transitions, motion
  style, durations.
- What changes: the objects of the 3D world and the data. Describe each new
  object at the detail of section 7, in the reference's materials and
  colours.
- Elements of the reference with no counterpart are dropped, and new
  elements the subject needs get the style of the closest reference element.
  Name both.

## 5. Storyboard and checks

- Write each scene's `Brief:` from `reference.md` (and its Mapping): the
  framing, camera keyframes, element timings, colours with hex, type sizes
  and eases of the matching part of the reference, in film time. A Brief that
  says "in the style of the reference" without these numbers is not done.
- A page style the caller sets (a palette and fonts chosen apart from the
  reference, such as a style sample the user picked) wins over the
  reference's palette and fonts: the Briefs carry the page style's hex
  colours and font families, and the reference keeps camera, motion,
  composition and density. When the page style changes after the Briefs
  are written, rewrite the colour, ground and font lines of each HTML
  scene's Brief to it, and `scaffold --refresh` each page made before. The
  Brief check and the critic then judge palette and type against the page
  style, and camera, motion, composition and density against the reference
  stills.
- Name in each Brief the reference stills its scene should match.
- Brief check: compare each still side by side with its reference stills, as
  well as against the Brief. Fix the page where the still differs in palette,
  type size, layout, lighting, depth of field, density of objects or camera
  framing.
- Stills critic: one fresh critic, given the reference stills the Brief
  names, reviews the scene once (`references/scene-critic.md`).
