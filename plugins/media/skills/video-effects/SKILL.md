---
name: video-effects
description: "Renders image-to-image transition clips: style morphs through generated keyframes, region morphs, crossfades. TRIGGER when: user asks to morph one image into another, a style morph or transition, animate a style change, or crossfade two images."
allowed-tools: Bash(${CLAUDE_SKILL_DIR}/scripts/video-effects.sh:*) Read Skill
compatibility: "Requires FFmpeg with libx264 (macOS: brew install ffmpeg). Keyframes for a morph are generated with media:image-gen."
metadata:
  version: "0.1.0"
---

# Video Effects

Renders a short MP4 that transforms one image into another: a hold on the
start image, the transformation, a hold on the end image, and a slow centred
push-in over the whole clip. The style morph goes through intermediate
keyframes that an image model generates from the start image, so the
composition stays fixed while the rendering changes.

```bash
${CLAUDE_SKILL_DIR}/scripts/video-effects.sh keys START --style TEXT --dir DIR [--end END] [--tier best|fast|multi-ref] [--model PROVIDER:MODEL] [--fractions 0.25,0.5,0.75] [--force]
${CLAUDE_SKILL_DIR}/scripts/video-effects.sh morph (--keys K0 K1 ... Kn | --from DIR) --out OUT.mp4 [common options]
${CLAUDE_SKILL_DIR}/scripts/video-effects.sh region (--keys K0 ... Kn | --from DIR) --out OUT.mp4 [--spread 0.55] [--lum-weight 0.35] [--seed 7] [--steps N] [common options]
${CLAUDE_SKILL_DIR}/scripts/video-effects.sh crossfade A B --out OUT.mp4 [common options]
${CLAUDE_SKILL_DIR}/scripts/video-effects.sh blur-crossfade A B --out OUT.mp4 [--blur 20] [common options]
```

## Effects

| Effect | What it does | Inputs |
|---|---|---|
| `morph` | Optical-flow morph along the key chain: each intermediate frame warps both neighbouring keys toward each other and blends them, so shapes move instead of ghosting. Key times: with `--from`, the keys sit at their fractions (start 0, in-betweens at `--fractions`, end 1); with `--keys`, equally spaced. | 2 or more keys, start first, end last |
| `region` | A separate effect: the same flow morph, but parts of the image change at different times. The order comes from smooth random noise (`--seed`) mixed with the end image's luminance (`--lum-weight`): bright areas change first. `--spread` is the fraction of the clip over which regions are staggered. The same seed gives the same clip. `--steps` is the length of the underlying flow sequence; its memory grows with it. | same as `morph` |
| `crossfade` | Eased blend of A into B. | 2 images |
| `blur-crossfade` | Eased blend under a Gaussian blur of both images whose sigma rises to `--blur` (output pixels) at mid-transition and falls back to 0. | 2 images |

## Style morph workflow

1. Write the keyframe list:
   `${CLAUDE_SKILL_DIR}/scripts/video-effects.sh keys <start.png> --style '<target style>' --dir <dir>`.
   It writes `<dir>/keys.json` and prints every image to generate, in order.
   Without `--end`, the first entry is the end image, re-rendered from the
   start image in the given style with the same composition. Then one
   in-between per fraction, referencing the start image first and the end
   image second. Each entry has `name`, `fraction`, `prompt`, `refs`
   (absolute paths, in order), `out` (absolute path in `<dir>`), `tier`
   (the image-gen tier, default `best`: the `image_best` model of the
   image-gen config), `model` (default null: ask image-gen for no model id;
   any other value is a `<provider>:<model>` id of the image-gen config,
   passed as given, which replaces the tier's model), `aspect` (the image-gen aspect nearest
   the start image's) and `size` (2K).
   The prompts can be edited in `keys.json` before generating. The
   `--style` text can be a style line from `brand:style` (for example the
   `paper-cut-diorama` style) followed by the palette: a brand's `accent1`,
   `accent2`, `accent3`, `dk1` and `lt1` (from `brand:brand`), else the
   style's default palette.
2. Load `media:image-gen` with the Skill tool and ask it for each entry:
   the prompt, the reference images in the listed order, the tier, the model
   when not null, aspect,
   size and the output path. Generate the end image first when it is in the
   list (the in-betweens reference it), then the in-betweens in parallel.
3. Read every generated image. Regenerate an entry whose layout drifted from
   the start image (moved or resized people or objects, new objects, changed
   text). When the end image is regenerated, regenerate every in-between too,
   since they reference it.
4. Render: `${CLAUDE_SKILL_DIR}/scripts/video-effects.sh morph --from <dir> --out <dir>/morph.mp4`.
   `--from` reads `keys.json`, checks that every image exists and uses the
   chain start, in-betweens by fraction, end. `region --from <dir>` works the
   same way.
5. Read the frame strip (`<out stem>_frames.png`) and show it to the user.

An end image the user supplies (`--end`) must have the start image's
composition. An end image generated separately, not from the start image,
does not line up: people and objects sit in different places, and the morph
shows them sliding and blending.

## Common options

| Option | Default | Meaning |
|---|---|---|
| `--out` | required | Output MP4 |
| `--trans` | 3.5 | Transformation length, seconds |
| `--hold` | 1.5 | Hold on the start and on the end image, seconds |
| `--hold-start`, `--hold-end` | `--hold` | Override one hold |
| `--push-in` | 0.08 | Centred zoom from 1 to 1 + push-in over the whole clip, eased; 0 disables; at most 0.5 |
| `--size` | 1920x1080 | Output WxH, even numbers, at most 7680 per side; vertical sizes such as 1080x1920 work |
| `--fps` | 30 | Frames per second |
| `--strip` | `<out stem>_frames.png` | Frame strip path, `.png`, `.jpg` or `.jpeg` |
| `--force` | off | Replace existing outputs; without it an existing MP4, strip or sidecar is refused |

Every image is centre-cropped to the output aspect (no squash); a key whose
aspect differs from the output by more than 2 % gets a warning on stderr. At
zoom 1 the frame shows the whole cropped image, so the first frame equals a
still of the start image.

A 3.5 s transformation suits fast-paced films, 5.6 to 7 s calmer ones.

## Outputs

- `OUT.mp4`: H.264, yuv420p, no audio.
- `<out stem>_frames.png`: 6 evenly spaced frames of the transformation
  (first = its start, last = its end) in a 3x2 grid of 640-pixel-wide tiles.
- `OUT.mp4.json`: effect, every parameter, inputs with SHA-256, fps, size,
  frame counts (holds, transformation, total), duration, work canvas size,
  OpenCV, NumPy and FFmpeg versions.

The paths of the three files are printed on stdout.

## Using a clip in a short-video film

Render with `--size` and `--fps` equal to the film's `video:` settings. The
scene needs `Engine: clip` in the film's storyboard. Load `media:short-video`
with the Skill tool and ask it to import the MP4 into that scene with its
`clip` command.

## Known limits

- Objects whose shape differs between consecutive keys (a round table in one
  key, a square one in the next) briefly show a double outline mid-transition.
- Each render uses a lot of memory, `region` the most. Several renders run
  in parallel can exhaust RAM and make the machine swap; run them one after
  another.

## Rules

- The skill's code never generates images; keyframes come from `media:image-gen`.
- Pass absolute paths for `--out`, `--dir` and every key.
