# Chapter patterns

Each chapter is `chapters/<id>.html` (elements in their finished state, each with an id) and `chapters/<id>.js`
(one `HA.chapter` call that returns a paused timeline). Ids carry the chapter id as a prefix (`title-head`,
`chart-bar-2`), so they stay unique across chapters and tell the editor's user what was marked.

## Layout

The stage is `width x height` pixels of `animation.json`; the chapter's `<section>` fills it. Position elements
absolutely in stage pixels. Text sizes for 16:9: headline 64 to 120 px, body 32 to 48 px, labels 24 to 28 px. Fonts
are system fonts (`sans-serif`, `serif`, `monospace`); a web font is a file in the folder loaded with `@font-face`
and a relative URL. Set the background of each chapter on its outer element.

```html
<style>
#title-wrap { position: absolute; left: 0; top: 0; width: 100%; height: 100%; display: flex; flex-direction: column;
  justify-content: center; padding-left: 160px; box-sizing: border-box; font-family: sans-serif; }
#title-head { font-size: 120px; color: #fff; margin: 0; }
#title-sub { font-size: 48px; color: #cbd5e1; margin: 24px 0 0; }
#title-rule { width: 240px; height: 8px; margin-top: 40px; }
</style>
<div id="title-wrap">
  <h1 id="title-head"></h1>
  <p id="title-sub"></p>
  <div id="title-rule"></div>
</div>
```

## Title: text that moves in

GSAP (`from` animates from the given start values to the finished state):

```js
HA.chapter("title", function (ctx) {
  var el = ctx.el, content = ctx.content;
  el("title-wrap").style.background = content.ink;
  el("title-head").textContent = content.title;
  el("title-sub").textContent = content.subtitle;
  el("title-rule").style.background = content.accent;
  var tl = gsap.timeline({ paused: true });
  tl.from(el("title-head"), { opacity: 0, y: 60, duration: 0.8, ease: "power3.out" }, 0.2)
    .from(el("title-sub"), { opacity: 0, y: 40, duration: 0.6, ease: "power2.out" }, 0.6)
    .from(el("title-rule"), { scaleX: 0, transformOrigin: "0% 50%", duration: 0.6, ease: "power2.out" }, 0.9);
  return tl;
});
```

anime.js 4 (`{ from: v }` animates from `v` to the current value; times in ms):

```js
var tl = anime.createTimeline({ autoplay: false });
tl.add(el("title-head"), { opacity: { from: 0 }, translateY: { from: 60 }, duration: 800, ease: "outCubic" }, 200)
  .add(el("title-sub"), { opacity: { from: 0 }, translateY: { from: 40 }, duration: 600, ease: "outQuad" }, 600);
return tl;
```

Motion (keyframes `[start, end]`; `at` places a segment in seconds):

```js
return Motion.animate([
  [el("title-head"), { opacity: [0, 1], y: [60, 0] }, { duration: 0.8, ease: "easeOut", at: 0.2 }],
  [el("title-sub"), { opacity: [0, 1], y: [40, 0] }, { duration: 0.6, ease: "easeOut", at: 0.6 }]
]);
```

## Bar chart with d3

d3 draws the finished chart (scales, data join, attributes); the timing library animates it. d3 transitions are not
used. Created elements get ids.

```html
<div id="chart-frame">
  <div id="chart-label"></div>
  <h2 id="chart-headline"></h2>
  <svg id="chart-svg" width="1680" height="680"></svg>
  <div id="chart-source"></div>
</div>
```

```js
var bars = content.bars, W = 1680, H = 680, base = H - 80;
var x = d3.scaleBand().domain(bars.map(function (d) { return d.label; })).range([0, W]).padding(0.3);
var y = d3.scaleLinear().domain([0, d3.max(bars, function (d) { return d.value; })]).range([base, 60]);
var best = d3.maxIndex(bars, function (d) { return d.value; });
d3.select(el("chart-svg")).selectAll("rect").data(bars).join("rect")
  .attr("id", function (d, i) { return "chart-bar-" + i; })
  .attr("x", function (d) { return x(d.label); }).attr("width", x.bandwidth())
  .attr("y", function (d) { return y(d.value); }).attr("height", function (d) { return base - y(d.value); })
  .attr("fill", function (d, i) { return i === best ? content.accent : content.muted; });
```

Bars grow from the baseline, values fade in after, the accent comes last:

```js
// GSAP: SVG attributes through attr
bars.forEach(function (d, i) {
  tl.from(el("chart-bar-" + i), { attr: { y: base, height: 0 }, duration: 0.6, ease: "power2.out" }, 0.4 + i * 0.25);
});
tl.from(el("chart-bar-" + best), { attr: { fill: content.muted }, duration: 0.4 }, 2.4);

// anime.js 4: SVG attributes by name
tl.add(el("chart-bar-" + i), { y: { from: base }, height: { from: 0 }, duration: 600, ease: "outQuad" }, 400 + i * 250);
tl.add(el("chart-bar-" + best), { fill: { from: content.muted }, duration: 400, ease: "linear" }, 2400);

// Motion: scaleY with the origin at the bar's bottom; fill as a style
//   d3: .style("fill", ...).style("transform-box", "fill-box").style("transform-origin", "50% 100%")
sequence.push([el("chart-bar-" + i), { scaleY: [0, 1] }, { duration: 0.6, ease: "easeOut", at: 0.4 + i * 0.25 }]);
sequence.push([el("chart-bar-" + best), { fill: [content.muted, content.accent] }, { duration: 0.4, at: 2.4 }]);
```

## Count-up

A plain object or motion value counts; the timeline's own update callback writes the text, and the script writes it
once from the start value. A callback on the single tween would miss frames before the tween starts.

```js
// GSAP
var n = { v: 0 };
function show() { el("kpi-value").textContent = Math.round(n.v).toLocaleString("en-US"); }
var tl = gsap.timeline({ paused: true, onUpdate: show });
tl.to(n, { v: content.total, duration: 1.2, ease: "power2.out" }, 0.5);
show();

// anime.js 4: onRender of the timeline
var n = { v: 0 };
function show() { el("kpi-value").textContent = Math.round(n.v).toLocaleString("en-US"); }
var tl = anime.createTimeline({ autoplay: false, onRender: show });
tl.add(n, { v: content.total, duration: 1200, ease: "outQuad" }, 500);
show();

// Motion: a motion value in the sequence
var mv = Motion.motionValue(0);
function show() { el("kpi-value").textContent = Math.round(mv.get()).toLocaleString("en-US"); }
mv.on("change", show);
show();
sequence.push([mv, [0, content.total], { duration: 1.2, ease: "easeOut", at: 0.5 }]);
```

## Line that draws

```js
// GSAP and anime.js: dash the path by its length and move the offset to 0
var len = el("line-path").getTotalLength();
el("line-path").setAttribute("stroke-dasharray", len);
tl.fromTo(el("line-path"), { attr: { "stroke-dashoffset": len } },
  { attr: { "stroke-dashoffset": 0 }, duration: 1, ease: "power2.out" }, 0);            // GSAP
tl.add(el("line-path"), { strokeDashoffset: [len, 0], duration: 1000, ease: "outQuad" }, 0);   // anime.js
// Motion: pathLength from 0 to 1
sequence.push([el("line-path"), { pathLength: [0, 1] }, { duration: 1, ease: "easeOut", at: 0 }]);
```

## Library notes

- GSAP 3.13: `from`, `to`, `fromTo`, `set`; positions in seconds; labels with `tl.addLabel`.
- anime.js 4.5: `tl.add(target, params, position)`; ms; easing names `linear`, `outQuad`, `outCubic`, `inOutSine`;
  `{ from: v }` and `[from, to]` values; `anime.stagger`. Callbacks that need the values just set use `onRender`.
- Motion 14: `Motion.animate(sequence)`; seconds; easing `linear`, `easeIn`, `easeOut`, `easeInOut`, or
  `[x1, y1, x2, y2]`; transforms `x`, `y`, `scale`, `scaleX`, `scaleY`, `rotate`. Values reach the page one frame
  after a seek; the player waits for it.
