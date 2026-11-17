/*
 * Kit pipeline: stations (a platform with a placeholder object that lights up), glowing connectors that draw on
 * between them, and particle flows along a curve, for process lines and hub-and-nodes diagrams.
 * Classic script for three.js 0.159.0 (global THREE); load kit/glow.js first.
 *
 * Conventions: positions are [x, y, z] with y up; the line layout runs along +x on the ground plane. Every
 * function of time takes the scene time t, so a seek to any t draws the same frame. A level is 0 (unlit) to 1
 * (lit), with values above 1 for a flash. No colour is set here beyond neutral defaults: pass the palette in.
 */
(function () {
  "use strict";
  var Kit = window.Kit = window.Kit || {};
  var P = Kit.pipeline = {};

  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function opt(o, k, d) { return o && o[k] !== undefined ? o[k] : d; }
  function smooth(u) { u = clamp(u, 0, 1); return u * u * (3 - 2 * u); }
  P.clamp = clamp;
  P.smooth = smooth;
  // 0 before a, 1 after b, linear between.
  P.lin = function (t, a, b) { return clamp((t - a) / (b - a), 0, 1); };
  // A Gaussian bump centred on c with half-width w (1 at c).
  P.bump = function (t, c, w) { var x = (t - c) / w; return Math.exp(-x * x); };
  // A seeded generator in [0, 1) (Park-Miller).
  P.rng = function (seed) { var s = seed || 1; return function () { s = (s * 16807) % 2147483647; return s / 2147483647; }; };

  // n positions on a straight line along +x, centred on `center` ([x, y, z], default origin), `spacing` apart
  // (default 6).
  P.line = function (n, opts) {
    var sp = opt(opts, "spacing", 6), c = opt(opts, "center", [0, 0, 0]), out = [];
    for (var i = 0; i < n; i++) out.push([c[0] + (i - (n - 1) / 2) * sp, c[1], c[2]]);
    return out;
  };

  // n positions on a circular arc of `radius` (default 7) around `center`, on the ground plane. The arc spans
  // `spread` degrees centred on `facing` degrees (default 0: toward -z, away from a camera at +z), with the end
  // nodes on the arc's ends. A spread of 360 (the default) spaces them evenly around the circle, the first at
  // `facing`.
  P.hub = function (n, opts) {
    var r = opt(opts, "radius", 7), c = opt(opts, "center", [0, 0, 0]);
    var spread = opt(opts, "spread", 360), facing = opt(opts, "facing", 0), out = [];
    for (var i = 0; i < n; i++) {
      var deg = spread >= 360 ? facing + i * 360 / n : facing - spread / 2 + (n === 1 ? 0.5 : i / (n - 1)) * spread;
      var a = deg * Math.PI / 180;
      out.push([c[0] + r * Math.sin(a), c[1], c[2] - r * Math.cos(a)]);
    }
    return out;
  };

  // The level of a station switched on at tOn: `base` (default 0.2) before, rising to 1 over `rise` seconds
  // (default 0.5, smoothstep) from tOn - 0.1, plus a flash of height `flash` (default 0.6) and half-width
  // `flashWidth` (default 0.25) s at tOn + 0.3. A tOn of null or undefined keeps the base level.
  P.level = function (t, tOn, opts) {
    var base = opt(opts, "base", 0.2);
    if (tOn === null || tOn === undefined) return base;
    var rise = opt(opts, "rise", 0.5), flash = opt(opts, "flash", 0.6), fw = opt(opts, "flashWidth", 0.25);
    return base + (1 - base) * smooth((t - tOn + 0.1) / rise) + flash * P.bump(t, tOn + 0.3, fw);
  };

  function glowMat(color, opacity) {
    return new THREE.MeshBasicMaterial({ map: Kit.glowTexture(), color: color, transparent: true, opacity: opacity,
      blending: THREE.AdditiveBlending, depthWrite: false });
  }

  // The placeholder object of a station kind, standing on y = 0, about `s` units wide. Kinds: "box", "cylinder",
  // "ring" (a standing torus on a post), "stack" (four slabs with seams). An unknown kind gives a box.
  function shape(kind, s, mat, postMat) {
    var g = new THREE.Group(), m;
    if (kind === "cylinder") {
      m = new THREE.Mesh(new THREE.CylinderGeometry(0.5 * s, 0.5 * s, 1.3 * s, 48), mat);
      m.position.y = 0.65 * s; g.add(m);
    } else if (kind === "ring") {
      m = new THREE.Mesh(new THREE.TorusGeometry(0.55 * s, 0.13 * s, 20, 64), mat);
      m.position.y = 1.15 * s; g.add(m);
      var post = new THREE.Mesh(new THREE.CylinderGeometry(0.05 * s, 0.08 * s, 0.5 * s, 12), postMat);
      post.position.y = 0.25 * s; g.add(post);
    } else if (kind === "stack") {
      for (var k = 0; k < 4; k++) {
        m = new THREE.Mesh(new THREE.BoxGeometry(1.0 * s, 0.24 * s, 0.75 * s), mat);
        m.position.y = (0.12 + k * 0.28) * s;              // a 0.04 s seam between slabs
        m.rotation.y = (k % 2 ? 1 : -1) * 0.08 * k;
        g.add(m);
      }
    } else {
      m = new THREE.Mesh(new THREE.BoxGeometry(0.95 * s, 0.95 * s, 0.95 * s), mat);
      m.position.y = 0.475 * s; g.add(m);
    }
    g.traverse(function (o) { if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; } });
    return g;
  }

  // A station: a round platform, a rim ring and a floor pool in the accent colour, a placeholder object
  // (`obj`, a group the page may scale or turn), a halo glow and a point light. opts: {kind ("box"), color
  // (accent, 0xffffff), body (object colour, 0x3a4256), base (platform colour, 0x161b28), size (1), position
  // ([0, 0, 0]), light (peak point-light intensity, 12; 0 for none)}. Returns {group, obj, mat, set(level)}:
  // set lights the rim, pool, halo, emissive object and light in proportion to the level.
  P.station = function (opts) {
    var s = opt(opts, "size", 1), color = new THREE.Color(opt(opts, "color", 0xffffff));
    var group = new THREE.Group(), pos = opt(opts, "position", [0, 0, 0]);
    group.position.set(pos[0], pos[1], pos[2]);
    var plat = new THREE.Mesh(new THREE.CylinderGeometry(1.25 * s, 1.35 * s, 0.22 * s, 64),
      new THREE.MeshStandardMaterial({ color: opt(opts, "base", 0x161b28), roughness: 0.35, metalness: 0.6 }));
    plat.position.y = 0.11 * s; plat.castShadow = true; plat.receiveShadow = true; group.add(plat);
    var rimMat = new THREE.MeshBasicMaterial({ color: color, transparent: true, opacity: 0.3, depthWrite: false });
    var rim = new THREE.Mesh(new THREE.TorusGeometry(1.27 * s, 0.03 * s, 8, 96).rotateX(Math.PI / 2), rimMat);
    rim.position.y = 0.23 * s; group.add(rim);
    var pool = new THREE.Mesh(new THREE.PlaneGeometry(5 * s, 5 * s).rotateX(-Math.PI / 2), glowMat(color, 0));
    pool.position.y = 0.03; pool.renderOrder = 1; group.add(pool);
    var mat = new THREE.MeshStandardMaterial({ color: opt(opts, "body", 0x3a4256), roughness: 0.4, metalness: 0.3,
      emissive: color, emissiveIntensity: 0 });
    var postMat = new THREE.MeshStandardMaterial({ color: opt(opts, "base", 0x161b28), roughness: 0.4, metalness: 0.6 });
    var obj = shape(opt(opts, "kind", "box"), s, mat, postMat);
    obj.position.y = 0.22 * s; group.add(obj);
    var halo = Kit.glow({ color: color, size: 4 * s, opacity: 0, position: [0, 1.1 * s, 0] });
    halo.material.depthTest = false; halo.renderOrder = 3; group.add(halo);
    var peak = opt(opts, "light", 12), light = null;
    if (peak > 0) { light = new THREE.PointLight(color, 0, 8 * s, 1.5); light.position.set(0, 2.6 * s, 1.2 * s); group.add(light); }
    return {
      group: group, obj: obj, mat: mat, rim: rim, pool: pool, halo: halo, light: light,
      set: function (level) {
        var l = Math.max(0, level), u = Math.min(1, l);
        rimMat.opacity = Math.min(1, 0.2 + 0.8 * u);
        pool.material.opacity = 0.45 * Math.min(1.5, l);
        halo.material.opacity = 0.12 * u + 0.35 * Math.max(0, l - 1);
        mat.emissiveIntensity = 0.05 + 0.75 * Math.min(1.6, l);
        if (light) light.intensity = peak * Math.min(1.6, l);
      }
    };
  };

  // A curve from a to b ([x, y, z]) that rises `arc` units (default 0) at its middle; `lift` raises both ends
  // (default 0). With `via` ([[x, y, z], ...]) it is a Catmull-Rom curve through a, the via points and b.
  P.curve = function (a, b, opts) {
    var lift = opt(opts, "lift", 0), arc = opt(opts, "arc", 0), via = opt(opts, "via", null);
    var A = new THREE.Vector3(a[0], a[1] + lift, a[2]), B = new THREE.Vector3(b[0], b[1] + lift, b[2]);
    if (via) {
      var pts = [A].concat(via.map(function (p) { return new THREE.Vector3(p[0], p[1], p[2]); }), [B]);
      return new THREE.CatmullRomCurve3(pts);
    }
    var M = A.clone().add(B).multiplyScalar(0.5); M.y += 2 * arc;   // a quadratic's middle is half its control
    return new THREE.QuadraticBezierCurve3(A, M, B);
  };

  // A glowing tube along a curve: a thin core and a wide additive halo. opts: {color (0xffffff), radius (0.04),
  // halo (halo radius, 0.16; 0 for none), opacity (0.85), segments (120), solid (false: additive; true: normal
  // blending, for a light ground where additive light vanishes)}. Returns {group, curve,
  // progress(head, tail, gain)}: shows the part between the fractions tail (default 0) and head of the curve
  // length, scaled in opacity by gain (default 1).
  P.connector = function (curve, opts) {
    var color = opt(opts, "color", 0xffffff), n = opt(opts, "segments", 120), op = opt(opts, "opacity", 0.85);
    var blending = opt(opts, "solid", false) ? THREE.NormalBlending : THREE.AdditiveBlending;
    var group = new THREE.Group(), tubes = [];
    function add(radius, opacity) {
      var geo = new THREE.TubeGeometry(curve, n, radius, 10, false);
      var m = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: color, transparent: true, opacity: opacity,
        blending: blending, depthWrite: false }));
      m.frustumCulled = false; group.add(m);
      tubes.push({ mesh: m, base: opacity, per: geo.index.count / n });
    }
    add(opt(opts, "radius", 0.04), op);
    var hr = opt(opts, "halo", 0.16);
    if (hr > 0) add(hr, op * 0.22);
    var c = {
      group: group, curve: curve,
      progress: function (head, tail, gain) {
        head = clamp(head, 0, 1); tail = clamp(tail || 0, 0, head); gain = gain === undefined ? 1 : gain;
        tubes.forEach(function (tb) {
          var s0 = Math.floor(tail * n), s1 = Math.ceil(head * n);
          tb.mesh.geometry.setDrawRange(s0 * tb.per, Math.max(0, s1 - s0) * tb.per);
          tb.mesh.material.opacity = tb.base * gain;
          tb.mesh.visible = head > 0 && gain > 0;
        });
      }
    };
    c.progress(0);
    return c;
  };

  // Particles streaming along a curve: `count` (default 60) glow points spaced evenly in curve fraction, moving
  // at `speed` curve lengths per second (default 0.5), jittered by up to `spread` units (default 0.08, seeded by
  // `seed`), size `size` (default 0.35), colour `color` (default 0xffffff), and a head glow of size `head`
  // (default 1.4; 0 for none). Returns {group, curve, points, headGlow, update(t, t0, opts)}: the first
  // particle leaves the start at t0, so the stream's front reaches the end 1 / speed s later; opts {reach (a
  // fraction of the curve that hides particles beyond it, default 1), gain (0 to 1, default 1), stop (a time
  // after which no particle leaves the start; the last ones run out to the end)}. The head glow rides the
  // front until it arrives. Particles fade in over the first and out over the last 8% of the curve. With `solid`
  // (default false) the points blend normally, for a light ground where additive light vanishes: they keep their
  // full colour (gain sets the material opacity), hidden ones move far below the floor, and there is no head glow.
  P.flow = function (curve, opts) {
    var N = opt(opts, "count", 60), speed = opt(opts, "speed", 0.5), spread = opt(opts, "spread", 0.08);
    var color = new THREE.Color(opt(opts, "color", 0xffffff)), rand = P.rng(opt(opts, "seed", 7));
    var solid = opt(opts, "solid", false);
    var pos = new Float32Array(N * 3), col = new Float32Array(N * 3), jit = [];
    for (var k = 0; k < N; k++) jit.push([(rand() - 0.5) * 2 * spread, (rand() - 0.5) * 2 * spread, (rand() - 0.5) * 2 * spread]);
    var geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
    var pts = new THREE.Points(geo, new THREE.PointsMaterial({ map: Kit.glowTexture(), size: opt(opts, "size", 0.35),
      vertexColors: true, transparent: true, depthWrite: false, sizeAttenuation: true,
      blending: solid ? THREE.NormalBlending : THREE.AdditiveBlending }));
    pts.frustumCulled = false;
    var group = new THREE.Group(); group.add(pts);
    var hs = solid ? 0 : opt(opts, "head", 1.4), head = null;
    if (hs > 0) { head = Kit.glow({ color: color, size: hs, opacity: 0 }); group.add(head); }
    var v = new THREE.Vector3();
    var f = {
      group: group, curve: curve, points: pts, headGlow: head,
      update: function (t, t0, o) {
        var gain = opt(o, "gain", 1), reach = opt(o, "reach", 1), stop = opt(o, "stop", Infinity);
        var running = t >= t0, front = Math.min(reach, (t - t0) * speed);
        for (var i = 0; i < N; i++) {
          var fr = (((t - t0) * speed + i / N) % 1 + 1) % 1;  // slot i's fraction along the curve
          var leftAt = t - fr / speed;                         // when the particle there left the start
          var on = running && fr <= reach && leftAt >= t0 - 1e-6 && leftAt <= stop;
          var p = curve.getPointAt(clamp(fr, 0, 1), v);
          var j = jit[i];
          pos[i * 3] = p.x + j[0]; pos[i * 3 + 1] = solid && !on ? -1e4 : p.y + j[1]; pos[i * 3 + 2] = p.z + j[2];
          var a = solid ? 1 : (on ? gain * Math.min(1, fr / 0.08, (1 - fr) / 0.08) : 0);
          col[i * 3] = color.r * a; col[i * 3 + 1] = color.g * a; col[i * 3 + 2] = color.b * a;
        }
        geo.attributes.position.needsUpdate = true;
        geo.attributes.color.needsUpdate = true;
        if (solid) pts.material.opacity = gain;
        if (head) {
          head.position.copy(curve.getPointAt(clamp(front, 0, 1), v));
          head.material.opacity = running && front > 0 && front < 1 && t <= stop ? 0.9 * gain : 0;
        }
      }
    };
    f.update(-1, 0);
    return f;
  };
})();
