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
`assemble` remove a half-written version on failure, keeping its number used. `scaffold`, `voice`, `clip`, `music`,
`html` and `assemble` each write a new version, and `scaffold --refresh` rewrites the latest version in place while it
is not rendered. `render` rewrites the outputs of the latest scene version, except on a world scene, where it writes a
new version of every scene of the world. The other commands write no version.

A scene or world version carries forward every file the author added (fonts, pictures, `background.mp4`): `scaffold`
copies each file and directory of the previous version that it does not generate itself (`scenes.GENERATED`) into the
new one.

## Staleness

Versions store no hashes of their inputs, and `assemble` takes each scene's latest rendered version without checking
it against the storyboard. `status` compares what a version holds with what the commands would make now: a voice
version's `timing.json` (sentences, and each sentence's recorded voice) with the storyboard and the resolved voices,
and a scene version's voice version, engine, `background.png`, `brief.md` and `card.js` with the latest voice version
and what `scaffold` writes now. An HTML scene is judged on its latest page version, rendered or not, since the HTML
film plays pages; `rendered` says whether that version has a render for `assemble`. Other engines are judged on their
latest render. A world scene is judged with its world (`world.page_reasons`, `world.render_reasons`): a newer world
version, or a change of the world's scenes, voice versions, lengths, Briefs or On screen text, makes every scene of the
world stale. A change that reaches the page only through the agent (a lesson, a reworded `references/scenes.md`) is
not detected.

## Narration and music

The narration is made by the agent with `media:voiceover` and the music with `media:music` or supplied by the user.
`voice` checks the voiced sentences against the storyboard, so a script voiced before a later edit cannot be imported.
Each sentence has a resolved voice: its speaker's voice, or `voice:` without a speaker, with the sentence's own
settings (`voices`) over it. A scene is voiced in parts, one per run of consecutive sentences with the same speaker and
resolved voice. `voice` checks the speech model, voice, speed and style in every recording's `timing.json` against its
run's resolved voice, and `script` deletes recordings that no longer match the scene's part layout, so a recording in
another voice cannot be imported. A joined recording lists each part's voice and number of sentences, which `status`
uses to check each sentence's recorded voice.

## HTML scenes

Each scene version is a self-contained HyperFrames project with its own copy of the background image (when it has
one), the timing data, `gsap.min.js` and every library and kit file its page loads (`scenes.copy_page_files`), so an
old version renders the same later. On the pinned HyperFrames version the render length comes from
the root element's `data-duration` and, without it, from the GSAP timeline length, not from the clips. The root and
the background layers therefore carry `data-duration` marked `data-full-length`; every scaffold that copies an
`index.html` rewrites those to the scene length, the narration plus the template's `hold_seconds` (a silent scene: its
`Length:`).

An HTML scene needs no render to be seen: `stills`, `check` and `html` work on its latest page version
(`pages.scene_page`), and only an MP4 film needs `render`. A silent scene's `timing.json` is
`{"duration": <length>, "sentences": []}` with no `voice_version`, and `render` muxes silence. `scaffold --estimate`
times a narrated scene without a recording: each word lasts 1 / `length.words_per_second` s, `timing.json` holds
`estimated` (that rate), and `render` refuses the version until the voice is recorded and the scene scaffolded again.
It applies to an HTML scene outside a world only.

`check` and `render` run the same static checks (`scenes.check_page`) before `hyperframes lint`:

- every literal timing-helper call against `timing.json`, because a wrong call throws in the page and renders a scene
  with no animation;
- a seekable page (`check_timeline`): the root registers `window.__timelines["<id>"]` (GSAP) or listens for
  `hf-seek` (anime.js, Motion, three.js; required with `data-no-timeline`);
- the determinism rules below;
- each `<video>` file exists in the version and lasts the scene within one frame, because HyperFrames stops updating a
  video, and a camera move on it, where the file ends.

A scene without `Image:` starts from `assets/scene-drawn.html`: `#bg-fill` as a flat colour or gradient and the
`#anchored` layer the camera moves, with no `#bg-image` and no `background.png`, since what it shows is drawn in the
page. A scene whose image was removed keeps its previous page, which still shows `background.png`; `check` and
`render` refuse a non-template page that uses `background.png` when the version has none, because the picture would
render broken.

HyperFrames and the animation libraries (GSAP, anime.js, Motion, d3, three.js) are pinned in
`scripts/node/package-lock.json`, so a render does not change when a package publishes a new version. A page loads a
library by bare file name (`<script src="three.min.js">`), and `scenes.LIBS` maps each allowed name to its file under
`node_modules` with its SHA-256, which `setup` checks. Only classic UMD files are listed, because module scripts do not
load from file://; three.js stays at 0.159.0, the last release with `build/three.min.js`. `setup` copies the package
files to `$PLUGIN_ENV_DIR/node` and runs `npm ci` there, outside the plugin directory; `scaffold`, `check`, `stills`,
`render` and `html` rerun it when the copies differ from `scripts/node/`. `hyperframes doctor` reports
failure whenever an optional tool is missing, so `setup` judges only the checks rendering needs (Node.js, FFmpeg,
FFprobe, Chrome).

Every engine ends in `scenes.finish`, which muxes the scene's audio with the video stream-copied. The audio is padded
and cut to the video length (`apad=whole_dur`, `atrim`) because `-shortest` with stream copy and `apad` never ends.

## Determinism

HyperFrames seeks a page frame by frame, so the frame at `t` must depend on `t` only. `determinism.check` reads the
page's inline scripts and styles, its tags and the author's own local scripts without running them, on code with
comments and string contents blanked (`js_source.JsSource`), and refuses: timers and frame loops (`setTimeout`,
`setInterval`, `requestAnimationFrame`, `setAnimationLoop`, `THREE.Clock`), the wall clock (`Date.now`, `new Date()`,
`performance.now`), unseeded randomness (`Math.random` and the library helpers built on it), d3 transitions, endless
repeats, autoplay and `.play()`, CSS animations, transitions and `@keyframes` (in styles, style attributes and strings
set from scripts), `<audio>` and `new Audio`, a `<video>` without `data-start`, run-time loads (`fetch`,
`XMLHttpRequest`, dynamic `import`, CSS `@import`), remote URLs other than `www.w3.org` namespaces, and a declaration
that shadows a timing helper (`S`, `SE`, `W`, `WE`, `ST`, `STE`). The `LIBS` files, `kit/*.js`, `timing.js` and
`card.js` are trusted and not scanned.

## Stills

`stills` takes PNGs of a page at scene times with `hyperframes snapshot --at`, which seeks the page as `render` does,
so an HTML scene is checked without an MP4. Each time is seeked twice, first `stills.WARM` (0.005 s) later, and only
the second shot is kept: on the hardware GPU the first three.js draw that links new shader programs can come out all
black, and GSAP calls no `onUpdate` for a seek to the time it is already at. A WebGL page's still with at least
`BLANK_FRACTION` (0.5) of its pixels exactly #000000 is taken again once in a new browser, and a second blank still
fails. The snapshot keeps the GPU, because SwiftShader's compositor paints a page-coloured rectangle over the canvas at
a DOM overlay's position, mirrored vertically. Stills go to `<page dir>/stills/` (a world scene's prefixed with the
scene id); `--mark` adds a copy with a red point or box, `--sheet` a labelled contact sheet.

## Shared worlds

Consecutive HTML scenes with the same `World:` share one page, `worlds/<name>/v<N>/index.html`, whose root id and
timeline key are the world name. Scene starts are frame-aligned: with $d_k$ the length of scene $k$,
$f_0 = 0$, $f_{k+1} = \mathrm{round}((d_0 + \dots + d_k)\cdot \mathrm{fps})$ and $\mathrm{start}_k = f_k/\mathrm{fps}$,
so the cut points fall on frames and rounding does not accumulate. `world.json` holds that plan and each scene's voice
version. `timing.js` gives absolute times and the helpers take the scene id first; `ST` and `STE` give a scene's start
and end.

`scaffold` on any scene of a world writes the next world version. `render` checks the plan against the storyboard,
renders the world once to `silent.mp4`, then cuts each scene's frames `[f_k, f_{k+1})` (`select` on the frame number,
re-encoded with the `encode:` settings) into a new version of that scene with its own `world.json` (world, version,
start, length), and muxes the scene's narration with `scenes.finish`. Every scene of the world gets a new version on
every render, so parallel work on two scenes of one world overwrites each other's.

## HTML film

`html` writes `film/html/v<N>/film.html` and `manifest.json` (segments with start, length, scenes, source and audio
files, and the file size). The film is a list of segments in storyboard order: a page (one scene, or a world once
across its scenes), a rendered `scene.mp4` of another engine, or a card for a scene with nothing to show, which lasts
its `Length:`, its recording or 3 s. `assets/film-player.html` owns the clock; `assets/film-scene.js`, inlined into
every page, seeks it the way HyperFrames does (the GSAP timeline, `hf-seek`, each `<video data-start>`), with the same
double draw as `stills` on a paused seek. Each page is inlined whole (`film_html.inline_page`): local scripts as text,
every other local file as a data URI; narration and the music `assemble` would use play beside the pages as 128 kbit/s
MP3 data URIs. The file plays from file:// on another machine. A font installed only on this machine is missing there,
so `html` warns for each font stack whose first family no local `@font-face` file embeds.

## Kit and techniques

`assets/kit/` holds classic three.js helper scripts that a page loads as `kit/<file>.js`; `scaffold` copies the named
files into the version, and `check`, `stills`, `render` and `html` copy any that is missing. `assets/techniques/<name>/` holds working silent GSAP pages with a still and a note.
No code reads the techniques: the agent copies a page into a scaffolded `index.html`. Their `README.md` files list the
functions and the techniques.

## Reference analysis

`refs` extracts the measurable part of a reference video or reference images into `<project>/refs/` (or `--out`) for
the agent that writes `reference.md`. For a video: full-size frames at `--fps` (default 4) and at scene changes (FFmpeg
`scene` score above 0.3), contact sheets of 12 frames, and in `refs.json` the size, fps, cut times, each frame's median
colour, a motion curve (mean absolute difference of consecutive grey frames at 12 fps, 0 to 1) and dominant colours
(k-means with a fixed seed) per sheet and per source. Images are copied and sheeted. A second run replaces the entry of
the same source and keeps the others.

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

## Presenter scenes

`Engine: presenter` scenes (`presenter_scene`) call `ai_models.video.present` with the scene's image, the voice
version's `narration.wav`, no aspect ratio (so the model's frame size is the bucket nearest the picture's), the
`Brief:` as prompt when given, and an optional seed; the model is task `presenter` of `config.yaml`. `video_scene.fill`
with `Fit.CONTAIN` fits the model clip into the `video:` frame uncropped, over a blurred copy of the clip scaled to
cover the frame, and to the scene's length; `scenes.finish` muxes
the narration. `meta.json` keeps `speech_sha256` of the recording, and `status` reports a render stale when the
recording differs from it, besides the image and voice version checks every scene has. `Brief:` is optional for this
engine and `Image:` required, in `storyboard.check` and in Studio's copy of the check. In a viewing test of Kandinsky
S2V the mouth over-articulated and lip sync had gaps, at about 23 min per 4 s of clip on a GB10, so the skill uses the
engine only when the user asks for a talking presenter.

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
`meta.json` records the model, the prompt, the seed, the clip length, `ambience_relative_db` and the
measured loudness and gain of the ambience mix.

When `model.mp4` has an audio stream (a model that generates sound with the frames) and the scene's `ambience` is not
False (`Ambience: off`), `video_scene.mix_ambience` writes `audio.wav`: the narration plus the clip's track, faded over `mix.ambience_fade`, both resampled to `mix.sample_rate` in the `encode:` channel layout,
summed with `amix=normalize=0` and stored as 32-bit float so the sum cannot clip before the film's loudness pass.
`finish` muxes `audio.wav` in place of `narration.wav`. The mix happens per scene, not in `assemble`, so the scene
critic hears the ambience and `assemble` needs no second audio stream per scene; the cost is that the ambience also
feeds the music's sidechain, so music under a video scene ducks a little more.

The model's track has no fixed loudness: two LTX-2.5 clips of the harbour film measured -29.5 and -20.7 LUFS. So the
level is relative, not a fixed gain like `music_db`: `video_scene.loudness` measures the integrated loudness (EBU R128,
`ebur128`) of the narration and of the part of the track the scene uses, and `ambience_gain` sets the track
`mix.ambience_relative_db` LU from the narration (from `mix.loudness_i` when the narration is silent), with the gain
capped at `mix.ambience_max_gain_db` so a near-silent track (-inf LUFS included) is not raised into noise. The gain is a
static `volume`, so the track keeps its own dynamics.

## Clip scenes

`clip` refuses a file that is not at the `video:` size and frame rate instead of scaling it. Frame rates count as
equal when both reduce to the same fraction with a denominator of at most 1001, or differ by less than 0.001 fps, so
`fps: 29.97` matches NTSC's 30000/1001. `silent.mp4` is re-encoded with the `encode:` settings, the `video:` fps and
`setsar=1`, and a silent clip scene gets silence at the film's sample rate and channel layout, so clip scenes join
HTML, manim, video and presenter scenes in the concat.

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

Which scenes get the caption is `storyboard.show_author`: the scene's own `show_author` (`Show author: true|false` in
storyboard.md), else its template's `show_author` rule under `templates:` (false for `title` and `end`, whose pages
show the author), else true. The per-scene key exists for pictures from the user's material that already show the
author's name, such as the first and last slide of a deck, where the caption would show the name twice; the agent sets
it from what it sees in the picture, and the critic reports a scene that shows the name and is still captioned. With
`credit.text: null` (logo only) every scene gets the logo whatever its `show_author`. Each scene entry of
`film/v<N>/manifest.json` records the `show_author` the MP4 was assembled with, so a later change is detectable. The
caption is drawn on the MP4 only; the HTML film has none. `validate` refuses a project settings file that still holds
the earlier template rule `shows_author` (the inverse of `show_author`), since it is no longer read.

## Review

Motion is judged by agents looking at stills of the scenes (`stills` on a page, `frames` on a render), and no code
measures it: a frame comparison is a proxy tied to how scenes are rendered today, and the rule (no stretch still for
longer than about 2 s) is about what a viewer sees. The agent that builds an HTML scene does not judge its own stills;
a fresh critic subagent scores them (`references/scene-critic.md`). The procedures are in `SKILL.md`.

The film critic runs only on an MP4 film, through `ai:second-opinion`, with the model of task `film_critic` of
`config.yaml` or `critic.model` of a project's `settings.yaml` (`critic` prints it). It reports at most `critic.max_findings` findings, each with a time range in the film, limited to what misleads or bores
a viewer: still stretches, wrong facts or numbers, narration that does not match the picture, unreadable text, and
narration hard to hear or audio defects. Consistency of fonts and colours and the brand logo are not on its list; the
logo is checked in post-production. Each round ends in one assembly, and `critic.rounds` (default 1) sets how many
rounds run. The scene critic subagent (`critic.claude`) is off by default. `validate` checks that `critic.rounds` and
`critic.max_findings` are whole numbers of at least 1.

## Audio check

Each channel is checked on its own, because a mono downmix halves a defect in one channel. The burst threshold sits
above the level speech sibilants reach in finished films, so normal speech is not flagged.
