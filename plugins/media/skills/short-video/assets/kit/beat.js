/*
 * Kit beat: cut effects and kinetic words for a reel cut on a musical beat grid. Classic script for GSAP 3
 * (global gsap); no three.js. Each effect adds tweens to the page's paused timeline `tl` at a time `t` in
 * seconds, or returns an update(t) function for the page's clock tween, so every frame is a function of the
 * timeline time. Random values come from a seeded generator.
 *
 * Defaults: frame 1920x1080, 30 fps, 120 bpm, white flash, red, green and blue strips for the chromatic
 * slice, near-black wipe bars with white edges, white particles. Elements are absolutely positioned with
 * inline styles, so a page needs no CSS for them; colours and fonts of the words are the page's.
 * Arguments that take an element also take a CSS selector.
 */
(function () {
  "use strict";
  var Kit = window.Kit = window.Kit || {};
  var B = Kit.beat = {};

  function el(x) { return typeof x === "string" ? document.querySelector(x) : x; }
  function opt(o, k, d) { return o && o[k] !== undefined ? o[k] : d; }
  function between(r, lo, hi) { return lo + r() * (hi - lo); }

  // Seeded Park-Miller generator in [0, 1); the first draws of a small seed are near 0, so three are discarded.
  B.rand = function (seed) {
    var s = (Math.floor(seed) % 2147483647) || 1;
    if (s < 0) s += 2147483646;
    var r = function () { s = (s * 16807) % 2147483647; return s / 2147483647; };
    r(); r(); r();
    return r;
  };

  // The beat grid of a tempo: beat length 60 / bpm seconds, `perBar` beats to a bar, the first beat at `offset`.
  // at(n): time of beat n; bars(n): time of bar n; index(t): the beat at or before t; snap(t): nearest beat time;
  // list(t0, t1, every): beat times in [t0, t1), every `every` beats from the first beat at or after t0.
  B.grid = function (bpm, o) {
    var beat = 60 / (bpm || 120), off = opt(o, "offset", 0), per = opt(o, "perBar", 4);
    var g = { bpm: bpm || 120, beat: beat, bar: beat * per, offset: off, perBar: per };
    g.at = function (n) { return off + n * beat; };
    g.bars = function (n) { return off + n * beat * per; };
    g.index = function (t) { return Math.floor((t - off) / beat + 1e-9); };
    g.snap = function (t) { return off + Math.round((t - off) / beat) * beat; };
    g.list = function (t0, t1, every) {
      var out = [], step = every || 1, n = Math.ceil((t0 - off) / beat - 1e-9);
      for (var t = g.at(n); t < t1 - 1e-9; n += step, t = g.at(n)) out.push(+t.toFixed(6));
      return out;
    };
    return g;
  };

  // Drifting glow dots inside rectangular regions of `parent`; each wraps around its region and fades near the
  // edges. Returns update(t). Options: n (40), regions [{x, y, w, h}] (the frame), width, height (1920, 1080),
  // seed (1), colors (["#ffffff"]), size [min, max] px (2, 7), drift max horizontal px/s (15), rise [min, max]
  // px/s upward (8, 34), alpha [min, max] (0.25, 0.85), twinkle [min, max] Hz-ish (0.8, 3), fade px (40),
  // glow (3, the shadow radius in sizes).
  B.particles = function (parent, o) {
    parent = el(parent);
    var fw = opt(o, "width", 1920), fh = opt(o, "height", 1080);
    var n = opt(o, "n", 40), regions = opt(o, "regions", [{ x: 0, y: 0, w: fw, h: fh }]);
    var r = B.rand(opt(o, "seed", 1)), colors = opt(o, "colors", ["#ffffff"]);
    var size = opt(o, "size", [2, 7]), drift = opt(o, "drift", 15), rise = opt(o, "rise", [8, 34]);
    var alpha = opt(o, "alpha", [0.25, 0.85]), tw = opt(o, "twinkle", [0.8, 3]), fade = opt(o, "fade", 40);
    var glow = opt(o, "glow", 3), ps = [];
    for (var i = 0; i < n; i++) {
      var d = document.createElement("div"), sz = between(r, size[0], size[1]);
      var c = colors[Math.floor(r() * colors.length)];
      d.className = "kit-beat-p";
      d.style.cssText = "position:absolute;left:0;top:0;border-radius:50%;pointer-events:none;opacity:0;width:" +
        sz.toFixed(1) + "px;height:" + sz.toFixed(1) + "px;background:" + c + ";box-shadow:0 0 " +
        (sz * glow).toFixed(1) + "px " + c;
      parent.appendChild(d);
      ps.push({ el: d, reg: regions[i % regions.length], x0: r(), y0: r(), vx: (r() - 0.5) * 2 * drift,
                vy: -between(r, rise[0], rise[1]), ph: r() * 6.283, tw: between(r, tw[0], tw[1]),
                a: between(r, alpha[0], alpha[1]) });
    }
    var update = function (t) {
      ps.forEach(function (p) {
        var w = p.reg.w, h = p.reg.h;
        var x = (p.x0 * w + p.vx * t) % w; if (x < 0) x += w;
        var y = (p.y0 * h + p.vy * t) % h; if (y < 0) y += h;
        var edge = Math.max(0, Math.min(1, y / fade, (h - y) / fade, x / fade, (w - x) / fade));
        var k = 0.55 + 0.45 * Math.sin(p.ph + t * p.tw * 3.1);
        p.el.style.transform = "translate(" + (p.reg.x + x).toFixed(1) + "px," + (p.reg.y + y).toFixed(1) + "px)";
        p.el.style.opacity = (p.a * k * edge).toFixed(3);
      });
    };
    update.elements = ps.map(function (p) { return p.el; });
    return update;
  };

  // A flash on `target`, a full-frame layer whose colour the page sets (white when it has no background).
  // At t the layer jumps to `peak`, holds `hold` seconds, then decays to 0 over `decay`. With rise > 0 it ramps
  // up over the `rise` seconds before t instead. Options: peak (1), hold (one frame), decay (0.1), rise (0),
  // second (0.55: the opacity of the frame after the peak; null for none), fps (30), ease ("power2.out").
  B.flash = function (tl, target, t, o) {
    var e = el(target), f = 1 / opt(o, "fps", 30);
    var peak = opt(o, "peak", 1), hold = opt(o, "hold", f), decay = opt(o, "decay", 0.1);
    var rise = opt(o, "rise", 0), second = opt(o, "second", 0.55);
    if (!e.style.background && !getComputedStyle(e).backgroundImage.match(/gradient|url/) &&
        getComputedStyle(e).backgroundColor === "rgba(0, 0, 0, 0)") e.style.background = "#ffffff";
    if (rise > 0) tl.fromTo(e, { opacity: 0 }, { opacity: peak, duration: rise, ease: "none", immediateRender: false }, t - rise);
    else tl.set(e, { opacity: peak }, t);
    if (second !== null && hold > 0) tl.set(e, { opacity: peak * second }, t + hold);
    tl.to(e, { opacity: 0, duration: decay, ease: opt(o, "ease", "power2.out") }, t + hold + (second !== null && hold > 0 ? f : 0));
    return t + hold + decay;
  };

  // A chromatic slice around t: horizontal strips in `layer`, offset sideways by `offsets` (px) on consecutive
  // frames, centred on the frame of t; `target` (the footage element, optional) is jolted by `jolt` x offset and
  // given `filter` on the same frames. Options: seed (1), colors (red, green, blue at 0.3), offsets ([140, -90,
  // 50, -20]), spread (2.2: strip offset factor), heights [min, max] px (10, 80), gaps [min, max] px (20, 110),
  // density (0.55: share of strips shown on odd frames), height (1080), fps (30), target, jolt (0.1),
  // filter ("saturate(1.6) contrast(1.15)"). Returns the time the last frame ends.
  B.slice = function (tl, layer, t, o) {
    layer = el(layer);
    var r = B.rand(opt(o, "seed", 1)), f = 1 / opt(o, "fps", 30), fh = opt(o, "height", 1080);
    var cols = opt(o, "colors", ["rgba(255,40,60,0.3)", "rgba(40,255,120,0.3)", "rgba(60,120,255,0.3)"]);
    var offs = opt(o, "offsets", [140, -90, 50, -20]), spread = opt(o, "spread", 2.2);
    var hs = opt(o, "heights", [10, 80]), gs = opt(o, "gaps", [20, 110]), dens = opt(o, "density", 0.55);
    var target = o && o.target ? el(o.target) : null, jolt = opt(o, "jolt", 0.1);
    var filter = opt(o, "filter", "saturate(1.6) contrast(1.15)");
    var strips = [], y = 0;
    while (y < fh) {
      var h = Math.floor(between(r, hs[0], hs[1])), s = document.createElement("div");
      var c1 = cols[Math.floor(r() * cols.length)], c2 = cols[Math.floor(r() * cols.length)];
      s.className = "kit-beat-strip";
      s.style.cssText = "position:absolute;left:-12%;width:124%;opacity:0;mix-blend-mode:screen;pointer-events:none;" +
        "top:" + y + "px;height:" + h + "px;background:linear-gradient(90deg, transparent, " + c1 + " 20%, " + c2 +
        " 80%, transparent)";
      layer.appendChild(s);
      strips.push({ el: s, k: (r() - 0.5) * 2, on: r() < dens });
      y += h + Math.floor(between(r, gs[0], gs[1]));
    }
    var t0 = t - Math.floor(offs.length / 2) * f;
    offs.forEach(function (off, i) {
      strips.forEach(function (sp) {
        tl.set(sp.el, { x: off * sp.k * spread, opacity: sp.on || i % 2 === 0 ? Math.max(0, 1 - i * 0.2) : 0 }, t0 + i * f);
      });
      if (target) tl.set(target, { x: off * jolt, filter: filter }, t0 + i * f);
    });
    var end = t0 + offs.length * f;
    strips.forEach(function (sp) { tl.set(sp.el, { opacity: 0, x: 0 }, end); });
    if (target) tl.set(target, { x: 0, filter: "none" }, end);
    return end;
  };

  // A slice wipe across the cut at t: `bars` skewed bars sweep across `layer` so that they cover the frame centre
  // at t, then hide. Options: bars (4), width px (520), skew deg (-18), fill ("#0b0b0b"), edge
  // ("rgba(255,255,255,0.9)"), edges (an [left, right] pair of colours, overrides edge), edgeWidth px (6),
  // duration (0.26), stagger (0.025), lead (0.16: seconds before t the first bar starts), dir (1: left to right,
  // -1: right to left), frameWidth (1920), height (1280), ease ("power2.inOut"). Returns the bar elements.
  B.wipe = function (tl, layer, t, o) {
    layer = el(layer);
    var n = opt(o, "bars", 4), bw = opt(o, "width", 520), fw = opt(o, "frameWidth", 1920);
    var dur = opt(o, "duration", 0.26), st = opt(o, "stagger", 0.025), lead = opt(o, "lead", 0.16);
    var dir = opt(o, "dir", 1), ew = opt(o, "edgeWidth", 6), fill = opt(o, "fill", "#0b0b0b");
    var edges = opt(o, "edges", [opt(o, "edge", "rgba(255,255,255,0.9)"), opt(o, "edge", "rgba(255,255,255,0.9)")]);
    var x0 = -bw - 380, x1 = fw + 480, out = [];
    for (var j = 0; j < n; j++) {
      var b = document.createElement("div");
      b.className = "kit-beat-bar";
      b.style.cssText = "position:absolute;left:0;top:-100px;opacity:0;pointer-events:none;width:" + bw + "px;height:" +
        opt(o, "height", 1280) + "px;background:linear-gradient(90deg, " + edges[0] + " 0 " + ew + "px, " + fill + " " +
        ew + "px calc(100% - " + ew + "px), " + edges[1] + " calc(100% - " + ew + "px))";
      layer.appendChild(b);
      var a = dir > 0 ? x0 + j * 40 : x1 - j * 40, z = dir > 0 ? x1 : x0;
      tl.fromTo(b, { x: a, skewX: opt(o, "skew", -18), opacity: 1 },
                { x: z, opacity: 1, duration: dur, ease: opt(o, "ease", "power2.inOut"), immediateRender: false },
                t - lead + j * st);
      tl.set(b, { opacity: 0 }, t - lead + j * st + dur);
      out.push(b);
    }
    return out;
  };

  // A kinetic word stamped onto the beat t: `target` scales down from `from` to 1 and lands at t, shakes once,
  // grows slowly to `grow` while it holds, and leaves with a blur so it is gone at `until`. At t <= dur the word
  // is on screen from frame 0 (the opening cut). It has opacity 0 before it enters and after `until`.
  // Options: until (t + 2), from (2), dur (0.18), ease ("power4.in"), shake px (6), grow (1.08), exit (0.22),
  // exitScale (1.2), blur px (12), origin ("50% 50%"), keep (false: true holds the word to `until` with no exit).
  // Returns `until`.
  B.stamp = function (tl, target, t, o) {
    var e = el(target), until = opt(o, "until", t + 2), dur = opt(o, "dur", 0.18), sh = opt(o, "shake", 6);
    var exit = opt(o, "exit", 0.22), org = opt(o, "origin", "50% 50%");
    if (t - dur < 0) {
      tl.fromTo(e, { opacity: 0.85, scale: 1.25, filter: "blur(0px)", transformOrigin: org },
                { opacity: 1, scale: 1, duration: Math.max(0.08, Math.min(dur, 0.12)), ease: "power3.out" }, 0);
    } else {
      tl.fromTo(e, { opacity: 0, scale: opt(o, "from", 2), filter: "blur(0px)", transformOrigin: org },
                { opacity: 1, scale: 1, duration: dur, ease: opt(o, "ease", "power4.in") }, t - dur);
    }
    if (sh) tl.fromTo(e, { x: 0, y: 0 }, { x: sh, y: -sh, duration: 0.05, yoyo: true, repeat: 1, immediateRender: false }, t + 0.06);
    var keep = opt(o, "keep", false);
    tl.to(e, { scale: opt(o, "grow", 1.08), duration: Math.max(0.01, until - (keep ? 0 : exit) - t - 0.18), ease: "none" }, t + 0.18);
    if (keep) return until;
    tl.to(e, { opacity: 0, scale: opt(o, "exitScale", 1.2), filter: "blur(" + opt(o, "blur", 12) + "px)",
               duration: exit, ease: "power2.in" }, until - exit);
    tl.set(e, { opacity: 0 }, until);
    return until;
  };

  // A caption whose lines rise out of line masks at t and leave upward so the caption is gone at `until`.
  // `target` is the caption; its lines are the elements matching `lines` (".ln") inside it, each the only child
  // of an `overflow: hidden` mask. The caption has opacity 0 outside [t - 0.02, until], since a text shadow
  // bleeds out of a mask box. Options: until (t + 2), lines (".ln"), dur (0.5), stagger (0.12), ease
  // ("power4.out"), rotate deg (3), exit (0.3), exitStagger (0.05), drift px (0: a slow sideways drift while it
  // holds), keep (false: stay on screen after until). Returns `until`.
  B.rise = function (tl, target, t, o) {
    var e = el(target), lines = e.querySelectorAll(opt(o, "lines", ".ln"));
    var until = opt(o, "until", t + 2), exit = opt(o, "exit", 0.3), est = opt(o, "exitStagger", 0.05);
    var keep = opt(o, "keep", false), drift = opt(o, "drift", 0);
    var out = until - exit - est * Math.max(0, lines.length - 1);
    tl.set(e, { opacity: 0 }, 0);
    tl.set(e, { opacity: 1 }, Math.max(0, t - 0.02));
    lines.forEach(function (ln, j) {
      tl.fromTo(ln, { yPercent: 115, rotation: opt(o, "rotate", 3) },
                { yPercent: 0, rotation: 0, duration: opt(o, "dur", 0.5), ease: opt(o, "ease", "power4.out") },
                t + j * opt(o, "stagger", 0.12));
      if (!keep) tl.to(ln, { yPercent: -115, duration: exit, ease: "power3.in" }, out + j * est);
    });
    if (drift) tl.fromTo(e, { x: 0 }, { x: drift, duration: until - t, ease: "sine.inOut", immediateRender: false }, t);
    if (!keep) tl.set(e, { opacity: 0 }, until);
    return until;
  };
})();
