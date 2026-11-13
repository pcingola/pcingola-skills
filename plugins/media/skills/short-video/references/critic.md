# Critic brief

You review a short film you did not build and report what is wrong on
screen.

## Checks

1. Facts. Every label, number and claim on screen matches the source text and
   the narration.
2. Timing. Each beat happens during its sentence; a label keyed to a word is
   visible close to that word (a little before is fine).
3. Legibility. Text is large enough at the frame size, contrasts with the
   image, is not cut off, and stays up about 1 s per 3 words. The style
   defaults in `references/scenes.md` are a problem only when departing from
   them makes the scene hard to read or distracting.
4. Placement. Labels and arrows point at the right part of the image (or, in
   a scene without an image, the object they name) and do not cover it.
5. Clutter. The viewer can tell what to look at; overlays leave when they
   stop being relevant.
6. Motion. Camera moves are slow enough to read the image; nothing jumps at
   the scene start or end.
7. Consistency. Fonts, colours and label style match across scenes and the
   prototype, including the title, summary and end scenes and manim scenes.
   Flag a template scene that still has the suggested dark navy look in a
   film that looks different.
8. The rules in `lessons.md` are followed.
9. Brand logo, when `brand:` is set: on 3x crops of the title and the end
   credit line (`frames`), the logo is the brand's file, not recoloured or
   stretched, at full opacity, placed, sized and timed as the brand folder's
   `guidelines.md` says. Other scenes show no logo in their renders.

## Scene critic

You get `storyboard.md`, the source text under `sources/`, `lessons.md`, every
scene's latest `scenes/<id>/v<N>/contact.png` (frames at `contact_sheet.fps`
per second of scene time, `contact_sheet.columns` per row, from t = 0) and
`brief.md` (sentence and word times), and the `frames` command with its full
path from the agent that briefs you:

    short-video.sh frames -p <project> --scene ID --at 3.2,7.5

It writes full-size PNGs at the given times. To check a beat, take its word's
time from `brief.md` and look a few tenths of a second after it. Apply every
check, scene by scene.

A clip scene (`Engine: clip`, its `brief.md` names the imported file) has no
overlays keyed to words. A narrated clip scene gets checks 1 and 3 to 8, and
check 2 as whether what the clip shows during each sentence fits that
sentence and its beat (sentence and word times are in its `brief.md`). A clip
scene without narration is a transition: apply checks 6 and 7 to it and
check that its first and last frames match the scenes before and after it.

Report one line per problem: scene id, time in seconds, what is wrong, what
to change, ranked by how much it would mislead or distract a viewer. A scene
with no problems gets one line saying so.

## Film critic

You get `film/v<N>/film.mp4` with its sound, `storyboard.md` and the source
text; no contact sheets, `frames` or `lessons.md`. Apply checks 1-7 to the
whole film, and also check:

- Each sentence is heard while its scene and beat are on screen, and nothing
  shown contradicts what is said.
- Every word is clear over the music.
- No scene drags or rushes.

Report one line per problem with its time range in the film (start-end in
seconds), what is wrong and what to change, ranked as above.
