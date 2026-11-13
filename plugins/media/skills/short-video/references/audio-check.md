# Audio check

`audiocheck` finds two defects in an audio track, each channel on its own:

- burst: a 10 ms window whose energy above 16.5 kHz is more than 30 dB above
  its median over the windows with signal, e.g. a short burst of noise;
- click: a sample-to-sample step more than 3x the track's 99.99th-percentile
  step, e.g. a discontinuity. "click step 0.82" is the largest step, in
  full-scale units.

Check each source track, never `film.mp4`: in the mix, ducked music and
speech hide the defects. Quiet bursts are missed, so listening to the film
stays part of the review.

`voice` and `music` check each new track, `assemble` the tracks it mixes, and all three print findings as
warnings.
Before `assemble`:

    audiocheck -p <project>

checks each scene's narration and the music `assemble` will use, one line per
finding or `<track> clean`, and exits 1 on any finding. `audiocheck -p
<project> --film vN` checks the tracks film vN was mixed from;
`audiocheck FILE...` checks any files.

A finding gives the time within its track. In the film, a music time is the
same time (plus multiples of the music length when it loops); a narration
time is offset by the scene's start, the sum of the earlier scenes'
`duration` in `film/v<N>/manifest.json`. Play the track there, then fix it:

- narration: voice the scene again, `voice --scene ID`, then `scaffold` and
  `render` the scene;
- generated music: a new track with `media:music`, `music.file` pointed at
  it, `music`;
- music to keep: replace the flagged span (e.g. with the same span one bar
  earlier, crossfaded) in a new file, point `music.file` at it, `music`.

Check again until every track is clean, then assemble a new film version.
Tell the user about any finding you leave in place, with its track and time.
