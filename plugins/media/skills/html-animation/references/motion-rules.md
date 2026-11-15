# Motion rules for flat charts and diagrams

These rules apply to drawn 2D chapters: bar charts, lines, dots, diagrams, numbers. They do not apply to a three.js
chapter, where a camera move is the main movement.

## Movement

- No camera move, no 3D tilt, no bounce or elastic easing. Movement comes from marks arriving.
- Marks arrive one way each: bars grow from zero at their baseline, a value fades in after its bar lands, dots appear
  in a wave, lines draw from their start, numbers count up to their value.
- Each arrival eases out over about 0.6 s (GSAP `power2.out`, anime.js `outQuad`, Motion `easeOut`).
- Arrivals follow reading order (left to right, top to bottom), staggered by 0.15 to 0.3 s.
- A count-up ends on the exact value in `content.json`.

## Colour and focus

- Marks start in one muted colour (`content.json`, for example `muted`).
- The mark the headline is about takes the one accent colour (`accent`), after the others have landed.
- Focus comes from recolouring that mark or fading the others, never from moving them.

## Chapter frame

Every chart chapter of an animation has the same frame:

- a small label at the top (`chartLabel`);
- a headline that states the finding in a sentence ("The south installed the most panels"), not the chart's topic;
- one drawing;
- a source line at the bottom.

The label and headline fade in first; the drawing builds; the accent and the source line come last.

## Choice of drawing

The drawing follows the claim: a bar chart compares values, a line shows change over time, a stacked bar or a
unit chart shows a share of a total, two bars with a bracket show a gap. Consecutive chart chapters use different
drawings when their claims differ.
