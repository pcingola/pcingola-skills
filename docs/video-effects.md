# video-effects

## Keyframes

`keys` only writes the list of images and prompts; the agent generates them with `media:image-gen` and regenerates a
key whose layout drifted. The end image is generated first because every in-between references it.

With `--from`, the segment boundaries of the chain are the keys' fractions, so an in-between prompted as "f % of the
way" appears at that point of the transformation.

## Flow morph

Optical flow is computed between consecutive keys only, so each pair differs by part of the style change. Where the
forward and backward flows disagree (occlusions, an object present in one key only) a forward-backward confidence
fades the flow to zero, and the frame there falls back to a plain blend of the two keys instead of pixels dragged
along wrong vectors. Both keys are warped toward the frame's time before blending, so shapes move instead of ghosting.

`region` precomputes a flow sequence of `--steps` frames as uint8 and reads each pixel at its own delayed time. Its
memory is the number of steps times the canvas size, which is why the default is capped and `--steps` bounded.

## Canvas and push-in

Keys are cover-fitted to a work canvas of the output size times `1 + push-in`. The push-in is a centred crop of that
canvas scaled to the output, so zoom 1 shows the whole cropped image and the full zoom is a 1:1 crop, never an
upscale. Keys are kept as uint8 to save memory; transformation frames are float32 and rounded to uint8 once, on
output.

The blur sigmas, the flow tolerance and the region delay-field blurs were tuned on a reference canvas and scale with
the square root of the canvas area relative to it (`frames.canvas_scale`), so they cover the same share of the picture
at any output size.

## Outputs

An FFmpeg failure removes the partial MP4 and strip. The sidecar `OUT.mp4.json` identifies the exact keyframes (path
and SHA-256 per input) and holds every parameter, so the clip can be rendered again.
