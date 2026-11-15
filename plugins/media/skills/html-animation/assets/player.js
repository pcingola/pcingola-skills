/*
 * html-animation player. Copied into each animation folder by `init`; never edited by hand.
 *
 * index.html (written by `build`) sets window.HA_CONFIG = {title, size, width, height, fps, lib, chapters, content},
 * loads the libraries, this file and the chapter scripts, then calls HA.start().
 *
 * Global time t (seconds) belongs to the chapter with start < t <= start + duration (t = 0: the first chapter),
 * so t at a chapter's end shows that chapter's finished state. Every frame, during playback too, is a seek:
 * the adapter of the timing library maps t to the chapter's local time and seeks its paused timeline.
 */
(function () {
  "use strict";

  var cfg = window.HA_CONFIG;
  var params = new URLSearchParams(window.location.search);
  var embedded = window.parent !== window;
  var stillMode = params.has("still");

  var builders = {};
  var entries = [];          // [{id, title, start, duration, section, timeline}]
  var current = null;        // the visible entry
  var time = 0;
  var playing = false;
  var playOrigin = 0;        // performance.now() at t = 0 of the running playback
  var errors = [];
  var warnings = [];
  var resolveReady;

  var HA = window.HA = {
    lib: cfg.lib,
    content: cfg.content,
    width: cfg.width,
    height: cfg.height,
    fps: cfg.fps,
    title: cfg.title,
    chapters: [],
    errors: errors,
    warnings: warnings,
    duration: 0,
    get time() { return time; },
    get playing() { return playing; }
  };
  window.__timelines = window.__timelines || {};
  window.HA_READY = new Promise(function (resolve) { resolveReady = resolve; });

  // Adapters: one per timing library. prepare(tl) pauses the timeline, length(tl) is its duration in seconds,
  // seek(tl, local) shows its frame at local seconds.
  var ANIME_ZERO = 1e-3;
  var adapters = {
    gsap: {
      prepare: function (tl) { tl.pause(0); },
      length: function (tl) { return tl.duration(); },
      seek: function (tl, local) { tl.pause(); tl.seek(local, false); }
    },
    anime: {
      // anime.js 4 counts timeline time in milliseconds (engine.timeUnit "ms", the default). A child renders its
      // start state only when the playhead passes it backwards, so prepare runs to the end and back. At time 0
      // exactly anime.js fires no onRender or onUpdate, so seeks stop 1 microsecond after 0.
      prepare: function (tl) { tl.pause(); tl.seek(tl.duration); tl.seek(ANIME_ZERO); },
      length: function (tl) { return tl.duration / 1000; },
      seek: function (tl, local) { tl.pause(); tl.seek(Math.max(local * 1000, ANIME_ZERO)); }
    },
    motion: {
      prepare: function (c) { c.pause(); c.time = 0; },
      length: function (c) { return c.duration; },
      seek: function (c, local) { c.pause(); c.time = local; }
    }
  };
  var adapter = adapters[cfg.lib];

  HA.chapter = function (id, build) { builders[id] = build; };

  // A seeded generator for values that look random but stay the same on every load (mulberry32).
  HA.random = function (seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) >>> 0;
      var x = Math.imul(a ^ (a >>> 15), 1 | a);
      x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x;
      return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
    };
  };

  function post(msg) {
    if (embedded) window.parent.postMessage(msg, "*");
  }

  function entryAt(t) {
    for (var i = 0; i < entries.length; i++) {
      if (t <= entries[i].start + entries[i].duration) return entries[i];
    }
    return entries[entries.length - 1];
  }

  function clamp(t) { return Math.min(Math.max(Number(t) || 0, 0), HA.duration); }

  function show(entry) {
    if (current === entry) return;
    entries.forEach(function (e) { e.section.style.visibility = e === entry ? "visible" : "hidden"; });
    current = entry;
  }

  function render(t) {
    time = clamp(t);
    if (!entries.length) return;
    var e = entryAt(time);
    show(e);
    if (e.timeline) {
      try {
        adapter.seek(e.timeline, Math.min(time - e.start, e.duration));
      } catch (err) {
        report("seek " + e.id + ": " + err);
      }
    }
    updateBar();
  }

  HA.seek = function (t) {
    if (playing) playOrigin = performance.now() - clamp(t) * 1000;
    render(t);
    post({ type: "ha:time", t: time, chapter: current ? current.id : null, playing: playing });
  };

  function frame(now) {
    if (!playing) return;
    var t = (now - playOrigin) / 1000;
    if (t >= HA.duration) {
      render(HA.duration);
      playing = false;
    } else {
      render(t);
      requestAnimationFrame(frame);
    }
    post({ type: "ha:time", t: time, chapter: current ? current.id : null, playing: playing });
  }

  HA.play = function () {
    if (playing) return;
    if (time >= HA.duration) time = 0;
    playing = true;
    playOrigin = performance.now() - time * 1000;
    requestAnimationFrame(frame);
  };

  HA.pause = function () {
    playing = false;
    HA.seek(time);
  };

  function report(msg) {
    errors.push(msg);
    if (window.console) console.error("html-animation: " + msg);
  }

  // Visible elements with an id under a point or intersecting a rectangle (stage pixels), innermost first.
  HA.hits = function (q) {
    var stage = document.getElementById("ha-stage");
    var box = stage.getBoundingClientRect();
    var s = box.width / cfg.width;
    var r = q.rect ? { x: q.rect.x, y: q.rect.y, w: q.rect.w, h: q.rect.h }
                   : { x: q.point.x, y: q.point.y, w: 0, h: 0 };
    var x0 = box.left + r.x * s, y0 = box.top + r.y * s, x1 = x0 + r.w * s, y1 = y0 + r.h * s;
    if (!current) return [];
    var found = [];
    current.section.querySelectorAll("[id]").forEach(function (el) {
      var b = el.getBoundingClientRect();
      if (b.width <= 0 && b.height <= 0) return;
      if (b.right < x0 || b.left > x1 || b.bottom < y0 || b.top > y1) return;
      if (!visible(el, current.section)) return;
      var depth = 0;
      for (var p = el; p && p !== current.section; p = p.parentNode) depth++;
      found.push({ id: el.id, depth: depth, area: b.width * b.height });
    });
    found.sort(function (a, b) { return b.depth - a.depth || a.area - b.area; });
    return found.map(function (f) { return f.id; });
  };

  function visible(el, top) {
    var opacity = 1;
    for (var p = el; p && p !== top; p = p.parentElement) {
      var cs = getComputedStyle(p);
      if (cs.display === "none") return false;
      opacity *= parseFloat(cs.opacity);
    }
    var own = getComputedStyle(el);
    return own.visibility !== "hidden" && opacity > 0.01;
  }

  function onMessage(ev) {
    var m = ev.data;
    if (!m || typeof m.type !== "string" || m.type.indexOf("ha:") !== 0) return;
    if (m.type === "ha:seek") { HA.seek(m.t); }
    else if (m.type === "ha:play") { HA.play(); }
    else if (m.type === "ha:pause") { HA.pause(); }
    else if (m.type === "ha:query") {
      post({ type: "ha:hits", qid: m.qid, t: time, chapter: current ? current.id : null, ids: HA.hits(m) });
    }
  }

  // Stage scaled to fit the window; mark coordinates stay in stage pixels.
  function fit() {
    var stage = document.getElementById("ha-stage");
    var w = window.innerWidth, h = window.innerHeight;
    var s = Math.min(w / cfg.width, h / cfg.height);
    stage.style.transform = "translate(" + (w - cfg.width * s) / 2 + "px," + (h - cfg.height * s) / 2 + "px) scale(" + s + ")";
  }

  // Standalone play/pause and scrub bar; absent in the editor iframe and with ?still.
  var bar = null;
  function makeBar() {
    bar = document.createElement("div");
    bar.id = "ha-bar";
    bar.innerHTML = '<button id="ha-play" type="button">Pause</button>' +
      '<input id="ha-scrub" type="range" min="0" step="0.001">' +
      '<span id="ha-clock"></span>';
    document.body.appendChild(bar);
    var scrub = bar.querySelector("#ha-scrub");
    scrub.max = String(HA.duration);
    bar.querySelector("#ha-play").addEventListener("click", function () {
      if (playing) HA.pause(); else HA.play();
    });
    scrub.addEventListener("input", function () { HA.pause(); HA.seek(parseFloat(scrub.value)); });
    window.addEventListener("keydown", function (e) {
      if (e.code === "Space") { e.preventDefault(); if (playing) HA.pause(); else HA.play(); }
    });
  }

  function updateBar() {
    if (!bar) return;
    bar.querySelector("#ha-play").textContent = playing ? "Pause" : "Play";
    bar.querySelector("#ha-scrub").value = String(time);
    bar.querySelector("#ha-clock").textContent = time.toFixed(2) + " / " + HA.duration.toFixed(2) + " s";
  }

  HA.start = function () {
    var start = 0;
    cfg.chapters.forEach(function (c) {
      var section = document.getElementById("ch-" + c.id);
      var entry = { id: c.id, title: c.title, start: start, duration: c.duration, section: section, timeline: null };
      section.style.visibility = "hidden";
      var build = builders[c.id];
      if (!build) {
        report("chapter " + c.id + ": no HA.chapter(\"" + c.id + "\", ...) call");
      } else {
        try {
          var ctx = {
            el: function (id) {
              var found = document.getElementById(id);
              if (!found) throw new Error("no element with id \"" + id + "\"");
              return found;
            },
            root: section,
            content: cfg.content,
            duration: c.duration,
            lib: cfg.lib
          };
          entry.timeline = build(ctx);
          if (!entry.timeline) {
            report("chapter " + c.id + ": build returned no timeline");
          } else {
            adapter.prepare(entry.timeline);
            var len = adapter.length(entry.timeline);
            if (len > c.duration + 1e-3) {
              warnings.push("chapter " + c.id + ": timeline is " + len.toFixed(3) + " s, longer than its duration " + c.duration + " s");
            }
            if (cfg.lib === "gsap") window.__timelines[c.id] = entry.timeline;
          }
        } catch (err) {
          report("chapter " + c.id + ": " + (err && err.stack ? err.stack : err));
        }
      }
      entries.push(entry);
      HA.chapters.push({ id: c.id, title: c.title, start: start, duration: c.duration });
      start += c.duration;
    });
    HA.duration = start;

    fit();
    window.addEventListener("resize", fit);
    window.addEventListener("message", onMessage);
    if (!embedded && !stillMode) makeBar();

    var t0 = params.has("t") ? clamp(params.get("t")) : 0;
    render(t0);

    var fonts = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
    fonts.then(function () {
      render(t0);
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          post({ type: "ha:ready", title: cfg.title, width: cfg.width, height: cfg.height, fps: cfg.fps,
                 duration: HA.duration, chapters: HA.chapters });
          post({ type: "ha:time", t: time, chapter: current ? current.id : null, playing: false });
          resolveReady({ errors: errors, warnings: warnings });
          if (!embedded && !stillMode && !params.has("t")) HA.play();
        });
      });
    });
  };

  window.addEventListener("error", function (e) { report(String(e.message || e)); });
})();
