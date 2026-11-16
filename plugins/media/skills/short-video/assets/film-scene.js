/*
 * Film scene script: `html` inlines it into each scene or world page of film.html, which plays the page in an
 * iframe. The film player owns time; this script only seeks, the way HyperFrames does: the GSAP timeline
 * window.__timelines[<root id>], the `hf-seek` event (anime.js, Motion, three.js), and each <video data-start>.
 *
 * Messages from the player:  {type: "film:seek", seq, t, still}    page time in seconds; `still` when paused
 *
 * A paused seek draws twice, first WARM s later: on a hardware GPU the first three.js draw that links new shader
 * programs can come out black, and a second draw of the same state is correct. GSAP calls no onUpdate for a seek to
 * the time it is at, so the first draw is at another time.
 * Messages to the player:    {type: "film:ready", k, duration, errors}
 *                            {type: "film:seeked", k, seq, t}      after the seeked frame is drawn
 * `window.__FILM_INDEX` (set before this script) is the page's segment index k.
 */
(function () {
  "use strict";

  var errors = [];
  var time = 0;
  var root = null, rootId = null, W = 1920, H = 1080, duration = 0;
  var k = window.__FILM_INDEX;
  var WARM = 0.005;

  window.addEventListener("error", function (e) { errors.push(String(e.message || e)); });

  function post(msg) { msg.k = k; window.parent.postMessage(msg, "*"); }

  function seek(t, still) {
    time = Math.max(0, Number(t) || 0);
    if (still) draw(time + WARM);
    draw(time);
    document.querySelectorAll("video[data-start]").forEach(function (v) {
      var local = time - (parseFloat(v.getAttribute("data-start")) || 0);
      if (local >= 0 && isFinite(local)) { try { v.pause(); v.currentTime = local; } catch (err) { /* not loaded */ } }
    });
  }

  function draw(at) {
    var tl = window.__timelines && window.__timelines[rootId];
    if (tl && typeof tl.seek === "function") {
      try { tl.pause(); tl.seek(at, false); } catch (err) { errors.push("seek: " + err); }
    }
    try {
      window.dispatchEvent(new CustomEvent("hf-seek", { detail: { time: at, waitUntil: function () {} } }));
    } catch (err) { errors.push("hf-seek: " + err); }
  }

  // The frame scaled to fit the iframe, centred.
  function fit() {
    var w = window.innerWidth, h = window.innerHeight;
    var s = Math.min(w / W, h / H);
    document.documentElement.style.overflow = "hidden";
    document.body.style.margin = "0";
    document.body.style.overflow = "hidden";
    document.body.style.background = "#000";
    root.style.transformOrigin = "0 0";
    root.style.transform = "translate(" + (w - W * s) / 2 + "px," + (h - H * s) / 2 + "px) scale(" + s + ")";
  }

  window.addEventListener("message", function (ev) {
    var m = ev.data;
    if (ev.source !== window.parent || !m || m.type !== "film:seek" || !root) return;
    seek(m.t, m.still);
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { post({ type: "film:seeked", seq: m.seq, t: time }); });
    });
  });

  function start() {
    root = document.querySelector("[data-composition-id]") || document.getElementById("root");
    if (!root) {
      errors.push("no element with data-composition-id");
      post({ type: "film:ready", duration: 0, errors: errors });
      return;
    }
    rootId = root.getAttribute("data-composition-id");
    W = parseFloat(root.getAttribute("data-width")) || W;
    H = parseFloat(root.getAttribute("data-height")) || H;
    duration = parseFloat(root.getAttribute("data-duration")) || 0;
    fit();
    window.addEventListener("resize", fit);
    seek(0);
    var fonts = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
    fonts.then(function () {
      seek(time, true);
      requestAnimationFrame(function () { post({ type: "film:ready", duration: duration, errors: errors }); });
    });
  }

  if (document.readyState === "complete") start();
  else window.addEventListener("load", start);
})();
