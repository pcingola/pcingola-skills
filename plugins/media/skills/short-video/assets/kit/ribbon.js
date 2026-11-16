/*
 * Kit ribbon: flat route ribbons on the ground plane (x, z) that draw on by arc length, with rounded corners,
 * soft edges and fog, and a sampler that moves an object along the same path.
 * Classic script for three.js 0.159.0 (global THREE).
 */
(function () {
  "use strict";
  var Kit = window.Kit = window.Kit || {};

  function lerp(a, b, u) { return a + (b - a) * u; }

  // Replace each inner corner of polyline pts ([[x, z], ...]) with a quadratic arc of the given radius
  // (capped at half of each adjacent segment), and resample straight runs every `step` units.
  Kit.roundCorners = function (pts, radius, step) {
    step = step || 0.05;
    var out = [pts[0].slice()];
    function seg(a, b) {
      var l = Math.hypot(b[0] - a[0], b[1] - a[1]), n = Math.max(1, Math.ceil(l / step));
      for (var i = 1; i <= n; i++) out.push([lerp(a[0], b[0], i / n), lerp(a[1], b[1], i / n)]);
    }
    var cur = pts[0];
    for (var i = 1; i < pts.length - 1; i++) {
      var a = pts[i - 1], v = pts[i], b = pts[i + 1];
      var la = Math.hypot(v[0] - a[0], v[1] - a[1]), lb = Math.hypot(b[0] - v[0], b[1] - v[1]);
      var r = Math.min(radius, la / 2, lb / 2);
      var p0 = [v[0] + (a[0] - v[0]) / la * r, v[1] + (a[1] - v[1]) / la * r];
      var p1 = [v[0] + (b[0] - v[0]) / lb * r, v[1] + (b[1] - v[1]) / lb * r];
      seg(cur, p0);
      for (var k = 1; k <= 8; k++) {
        var u = k / 8, w0 = (1 - u) * (1 - u), w1 = 2 * u * (1 - u), w2 = u * u;
        out.push([w0 * p0[0] + w1 * v[0] + w2 * p1[0], w0 * p0[1] + w1 * v[1] + w2 * p1[1]]);
      }
      cur = p1;
    }
    seg(cur, pts[pts.length - 1]);
    return out;
  };

  // Arc-length sampler of polyline pts ([[x, z], ...]). at(s) returns {x, z, dx, dz}: the point at arc length s
  // (clamped) and the direction of its segment. length is the total arc length.
  Kit.pathSampler = function (pts) {
    var cum = [0];
    for (var i = 1; i < pts.length; i++) cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
    var total = cum[cum.length - 1];
    return {
      length: total,
      at: function (s) {
        s = Math.max(0, Math.min(total, s));
        var lo = 0, hi = cum.length - 1;
        while (hi - lo > 1) { var m = (lo + hi) >> 1; if (cum[m] < s) lo = m; else hi = m; }
        var u = Math.max(0, Math.min(1, (s - cum[lo]) / Math.max(1e-9, cum[hi] - cum[lo])));
        return { x: lerp(pts[lo][0], pts[hi][0], u), z: lerp(pts[lo][1], pts[hi][1], u),
                 dx: pts[hi][0] - pts[lo][0], dz: pts[hi][1] - pts[lo][1] };
      }
    };
  };

  var VS = [
    "attribute float aS; attribute float aSide; varying float vS; varying float vSide;",
    "#include <fog_pars_vertex>",
    "void main(){ vS = aS; vSide = aSide; vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);",
    "  gl_Position = projectionMatrix * mvPosition;",
    "#include <fog_vertex>",
    "}"].join("\n");
  var FS = [
    "uniform vec3 uColor; uniform float uOpacity; uniform float uHead; uniform float uTail; uniform float uFeather;",
    "varying float vS; varying float vSide;",
    "#include <fog_pars_fragment>",
    "void main(){ if (vS > uHead || vS < uTail) discard;",
    "  float a = uOpacity * (1.0 - smoothstep(1.0 - uFeather, 1.0, abs(vSide)));",
    "  gl_FragColor = vec4(uColor, a);",
    "  #include <colorspace_fragment>",
    "  #include <fog_fragment>",
    "}"].join("\n");

  // The triangle strip under polyline pts at height y: two vertices per point, attribute aS (arc length) and
  // aSide (-1 or 1). geometry.userData.length is the arc length.
  Kit.ribbonGeometry = function (pts, width, y) {
    var pos = [], idx = [], arc = [], side = [], s = 0;
    for (var i = 0; i < pts.length; i++) {
      var a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)];
      var tx = b[0] - a[0], tz = b[1] - a[1], l = Math.hypot(tx, tz) || 1, nx = -tz / l, nz = tx / l;
      if (i > 0) s += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
      pos.push(pts[i][0] + nx * width / 2, y, pts[i][1] + nz * width / 2, pts[i][0] - nx * width / 2, y, pts[i][1] - nz * width / 2);
      arc.push(s, s);
      side.push(1, -1);
      if (i > 0) { var k = (i - 1) * 2; idx.push(k, k + 2, k + 1, k + 1, k + 2, k + 3); }
    }
    var g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute("aS", new THREE.Float32BufferAttribute(arc, 1));
    g.setAttribute("aSide", new THREE.Float32BufferAttribute(side, 1));
    g.setIndex(idx);
    g.userData.length = s;
    return g;
  };

  // A ribbon mesh along pts ([[x, z], ...]). opts: {width (0.1), y (0.01), color (0xffffff), opacity (1),
  // feather (soft edge as a fraction of the half width, 0.45), order (draw order and polygon offset, 1),
  // progress (0..1, default 1)}. mesh.userData: {length, sampler}. Call Kit.ribbonProgress to draw it on.
  Kit.ribbon = function (pts, opts) {
    opts = opts || {};
    var order = opts.order === undefined ? 1 : opts.order;
    var g = Kit.ribbonGeometry(pts, opts.width || 0.1, opts.y === undefined ? 0.01 : opts.y);
    var mat = new THREE.ShaderMaterial({
      uniforms: THREE.UniformsUtils.merge([THREE.UniformsLib.fog, {
        uColor: { value: new THREE.Color(opts.color === undefined ? 0xffffff : opts.color) },
        uOpacity: { value: opts.opacity === undefined ? 1 : opts.opacity },
        uHead: { value: g.userData.length }, uTail: { value: -1 },
        uFeather: { value: opts.feather === undefined ? 0.45 : opts.feather }
      }]),
      vertexShader: VS, fragmentShader: FS, transparent: true, depthWrite: false, fog: true,
      side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -order, polygonOffsetUnits: -2 * order
    });
    var mesh = new THREE.Mesh(g, mat);
    mesh.renderOrder = order;
    mesh.frustumCulled = false;
    mesh.userData.length = g.userData.length;
    mesh.userData.sampler = Kit.pathSampler(pts);
    Kit.ribbonProgress(mesh, opts.progress === undefined ? 1 : opts.progress);
    return mesh;
  };

  // Show the part of the ribbon between arc fractions tail and head (0..1). tail defaults to 0.
  Kit.ribbonProgress = function (mesh, head, tail) {
    var L = mesh.userData.length, u = mesh.material.uniforms;
    u.uHead.value = Math.max(0, Math.min(1, head)) * L + (head >= 1 ? 1e-4 : 0);
    u.uTail.value = tail ? Math.max(0, Math.min(1, tail)) * L : -1;
    return mesh;
  };
})();
