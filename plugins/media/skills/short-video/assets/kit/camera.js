/*
 * Kit camera: an orbit pose (target, distance, pitch, yaw), keyframe paths over scene time, and a
 * least-squares fit that moves chosen pose fields until world points land on chosen frame positions.
 * Classic script for three.js 0.159.0 (global THREE). Every function of time takes t as an argument.
 */
(function () {
  "use strict";
  var Kit = window.Kit = window.Kit || {};
  var D2R = Math.PI / 180;

  // Eases on u in [0, 1].
  Kit.ease = {
    linear: function (u) { return u; },
    sineIn: function (u) { return 1 - Math.cos(u * Math.PI / 2); },
    sineOut: function (u) { return Math.sin(u * Math.PI / 2); },
    sineInOut: function (u) { return 0.5 - 0.5 * Math.cos(u * Math.PI); },
    quadInOut: function (u) { return u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2; },
    cubicIn: function (u) { return u * u * u; },
    cubicOut: function (u) { return 1 - Math.pow(1 - u, 3); },
    cubicInOut: function (u) { return u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2; },
    expoOut: function (u) { return u >= 1 ? 1 : 1 - Math.pow(2, -10 * u); }
  };

  function easeFn(e) {
    if (typeof e === "function") return e;
    var f = Kit.ease[e || "linear"];
    if (!f) throw new Error("Kit.ease: unknown ease " + e);
    return f;
  }

  // Place `camera` on an orbit around (tx, ty, tz): distance d, pitch degrees above the horizon (90 looks
  // straight down), yaw degrees of the viewing heading (0 looks toward -z, 90 toward +x). Sets fov when given.
  function pose(camera, s) {
    var p = (s.pitch === undefined ? 45 : s.pitch) * D2R, y = (s.yaw || 0) * D2R, d = s.d === undefined ? 10 : s.d;
    var tx = s.tx || 0, ty = s.ty || 0, tz = s.tz || 0;
    var hx = Math.sin(y), hz = -Math.cos(y), cp = Math.cos(p), sp = Math.sin(p);
    camera.position.set(tx - hx * cp * d, ty + sp * d, tz - hz * cp * d);
    camera.up.set(hx * sp, cp, hz * sp);
    camera.lookAt(tx, ty, tz);
    if (s.fov !== undefined && camera.isPerspectiveCamera && camera.fov !== s.fov) {
      camera.fov = s.fov;
      camera.updateProjectionMatrix();
    }
    camera.updateMatrixWorld(true);
    return camera;
  }

  // keys: [{t, tx, ty, tz, d, pitch, yaw, fov, ease, ...}] sorted by t. Every numeric field except t is
  // interpolated; a field a key omits keeps the previous key's value. The ease of a key shapes the segment
  // that ends at it (default "linear"). Two keys with the same t make a cut. Before the first key and after
  // the last, the state holds.
  function path(keys) {
    if (!keys || !keys.length) throw new Error("Kit.camera.path: no keys");
    var full = [], prev = {};
    keys.forEach(function (k, i) {
      if (i && k.t < keys[i - 1].t) throw new Error("Kit.camera.path: keys out of order at " + i);
      var f = {};
      Object.keys(prev).forEach(function (n) { f[n] = prev[n]; });
      Object.keys(k).forEach(function (n) { if (n !== "ease") f[n] = k[n]; });
      f.ease = easeFn(k.ease);
      full.push(f);
      prev = f;
    });
    function fields(a, b) {
      var out = {};
      Object.keys(b).forEach(function (n) { if (n !== "ease" && n !== "t" && typeof b[n] === "number") out[n] = b[n]; });
      return { a: a, b: b, out: out };
    }
    function at(t) {
      if (t <= full[0].t) return fields(full[0], full[0]).out;
      var last = full[full.length - 1];
      if (t >= last.t) return fields(last, last).out;
      var i = 1;
      while (i < full.length - 1 && full[i].t <= t) i++;
      var a = full[i - 1], b = full[i];
      var u = b.t > a.t ? b.ease((t - a.t) / (b.t - a.t)) : 1;
      var f = fields(a, b), out = {};
      Object.keys(f.out).forEach(function (n) {
        var va = typeof a[n] === "number" ? a[n] : b[n];
        out[n] = va + (b[n] - va) * u;
      });
      return out;
    }
    return {
      keys: full,
      at: at,
      apply: function (camera, t) { return pose(camera, at(t)); }
    };
  }

  // Gauss-Newton fit: change the fields `params` (e.g. ["tx", "tz", "d"]) of pose state `state` so each goal
  // [x, y, z, fx, fy] (world point, frame fractions from the top left) projects onto (fx, fy) through a copy
  // of `camera`. Returns a new state; `camera` is not moved.
  function fit(camera, state, params, goals, iterations) {
    var c = Object.assign({}, state), cam = camera.clone(), v = new THREE.Vector3();
    function proj(s) {
      pose(cam, s);
      var out = [];
      goals.forEach(function (g) { v.set(g[0], g[1], g[2]).project(cam); out.push((v.x + 1) / 2, (1 - v.y) / 2); });
      return out;
    }
    var n = params.length;
    for (var it = 0; it < (iterations || 30); it++) {
      var q = proj(c), res = q.map(function (val, i) { return val - goals[i >> 1][i % 2 ? 4 : 3]; });
      var J = params.map(function (k) {
        var h = k === "d" ? 1e-3 * Math.max(1e-3, Math.abs(c[k] || 0)) : 1e-3, save = c[k] || 0;
        c[k] = save + h;
        var q2 = proj(c);
        c[k] = save;
        return q2.map(function (val, i) { return (val - q[i]) / h; });
      });
      var A = [], b = [];
      for (var a = 0; a < n; a++) {
        A.push([]);
        var s = 0;
        for (var i = 0; i < res.length; i++) s += J[a][i] * res[i];
        b.push(-s);
        for (var bb = 0; bb < n; bb++) {
          var s2 = 0;
          for (var i2 = 0; i2 < res.length; i2++) s2 += J[a][i2] * J[bb][i2];
          A[a].push(s2 + (a === bb ? 1e-9 : 0));
        }
      }
      for (var p = 0; p < n; p++) {
        for (var r = p + 1; r < n; r++) {
          var f = A[r][p] / A[p][p];
          for (var cc = p; cc < n; cc++) A[r][cc] -= f * A[p][cc];
          b[r] -= f * b[p];
        }
      }
      var dx = new Array(n);
      for (var r3 = n - 1; r3 >= 0; r3--) {
        var s3 = b[r3];
        for (var c3 = r3 + 1; c3 < n; c3++) s3 -= A[r3][c3] * dx[c3];
        dx[r3] = s3 / A[r3][r3];
      }
      params.forEach(function (k, j) { c[k] = (c[k] || 0) + dx[j]; });
    }
    return c;
  }

  Kit.camera = { pose: pose, path: path, fit: fit };
})();
