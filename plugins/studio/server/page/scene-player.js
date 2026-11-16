/*
 * Studio scene player: inlined by the server into a short-video scene or world page served under /scene/, which
 * runs in an <iframe sandbox="allow-scripts"> of the Studio page. The Studio page owns time; this script only seeks.
 *
 * Messages from the parent:
 *   {type: "sv:seek", t}                       page time in seconds (world time for a world page)
 *   {type: "sv:query", qid, point: {x, y}}     or rect: {x, y, w, h}, in frame pixels
 * Messages to the parent:
 *   {type: "sv:ready", width, height, duration, errors}
 *   {type: "sv:hits", qid, t, ids}             visible elements with an id under the mark, innermost first
 */
(function () {
  "use strict";

  // Full-frame layers of a scene page: never what a mark points at.
  var LAYERS = { root: 1, "bg-fill": 1, "bg-image": 1, "bg-video": 1, anchored: 1 };
  var errors = [];
  var time = 0;
  var root = null, rootId = null, W = 1920, H = 1080, duration = 0;

  window.addEventListener("error", function (e) { errors.push(String(e.message || e)); });

  function post(msg) { window.parent.postMessage(msg, "*"); }

  function seek(t) {
    time = Math.max(0, Number(t) || 0);
    var tl = window.__timelines && window.__timelines[rootId];
    if (tl && typeof tl.seek === "function") {
      try { tl.pause(); tl.seek(time, false); } catch (err) { errors.push("seek: " + err); }
    }
    try {
      window.dispatchEvent(new CustomEvent("hf-seek", { detail: { time: time, waitUntil: function () {} } }));
    } catch (err) { errors.push("hf-seek: " + err); }
    document.querySelectorAll("video[data-start]").forEach(function (v) {
      var local = time - (parseFloat(v.getAttribute("data-start")) || 0);
      if (local >= 0 && isFinite(local)) { try { v.pause(); v.currentTime = local; } catch (err) { /* not loaded */ } }
    });
  }

  // The frame scaled to fit the iframe, centred; marks stay in frame pixels.
  function fit() {
    var w = window.innerWidth, h = window.innerHeight;
    var s = Math.min(w / W, h / H);
    document.documentElement.style.overflow = "hidden";
    document.body.style.margin = "0";
    document.body.style.overflow = "hidden";
    root.style.transformOrigin = "0 0";
    root.style.transform = "translate(" + (w - W * s) / 2 + "px," + (h - H * s) / 2 + "px) scale(" + s + ")";
  }

  function visible(el, top) {
    var opacity = 1;
    for (var p = el; p && p !== top.parentElement; p = p.parentElement) {
      var cs = getComputedStyle(p);
      if (cs.display === "none" || cs.visibility === "hidden") return false;
      opacity *= parseFloat(cs.opacity);
    }
    return opacity > 0.01;
  }

  // Visible elements with an id under a point or intersecting a rectangle (frame pixels), innermost first.
  function hits(q) {
    var box = root.getBoundingClientRect();
    var s = box.width / W;
    var r = q.rect ? q.rect : { x: q.point.x, y: q.point.y, w: 0, h: 0 };
    var x0 = box.left + r.x * s, y0 = box.top + r.y * s, x1 = x0 + r.w * s, y1 = y0 + r.h * s;
    var found = [];
    root.querySelectorAll("[id]").forEach(function (el) {
      if (LAYERS[el.id]) return;
      var b = el.getBoundingClientRect();
      if (b.width <= 0 && b.height <= 0) return;
      if (b.right < x0 || b.left > x1 || b.bottom < y0 || b.top > y1) return;
      if (!visible(el, root)) return;
      var depth = 0;
      for (var p = el; p && p !== root; p = p.parentNode) depth++;
      found.push({ id: el.id, depth: depth, area: b.width * b.height });
    });
    found.sort(function (a, b) { return b.depth - a.depth || a.area - b.area; });
    return found.map(function (f) { return f.id; });
  }

  window.addEventListener("message", function (ev) {
    var m = ev.data;
    if (ev.source !== window.parent || !m || typeof m.type !== "string" || !root) return;
    if (m.type === "sv:seek") seek(m.t);
    else if (m.type === "sv:query") {
      var ids = [];
      try { ids = hits(m); } catch (err) { errors.push("hits: " + err); }
      post({ type: "sv:hits", qid: m.qid, t: time, ids: ids });
    }
  });

  function start() {
    root = document.querySelector("[data-composition-id]") || document.getElementById("root");
    if (!root) {
      errors.push("no element with data-composition-id");
      post({ type: "sv:ready", width: W, height: H, duration: 0, errors: errors });
      return;
    }
    rootId = root.getAttribute("data-composition-id");
    W = parseFloat(root.getAttribute("data-width")) || W;
    H = parseFloat(root.getAttribute("data-height")) || H;
    duration = parseFloat(root.getAttribute("data-duration")) || 0;
    if (!(window.__timelines && window.__timelines[rootId]) && !root.hasAttribute("data-no-timeline")) {
      errors.push("no window.__timelines[\"" + rootId + "\"]");
    }
    fit();
    window.addEventListener("resize", fit);
    seek(0);
    var fonts = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
    fonts.then(function () {
      seek(time);
      requestAnimationFrame(function () {
        post({ type: "sv:ready", width: W, height: H, duration: duration, errors: errors });
      });
    });
  }

  if (document.readyState === "complete") start();
  else window.addEventListener("load", start);
})();
