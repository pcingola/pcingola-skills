# short-video

## Project directory

A film project is a directory given by path, and every file the tool writes for a film goes inside it. A path at or
under `forbidden_project_root` in the settings is refused. Its default is null, which refuses no path.

## Settings

`init` copies the whole of `assets/settings.yaml` into the project, so a later change to a default does not reach the
keys an existing project's copy already holds.

## Versions

The highest version number ever issued is kept in `.last_version`, so a number is never handed out again, even after
the newest directory is deleted. Versions refer to each other by number: a scene version names its voice version, and
a film manifest names the scene, voice and music versions it was made from; a reissued number would make an old
reference point at different content. A version counts as complete once its `meta.json` is written, and `clip` and
`assemble` remove a half-written version on failure, keeping its number used. `scaffold`, `voice`, `clip`, `music` and
`assemble` each write a new version; `render` rewrites the outputs of the latest scene version; the other commands
write no version.

## No staleness tracking

Versions store no hashes of their inputs, and `assemble` takes each scene's latest rendered version without checking
it against the storyboard; after an edit the agent redoes what "What an edit needs" in `references/storyboard.md`
lists.

## Narration and music

The narration is made by the agent with `media:voiceover` and the music with `media:music` or supplied by the user.
`voice` checks the voiced sentences against the storyboard, so a script voiced before a later edit cannot be imported.
For every scene with a Speaker column, `voice` checks the backend, voice, speed and style in each recording's
`timing.json` against the speaker's voice, and `script` deletes recordings that no longer match the scene's speaker
layout, so a recording in another voice cannot be imported.

## HTML scenes

Each scene version is a self-contained HyperFrames project with its own copy of the background image, GSAP and the
timing data, so an old version renders the same later. On the pinned HyperFrames version the render length comes from
the root element's `data-duration` and, without it, from the GSAP timeline length, not from the clips. The root and
the background layers therefore carry `data-duration` marked `data-full-length`; every scaffold that copies an
`index.html` rewrites those to the scene length, the narration plus the template's `hold_seconds`. `render` checks
every literal timing-helper call against `timing.json` before rendering, because a wrong call throws in the page and
renders a scene with no animation.

HyperFrames and GSAP are pinned in `scripts/node/package-lock.json`, so a render does not change when either package
publishes a new version. `setup` copies the package files to `$PLUGIN_ENV_DIR/node` and runs `npm ci` there, outside
the plugin directory; `render` reruns it when the copies differ from `scripts/node/`. `hyperframes doctor` reports
failure whenever an optional tool is missing, so `setup` judges only the checks rendering needs (Node.js, FFmpeg,
FFprobe, Chrome).

Every engine ends in `scenes.finish`, which muxes the scene's audio with the video stream-copied. The audio is padded
and cut to the video length (`apad=whole_dur`, `atrim`) because `-shortest` with stream copy and `apad` never ends.

## Manim scenes

Manim runs from its own uv project, `scripts/manim/`, with its own lock. Its environment sits next to short-video's
under the parent of `PLUGIN_ENV_DIR`; `render` refuses a manim scene when `PLUGIN_ENV_DIR` is unset, since uv's
default `.venv` would be created inside the plugin directory.

`TimedScene` in the generated `sv_timing.py` counts scene time in frames and reproduces Manim's own frame counting (a
static wait renders `int(duration * fps)` frames, a wait with updaters one frame per started frame interval), so
`at(t)` lands on the frame nearest `t`. `finish()` waits to the frame nearest the narration end and raises when the
scene is already past it, so a scene that ends with `finish()` always passes the render's length check.

Manim leaves the sample aspect ratio of its H.264 stream unset, HyperFrames writes 1:1, and `assemble`'s concat needs
them equal. `render` sets it with the `h264_metadata` bitstream filter, without re-encoding.

## Clip scenes

`clip` refuses a file that is not at the `video:` size and frame rate instead of scaling it. Frame rates count as
equal when both reduce to the same fraction with a denominator of at most 1001, or differ by less than 0.001 fps, so
`fps: 29.97` matches NTSC's 30000/1001. `silent.mp4` is re-encoded with the `encode:` settings, the `video:` fps and
`setsar=1`, and a silent clip scene gets silence at the film's sample rate and channel layout, so clip scenes join
HTML and manim scenes in the concat.

## Assembly

`mix.build_filter_graph` is a pure function that builds the whole FFmpeg graph, so its stages are unit tested without
FFmpeg. Each scene's audio is cut and padded to its video length before the concat, so the voice stays in sync and the
film is exactly as long as its pictures.

Loudness normalisation takes two passes. The first runs the audio graph only and measures; the second applies the
measured values with `linear=true`, which gives the mix one gain when the targets allow it and otherwise falls back to
loudnorm's dynamic mode. The second pass also draws the creator caption, so the film is encoded once.

The caption is drawn by `drawtext` from a text file with `expansion=none`, so a name with quotes, colons or `%` needs
no filtergraph escaping; the file and logo paths sit in a fresh temporary directory and are refused if they hold
characters that would need escaping. The brand folder comes from `brand:brand` and is passed as `--brand DIR`; its
name must equal the `brand:` setting, so a folder of another brand is refused.

## Audio check

Each channel is checked on its own, because a mono downmix halves a defect in one channel. The burst threshold sits
above the level speech sibilants reach in finished films, so normal speech is not flagged.
