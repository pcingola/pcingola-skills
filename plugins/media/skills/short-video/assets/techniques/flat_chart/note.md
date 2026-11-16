# flat_chart

A flat d3 chart built mark by mark with GSAP: label, headline, grid, bars in reading order, values, accent, source.

## When to use

- A comparison of values, a change over time, a share of a total: a claim that a chart states better than a 3D scene.
- The bar chart is the example. Pick the drawing from the claim: a line for change over time, a stacked bar or unit chart for a share, two bars with a bracket for a gap.

## Build

- d3 (`d3.min.js`) builds the SVG once at load: scales, grid, axis, bars, value and category labels. Every created element has an id.
- GSAP animates it; no three.js. Colours are CSS variables used through `style("fill", "var(--muted)")`, so a restyle changes only `:root`.
- Bars grow with `tl.from(rect, { attr: { y: base, height: 0 } })`. A `scaleY` tween with `svgOrigin` on the bar group put the bars at a wrong height.
- The accent is a second rect over the accent bar that fades in; the other bars drop to 60% opacity at the same time.
- No global named `top`, `name`, `status` or `parent`: a top-level `const top` throws, since `window.top` exists.

## Camera and timing

- No 3D tilt, no bounce or elastic ease. Movement comes from marks arriving, then from one flat push on `#anchored`.
- Label 0.1 s, headline 0.3 s, grid 0.8 s. Bars from 1.3 s, 0.25 s apart, each over 0.6 s (`power2.out`); its value 0.6 s after it starts.
- Accent 1.0 s after the last bar starts; source 0.5 s later.
- From the accent to 0.5 s before the end, `#anchored` pushes from scale 1 to 1.1 (`sine.inOut`), with its origin set so every label stays inside the 60 px margin. Without it the 3 s after the accent are still and fail the motion check. A narrated scene gives each sentence after the bars its own flat push to the mark it names (`references/motion-rules.md`).

## What to vary

- `DATA`, `ACCENT`, `UNIT`, the log or linear scale and its ticks, the money format.
- The headline states the finding as a sentence, not the chart's topic.
- Narrated scene: each bar's start on the word that names it (`W(n, "2011") - 0.1`), the accent on the sentence that makes the claim.
