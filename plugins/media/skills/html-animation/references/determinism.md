# Determinism and validate rules

The frame at `t` depends on `t` only. The player seeks the paused timeline on every frame, during playback too, so
`still` shows exactly what the browser plays, and the editor can reload at any `t`. Anything that runs on its own clock
breaks that. `validate` checks these rules on the source files; the `rule` field of each error names one.

| Rule | What `validate` checks | Fix |
|---|---|---|
| `format` | `animation.json` keys and values; `content.json` is an object; each chapter has its html and js; no chapter file outside `animation.json`; `lib/` holds the pinned timing library; `player.js` and `lib/` files are the pinned ones; no `<script>` in a chapter html | Edit the file named; `init` again restores `player.js` |
| `build` | `index.html` equals what `build` writes now | Run `build` |
| `chapter` | The script has one `HA.chapter("<id>", ...)` call with its own id | |
| `determinism` | No `setTimeout`, `setInterval`, `requestAnimationFrame`, `setAnimationLoop`, `THREE.Clock`, `Date`, `performance.now`, `Math.random`, library random functions, d3 `.transition()`, endless repeats (`repeat: -1`, `loop: true`), `autoplay: true` or `.play()`, `new Audio`, `<video>` or `<audio>` | Drive the value from the timeline; use `HA.random(seed)`; repeat a fixed number of times |
| `css-motion` | No CSS `animation`, `transition` or `@keyframes` in a chapter html, a style attribute or a script | Tween the property with the timeline |
| `offline` | No `http(s)://` or `//` URLs (except `www.w3.org` namespaces), no `fetch`, `XMLHttpRequest`, `import()` or CSS `@import` | Put files in the folder and use relative paths; put data in `content.json` |
| `id` | Every element of a chapter html has an `id` (except `style`, `br`, `wbr`), unique across chapters, not starting with `ch-` or `ha-` | |
| `target` | Scripts reach elements with `el(id)`; no `querySelector`, `querySelectorAll` or `getElementsBy*`; a selector string given to a tween or `d3.select` is `"#<id>"` of an existing element; `el("x")` names an id of the chapter html or one the script assigns; a script that creates elements (`append`, `join`, `insert`, `createElement`, a WebGL renderer) gives them ids | `d3.select(el("chart-svg"))`; `.attr("id", (d, i) => "chart-bar-" + i)`; `renderer.domElement.id = "scene-canvas"` |
| `content` | Every top-level key of `content.json` appears in some chapter script; every `content.<key>` a script reads exists | Remove unused keys or use them |
| `lib` | `d3.` and `THREE.` only with `lib/d3.min.js` and `lib/three.min.js` present; no global of another timing library | `init <folder> --lib <lib> --with d3,three` |

`validate` reads the sources without running them. Errors at run time (an exception in `build(ctx)`, a missing
element) show in `still`, which fails with the page's errors.

Values that only look random (scattered dots, noise) come from `HA.random(seed)`:

```js
var rand = HA.random(7);
var dots = d3.range(40).map(function (i) { return { x: rand() * 1600, y: rand() * 800 }; });
```

Elements in a chapter html are in their finished state: the timeline animates from a start state to it. Text and
numbers come from `content.json` and are set by the script before the timeline is built.
