# beat_reel

A reel cut on the music's beat: shots change on beats, each cut marked by a slice wipe, a four-frame chromatic slice and a white flash frame; one kinetic word per shot stamps in on its cut, and a title lands on the last cut and holds.

## When to use

- A silent hook, teaser or closing montage over several clips: footage, generated video, rendered scenes.
- A list of a few verbs or names, one per shot, timed to music.
- The page ships with drawn placeholder shots. Over real footage the shots are a `background.mp4` montage cut at the same times (Over footage).

## Build

- GSAP and `kit/beat.js` (`Kit.beat`, `assets/kit/README.md`). The constants at the top of the script hold `BPM`, `OFFSET`, `SHOT_BEATS`, `WORDS`, `BANDS`, `TITLE`, `SUBTITLE` and `STAGE`.
- `CUT_TIMES` holds the start of each word shot and then the title's cut. By default it is every `SHOT_BEATS` beats of `Kit.beat.grid(BPM, {offset: OFFSET})`; any increasing times work. The shot ends, the title cut `LAST` and every effect time derive from it. The scene length `D` is the root's `data-duration`, and the title holds from `LAST` to `D`.
- A paused timeline tweens a clock over the scene; `draw(t)` sets the placeholder shots and the particles from `t`.
- Placeholder shots: a sky gradient, a sun, two ridges and light rays from a seeded generator. Each pans while it is on screen, as a camera move on footage would. The ridges sit opposite the shot's open band.
- Cuts: `Kit.beat.wipe` (bars cross the centre at the cut, alternating direction), `Kit.beat.slice` on `#slices` with `STAGE` jolted, `Kit.beat.flash` on `#flash` (one frame at full white, one at 0.55, then a 0.1 s decay).
- Words: `Kit.beat.stamp`, from scale 2 to 1 landing on the cut, a shake, a slow grow, and a blurred exit that ends one frame before the next cut. A word has opacity 0 outside its window.
- A thin SVG frame tightens on each grid beat inside a shot (`grid.list(cut, nextCut)`) and springs open on the next cut. A light sweep crosses each shot on its middle inner beat.
- `#title-shade` darkens the frame from the title's cut, most behind the title, so the title reads over bright footage.

## Camera and timing

- Punch-in 1.0 to 1.06 over each shot, on `STAGE`.
- Defaults: 120 bpm, 4 beats per shot, cuts at 0, 2, 4, 6 s, the title cut at 8 s, `D` 9.5 s (19 beats).
- A word enters 0.18 s before its cut and lands on it; the first word is on screen from frame 0.
- The title holds `D - LAST` (1.5 s by default), at least 1 s. A hold over 2 s keeps moving: the title grows by 2% per second of hold, the rule and subtitle enter at half the hold (at most 2 s after the cut), and a light sweep crosses every 4 beats from 1.5 s after the cut. That passes the motion check up to a hold of about 4 s; a longer hold needs movement of its own (a second line, a camera move on the footage).
- A frame on a cut is the flash frame; take motion-check stills off the cuts (2.1, 4.1 s).

## Length

The storyboard's `Length:` of a silent scene equals the page's total: `LAST + hold`, where `LAST` is the last entry of `CUT_TIMES` and the hold is a whole number of beats of at least 1 s. With the defaults, `Length: 9.5` (`8 + 3 * 60 / 120`). After a change of `Length:`, `scaffold --scene ID --refresh` rewrites the root's `data-duration` in an unrendered version. A whole number of beats keeps the next scene's cut on a beat.

## Music

The cuts land on the beat only when `BPM` and `OFFSET` match the film's track at this scene's place in the film.

1. Make or pick the track before the reel's cuts are fixed. `media:music` takes `--bpm N` on Lyria and ACE-Step, but the generated tempo can differ from the request.
2. Measure it with `media:music` `analyze`: its `signal` section reports the tempo and beat confidence, and `summary.md` flags a tempo that differs from the request. A beat tracker can report half or double the played tempo (`checks.tempo.relation`). Set `BPM` to the measured tempo.
3. The report gives no beat positions. Read the first beat time `b0` of the track from the onset of the first strong hit in `<clip>_wave.png`; a generated track usually starts on a beat (`b0` = 0).
4. The film plays the music from film time 0, looped. The scene starts at film time `s`, the sum of the lengths of the scenes before it (`length` prints them). Then `OFFSET = ((b0 - s) mod beat)`, with `beat = 60 / BPM`. When every earlier scene lasts a whole number of beats and `b0` = 0, `OFFSET` is 0.
5. Check the cuts with the music in the HTML film: `html`, then open `film.html#t=<s + cut>` at a few cuts and play across them.

## Narrated

Each cut lands on the word that names its shot, rounded to the nearest beat:

```js
const CUT_TIMES = [grid.snap(W(1, "first")), grid.snap(W(2, "second")), grid.snap(W(3, "third")),
                   grid.snap(W(4, "fourth")), grid.snap(W(5, "title"))];
```

The first entry is 0 when the first shot opens the scene. `D` is the root's `data-duration`, set by `scaffold` from the narration; the title holds to it. The cut times differ per shot, and the montage below takes one frame count per shot.

## Over footage

1. Cut the clips into one montage, shot `k` lasting `round((cut[k+1] - cut[k]) * fps)` frames, where `cut` is `CUT_TIMES` followed by `D` and `fps` is `video:` of `settings.yaml`. Trim by frame count so the cuts do not drift. The size is the frame size times the largest zoom; 2048x1152 covers the 1.06 punch-in. With the defaults at 30 fps the shots are 60, 60, 60, 60 and 45 frames:

   ```sh
   # in-points 3.0, 11.0, 0.5, 6.0 and 2.0 s
   ffmpeg -ss 3.0 -i a.mp4 -ss 11.0 -i b.mp4 -ss 0.5 -i c.mp4 -ss 6.0 -i d.mp4 -ss 2.0 -i e.mp4 -filter_complex "
   [0:v]fps=30,scale=2048:1152:force_original_aspect_ratio=increase,crop=2048:1152,setsar=1,trim=end_frame=60,setpts=PTS-STARTPTS[v0];
   [1:v]fps=30,scale=2048:1152:force_original_aspect_ratio=increase,crop=2048:1152,setsar=1,trim=end_frame=60,setpts=PTS-STARTPTS[v1];
   [2:v]fps=30,scale=2048:1152:force_original_aspect_ratio=increase,crop=2048:1152,setsar=1,trim=end_frame=60,setpts=PTS-STARTPTS[v2];
   [3:v]fps=30,scale=2048:1152:force_original_aspect_ratio=increase,crop=2048:1152,setsar=1,trim=end_frame=60,setpts=PTS-STARTPTS[v3];
   [4:v]fps=30,scale=2048:1152:force_original_aspect_ratio=increase,crop=2048:1152,setsar=1,trim=end_frame=45,setpts=PTS-STARTPTS[v4];
   [v0][v1][v2][v3][v4]concat=n=5:v=1:a=0[v]" -map "[v]" -an -c:v libx264 -crf 16 -pix_fmt yuv420p background.mp4
   ```

   `ffprobe -count_frames` gives the total (285 frames here).
2. Copy `background.mp4` into the version directory and add the `<video id="bg-video">` line of "Background video" in `references/scenes.md` after `#bg-fill`, with `#bg-video { object-fit: cover; }`.
3. Delete the `#shots` div, the `.shot` rules, the block between the "placeholder shots" comments and the `drawShots(t)` line in `draw`. Set `STAGE = "#bg-video"`.
4. Set `BANDS` from the footage: each word sits in the band of its clip that holds no subject (sky, floor, a dark wall). Where no band is clear, add a gradient shade behind the word. The title shot is the last clip: pick one with a calm centre, and raise the `#title-shade` alphas when its centre is bright.
5. Take stills on each word, on the frame after each cut and on the title.

## What to vary

- Palette and fonts: the `:root` variables; `--flash` is the flash colour, `--acc-1` to `--acc-4` the word glows in turn.
- Pace: `BPM` and `SHOT_BEATS`, or uneven `CUT_TIMES`. Below 1 s per shot a word is no longer read; drop the words on some shots.
- Cut effects: `Kit.beat.wipe`, `slice` and `flash` options (bar count and colours, strip offsets, flash peak and decay). A calmer reel keeps the flash and drops the wipe.
- Captions instead of single words: `Kit.beat.rise` on a caption whose lines sit in `overflow: hidden` masks, entering one beat after the cut.
