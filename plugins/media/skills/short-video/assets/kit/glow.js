/*
 * Kit glow: additive glow sprites and point clouds, a stand-in for a bloom pass (the bloom addon is an ES
 * module and does not load from file://). Classic script for three.js 0.159.0 (global THREE).
 */
(function () {
  "use strict";
  var Kit = window.Kit = window.Kit || {};
  var cache = {};

  // A white radial falloff texture, size x size pixels, cached by size. The colour comes from the material.
  Kit.glowTexture = function (size) {
    size = size || 128;
    if (cache[size]) return cache[size];
    var cv = document.createElement("canvas");
    cv.id = "kit-glow-tex-" + size;
    cv.width = cv.height = size;
    var g = cv.getContext("2d"), r = size / 2;
    var gr = g.createRadialGradient(r, r, 0, r, r, r);
    gr.addColorStop(0, "rgba(255,255,255,1)");
    gr.addColorStop(0.18, "rgba(255,255,255,0.75)");
    gr.addColorStop(0.45, "rgba(255,255,255,0.22)");
    gr.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = gr;
    g.fillRect(0, 0, size, size);
    var tex = new THREE.CanvasTexture(cv);
    tex.colorSpace = THREE.SRGBColorSpace;
    cache[size] = tex;
    return tex;
  };

  // One additive sprite. opts: {color (default 0xffffff), size (world units, default 1), opacity (default 1),
  // position ([x, y, z])}. Fog is off so the glow keeps its colour at distance.
  Kit.glow = function (opts) {
    opts = opts || {};
    var s = new THREE.Sprite(new THREE.SpriteMaterial({
      map: Kit.glowTexture(), color: opts.color === undefined ? 0xffffff : opts.color,
      opacity: opts.opacity === undefined ? 1 : opts.opacity, transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending, fog: false
    }));
    s.scale.setScalar(opts.size || 1);
    if (opts.position) s.position.set(opts.position[0], opts.position[1], opts.position[2]);
    return s;
  };

  // Many glows of one colour as THREE.Points. positions: [[x, y, z], ...]. opts: {color, size, opacity}.
  Kit.glowPoints = function (positions, opts) {
    opts = opts || {};
    var flat = [];
    positions.forEach(function (p) { flat.push(p[0], p[1], p[2]); });
    var g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(flat, 3));
    return new THREE.Points(g, new THREE.PointsMaterial({
      map: Kit.glowTexture(), color: opts.color === undefined ? 0xffffff : opts.color, size: opts.size || 0.2,
      opacity: opts.opacity === undefined ? 1 : opts.opacity, transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending, sizeAttenuation: true, fog: false
    }));
  };

  // A cosine pulse between lo and hi with the given period (s) and phase (s), at scene time t.
  Kit.pulse = function (t, period, lo, hi, phase) {
    var u = 0.5 - 0.5 * Math.cos(2 * Math.PI * (t + (phase || 0)) / period);
    return lo + (hi - lo) * u;
  };
})();
