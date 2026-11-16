# Flat charts and diagrams

These rules apply to drawn 2D scenes and parts of scenes: bar charts, lines, dots, diagrams, numbers. A three.js
scene (`references/three.md`) moves by its camera instead.

## Movement

- No 3D tilt, no bounce or elastic easing. A camera move on `#anchored` (`scenes.md`) stays flat: a scale and a
  shift to the marks the sentence names.
- Marks arrive one way each: bars grow from zero at their baseline, a value fades in after its bar lands, dots
  appear in a wave, lines draw from their start, numbers count up to their value.
- Each arrival eases out over about 0.6 s (GSAP `power2.out`, anime.js `outQuad`, Motion `easeOut`).
- Arrivals follow reading order (left to right, top to bottom), staggered by 0.15 to 0.3 s, and start on the word
  that names the mark (`W(n, "word")`).
- A count-up ends on the exact value the narration or the On screen cell states.

## Colour and focus

- Marks start in one muted colour of the film's palette.
- The mark the sentence is about takes the one accent colour, after the others have landed.
- Focus comes from recolouring that mark or fading the others, never from moving them.

## Frame

A chart scene has the same frame in every chart of the film:

- a small label at the top;
- a headline that states the finding in a sentence ("The south installed the most panels"), not the chart's
  topic;
- one drawing;
- a source line at the bottom.

The label and headline fade in first; the drawing builds; the accent and the source line come last.

## Choice of drawing

The drawing follows the claim: a bar chart compares values, a line shows change over time, a stacked bar or a
unit chart shows a share of a total, two bars with a bracket show a gap. Consecutive chart scenes use different
drawings when their claims differ.
