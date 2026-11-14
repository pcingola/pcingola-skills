# short-video

## Project directory

A film project is a directory given by path, and every file the tool writes for a film goes inside it. A path at or
under `forbidden_project_root` in the settings is refused. Its default is null, which refuses no path.

## Storyboard source

A project keeps `storyboard.md` (edited by people in a text editor) or `storyboard.json` (written by the Studio page).
`parse_markdown` turns the Markdown into the dict `storyboard.json` stores, and every command works on that dict, read
by `storyboard.read` from whichever file exists. A project with both files is refused: keeping two files in step when
both are edited is not handled. Markdown syntax (headings, keys, table cells, line numbers) is checked by the parser;
every structural rule (required keys per scene kind, engines, templates, speaker names, list lengths, types) is in
`storyboard.check`, which both files go through, with field names and line numbers per file. No command rewrites the
storyboard file. The author is not part of the stored structure: it is a setting, and `load` copies it into template
scenes for `card.js`.

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

## Staleness

Versions store no hashes of their inputs, and `assemble` takes each scene's latest rendered version without checking
it against the storyboard. `status` compares what a version holds with what the commands would make now: a voice
version's `timing.json` (sentences, and each sentence's recorded voice) with the storyboard and the resolved voices,
and a rendered scene version's voice version, engine, `background.png`, `brief.md` and `card.js` with the latest voice
version and what `scaffold` writes now. A change that reaches the page only through the agent (a lesson, a reworded
`references/scenes.md`) is not detected.

## Narration and music

The narration is made by the agent with `media:voiceover` and the music with `media:music` or supplied by the user.
`voice` checks the voiced sentences against the storyboard, so a script voiced before a later edit cannot be imported.
Each sentence has a resolved voice: its speaker's voice, or `voice:` without a speaker, with the sentence's own
settings (`voices`) over it. A scene is voiced in parts, one per run of consecutive sentences with the same speaker and
resolved voice. `voice` checks the backend, voice, speed and style in every recording's `timing.json` against its
run's resolved voice, and `script` deletes recordings that no longer match the scene's part layout, so a recording in
another voice cannot be imported. A joined recording lists each part's voice and number of sentences, which `status`
uses to check each sentence's recorded voice.

## HTML scenes

Each scene version is a self-contained HyperFrames project with its own copy of the background image (when it has
one), GSAP and the timing data, so an old version renders the same later. On the pinned HyperFrames version the render length comes from
the root element's `data-duration` and, without it, from the GSAP timeline length, not from the clips. The root and
the background layers therefore carry `data-duration` marked `data-full-length`; every scaffold that copies an
`index.html` rewrites those to the scene length, the narration plus the template's `hold_seconds`. `render` checks
every literal timing-helper call against `timing.json` before rendering, because a wrong call throws in the page and
renders a scene with no animation.

A scene without `Image:` starts from `assets/scene-drawn.html`: `#bg-fill` as a flat colour or gradient and the
`#anchored` layer the camera moves, with no `#bg-image` and no `background.png`, since what it shows is drawn in the
page. A scene whose image was removed keeps its previous page, which still shows `background.png`; `render` refuses a
non-template page that uses `background.png` when the version has none, because the picture would render broken.

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

The starting `scene.py` (`assets/manim_scene.py`) is a moving skeleton (a `ValueTracker`-driven dot and one
`Transform` per sentence) that renders as it is; the only setting it takes is `manim.background_color`.

Manim leaves the sample aspect ratio of its H.264 stream unset, HyperFrames writes 1:1, and `assemble`'s concat needs
them equal. `render` sets it with the `h264_metadata` bitstream filter, without re-encoding.

## Video scenes

`Engine: video` scenes call `ai_models.video.animate` with the image, the prompt, the narration length, the `video:`
size and an optional seed; the model is task `video` of `config.yaml`. The skill project depends on `ai-models` like
image-gen: the wrapper adds the `local` extra (`ai-models[diffusers]`, torch from the CUDA 13.0 index on Linux) only
when `config.yaml` has a provider of kind `diffusers`. The `ai_models` import happens inside `video_scene.render`, after
the version checks, so every other command runs without a model configured.

A model returns clips of its own length, size and frame rate. `video_scene.fill` re-encodes the clip to `silent.mp4`:
scale to cover the `video:` frame and centre-crop, the `video:` fps, `setsar=1`, the `encode:` codec, then the last
frame held (`tpad=stop_mode=clone`, the filter of clip scenes) when the clip is shorter than the narration and `-t` at
the narration length when longer. Holding the last frame keeps the model's motion at its own speed; slowing the clip
down or looping it would change the motion or show a jump at the loop point. `model.mp4` keeps the model's clip, and
`meta.json` records the model, the prompt, the seed and the clip length.

## Clip scenes

`clip` refuses a file that is not at the `video:` size and frame rate instead of scaling it. Frame rates count as
equal when both reduce to the same fraction with a denominator of at most 1001, or differ by less than 0.001 fps, so
`fps: 29.97` matches NTSC's 30000/1001. `silent.mp4` is re-encoded with the `encode:` settings, the `video:` fps and
`setsar=1`, and a silent clip scene gets silence at the film's sample rate and channel layout, so clip scenes join
HTML, manim and video scenes in the concat.

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

## Review

Motion is judged by agents looking at the rendered scenes and the film, and no code measures it: a frame comparison
is a proxy tied to how scenes are rendered today, and the rule (no stretch still for longer than about 2 s) is about
what a viewer sees. The agent that makes a scene takes `frames` at one per second and compares frames 2 s apart: each
pair shows a new framing (the view moved by about 10% of the frame or more) or a new drawn, flowing or counting
element, so a slow drift of a few pixels fails. The contact sheet's thumbnails are too small for this.

The review runs on the assembled film by default: the film critic (`critic.model`, through `ai:second-opinion`)
reports at most `critic.max_findings` findings, each with a time range in the film, limited to what misleads or bores
a viewer: still stretches, wrong facts or numbers, narration that does not match the picture, unreadable text, and
narration hard to hear or audio defects. Consistency of fonts and colours and the brand logo are not on its list; the
logo is checked in post-production. Each round ends in one assembly, and `critic.rounds` (default 1) sets how many
rounds run. The scene critic subagent (`critic.claude`) is off by default. `validate` checks that `critic.rounds` and
`critic.max_findings` are whole numbers of at least 1.

## Audio check

Each channel is checked on its own, because a mono downmix halves a defect in one channel. The burst threshold sits
above the level speech sibilants reach in finished films, so normal speech is not flagged.
