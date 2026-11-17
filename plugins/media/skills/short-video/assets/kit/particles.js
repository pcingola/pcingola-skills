/*
 * Kit particles: glowing point clouds, a gradient sky, a star field, glow sprites and a glyph plane, the parts of
 * particle text (words formed by particles that lock into their letters). Classic script for three.js 0.159.0
 * (global THREE); adds Kit.particles. It needs no other kit file.
 *
 * Everything is a function of the scene time t and of seeded random values (Kit.particles.rng): no clock and no
 * Math.random. Colours are arguments; the defaults are neutral (white, greys). Word targets and glyph textures
 * are precomputed from the font file by `short-video.sh particle-text`, which writes <name>_targets.js (setting
 * window.PT_TARGETS[name]) and <name>_tex.png; no seek waits on a font load.
 *
 * Frame size: data-width and data-height of #root (default 1920x1080). Units: world units; the targets file
 * records the camera (fov, distance, frame) at which the text measures its font size in pixels.
 */
(function () {
  "use strict";
  var Kit = window.Kit = window.Kit || {};
  var P = Kit.particles = {};
  // Letter index unit of the texture's blue channel: B = (letter + 1) * STEP; at most MAX_LETTERS letters.
  var STEP = 8, MAX_LETTERS = 31;
  P.MAX_LETTERS = MAX_LETTERS;
  P.size = { width: 1920, height: 1080 };

  // Seeded generator in [0, 1) (Park-Miller).
  P.rng = function (seed) {
    var s = seed % 2147483647; if (s <= 0) s += 2147483646;
    return function () { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; };
  };
  P.clamp = function (v, a, b) { return v < a ? a : v > b ? b : v; };
  // 0 before a, 1 after b, linear between.
  P.lin = function (t, a, b) { return P.clamp((t - a) / (b - a), 0, 1); };
  P.mix = function (a, b, u) { return a + (b - a) * u; };
  P.smooth = function (u) { return u * u * (3 - 2 * u); };
  P.sineIO = function (u) { return 0.5 - 0.5 * Math.cos(Math.PI * u); };
  P.cubicIO = function (u) { return u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2; };
  P.outCubic = function (u) { return 1 - Math.pow(1 - u, 3); };
  P.outExpo = function (u) { return u >= 1 ? 1 : 1 - Math.pow(2, -10 * u); };
  P.inQuad = function (u) { return u * u; };
  // [r, g, b] in 0..1 of a CSS colour.
  P.col = function (c) { var k = new THREE.Color(c); return [k.r, k.g, k.b]; };
  // A CSS variable of the root element (e.g. "--ink"), or fallback when it is unset.
  P.css = function (name, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  };

  // Decoded word targets: {n, x, y (Float32Array, world units, centred on the text box), li (letter index per
  // point), w, h, em, ink ([w, h] of the ink), letters, lines, lc, ly (letter centres), camera ({width, height, fov,
  // distance, end})}. Throws when the camera's frame differs from #root's data-width and data-height.
  P.targets = function (name) {
    var d = (window.PT_TARGETS || {})[name];
    if (!d) throw new Error("Kit.particles.targets: no PT_TARGETS[" + JSON.stringify(name) + "]; load " + name + "_targets.js");
    var bin = atob(d.xy), buf = new ArrayBuffer(bin.length), u8 = new Uint8Array(buf), i;
    for (i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
    var q = new Int16Array(buf), n = d.n, x = new Float32Array(n), y = new Float32Array(n);
    var k = d.half / 32767;
    for (i = 0; i < n; i++) { x[i] = q[2 * i] * k; y[i] = q[2 * i + 1] * k; }
    var lb = atob(d.li), li = new Uint8Array(n);
    for (i = 0; i < n; i++) li[i] = lb.charCodeAt(i);
    var root = document.getElementById("root"), c = d.camera;
    if (root && root.dataset.width && (Number(root.dataset.width) !== c.width || Number(root.dataset.height) !== c.height))
      throw new Error("Kit.particles.targets: " + name + "_targets.js was made for a " + c.width + "x" + c.height +
                      " frame, #root is " + root.dataset.width + "x" + root.dataset.height + "; run particle-text with --frame " +
                      root.dataset.width + "x" + root.dataset.height);
    return { n: n, x: x, y: y, li: li, w: d.w, h: d.h, em: d.em, ink: d.ink, letters: d.letters, lines: d.lines,
             lc: d.lc, ly: d.ly, camera: c };
  };

  // Renderer, scene, perspective camera and sky. The canvas goes into #<opts.container> (default "gl").
  // opts: {fov (35), near (0.1), far (400), clear (sky top colour), sky: options of P.sky or false}.
  // Returns {renderer, scene, camera, sky, width, height, pxScale (pixels per world unit at distance 1)}.
  P.stage = function (opts) {
    opts = opts || {};
    var root = document.getElementById("root");
    var W = Number(opts.width || (root && root.dataset.width) || 1920);
    var H = Number(opts.height || (root && root.dataset.height) || 1080);
    P.size = { width: W, height: H };
    var renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(1);
    renderer.setSize(W, H);
    var skyOpts = opts.sky === false ? null : (opts.sky || {});
    renderer.setClearColor(new THREE.Color(opts.clear || (skyOpts && skyOpts.top) || "#0a0a0c"));
    renderer.domElement.id = "gl-canvas";
    document.getElementById(opts.container || "gl").appendChild(renderer.domElement);
    var scene = new THREE.Scene();
    var fov = opts.fov || 35;
    var camera = new THREE.PerspectiveCamera(fov, W / H, opts.near || 0.1, opts.far || 400);
    var sky = null;
    if (skyOpts) { sky = P.sky(skyOpts); scene.add(sky.mesh); }
    return { renderer: renderer, scene: scene, camera: camera, sky: sky, width: W, height: H,
             pxScale: H / (2 * Math.tan(THREE.MathUtils.degToRad(fov) / 2)) };
  };

  // Camera on an orbit: target (tx, ty, tz), distance d, yaw and pitch in degrees (yaw 0 looks toward -z),
  // roll in degrees about the view axis.
  P.pose = function (camera, p) {
    var y = THREE.MathUtils.degToRad(p.yaw || 0), pi = THREE.MathUtils.degToRad(p.pitch || 0);
    var tx = p.tx || 0, ty = p.ty || 0, tz = p.tz || 0;
    camera.position.set(tx + p.d * Math.sin(y) * Math.cos(pi), ty + p.d * Math.sin(pi), tz + p.d * Math.cos(y) * Math.cos(pi));
    camera.up.set(0, 1, 0);
    camera.lookAt(tx, ty, tz);
    if (p.roll) camera.rotateZ(THREE.MathUtils.degToRad(p.roll));
    camera.updateMatrixWorld();
  };

  // Sky: a large back-faced sphere with a vertical gradient (top, bottom), up to three soft colour blobs
  // ({dir: [x, y, z], col, amp, w}) and a dither against banding. Returns {mesh, uniforms}; uniforms.uGain.value
  // scales the blobs.
  P.sky = function (o) {
    o = o || {};
    var blobs = (o.blobs || []).slice(0, 3);
    while (blobs.length < 3) blobs.push({ dir: [0, 0, -1], col: "#000000", amp: 0, w: 1 });
    var u = {
      uTop: { value: new THREE.Color(o.top || "#0a0a0c") },
      uBot: { value: new THREE.Color(o.bottom || "#1a1b20") },
      uB: { value: blobs.map(function (b) { return new THREE.Vector3().fromArray(b.dir).normalize(); }) },
      uBC: { value: blobs.map(function (b) { return new THREE.Color(b.col); }) },
      uBA: { value: blobs.map(function (b) { return b.amp; }) },
      uBW: { value: blobs.map(function (b) { return b.w; }) },
      uGain: { value: 1.0 }
    };
    var mat = new THREE.ShaderMaterial({
      uniforms: u, side: THREE.BackSide, depthWrite: false,
      vertexShader: "varying vec3 vD; void main(){ vD = normalize(position); gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0);}",
      fragmentShader: [
        "uniform vec3 uTop; uniform vec3 uBot; uniform vec3 uB[3]; uniform vec3 uBC[3]; uniform float uBA[3]; uniform float uBW[3]; uniform float uGain;",
        "varying vec3 vD;",
        "float h(vec2 p){ return fract(sin(dot(p, vec2(12.9898,78.233)))*43758.5453); }",
        "void main(){",
        "  float g = smoothstep(0.55, -0.45, vD.y);",
        "  vec3 c = mix(uTop, uBot, g);",
        "  for(int i=0;i<3;i++){ float d = 1.0 - dot(vD, uB[i]); c += uBC[i]*uBA[i]*exp(-d/(uBW[i]*uBW[i])) * uGain; }",
        "  c += (h(gl_FragCoord.xy) - 0.5) / 255.0;",
        "  gl_FragColor = vec4(c, 1.0);",
        "}"].join("\n")
    });
    var mesh = new THREE.Mesh(new THREE.SphereGeometry(300, 48, 32), mat);
    mesh.renderOrder = -10;
    return { mesh: mesh, uniforms: u };
  };

  // A cloud of n glowing points blended additively. The caller fills pos (3n), col (3n, 0..1), size (n, world
  // units) and alpha (n) from t and calls flush(). Near points larger than 26 px turn into soft bokeh.
  // opts: {core (white core strength, 0.55), maxPx (160), depthTest (true), renderOrder}.
  P.cloud = function (n, stage, opts) {
    opts = opts || {};
    var g = new THREE.BufferGeometry();
    var pos = new Float32Array(3 * n), col = new Float32Array(3 * n), size = new Float32Array(n), alpha = new Float32Array(n);
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute("aColor", new THREE.BufferAttribute(col, 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute("aSize", new THREE.BufferAttribute(size, 1).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute("aAlpha", new THREE.BufferAttribute(alpha, 1).setUsage(THREE.DynamicDrawUsage));
    g.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 1e5);
    var mat = new THREE.ShaderMaterial({
      uniforms: { uScale: { value: stage.pxScale }, uCore: { value: opts.core != null ? opts.core : 0.55 }, uMax: { value: opts.maxPx || 160 } },
      transparent: true, depthWrite: false, depthTest: opts.depthTest !== false,
      vertexShader: [
        "attribute vec3 aColor; attribute float aSize; attribute float aAlpha;",
        "uniform float uScale; uniform float uMax; varying vec3 vC; varying float vA; varying float vS;",
        "void main(){",
        "  vec4 mv = modelViewMatrix*vec4(position,1.0);",
        "  gl_Position = projectionMatrix*mv;",
        "  float ps = aSize*uScale/max(-mv.z, 0.05);",
        "  float a = aAlpha;",
        "  if (mv.z > -0.3) a = 0.0;",
        "  if (ps < 1.6) { a *= ps/1.6; ps = 1.6; }",
        "  if (ps > 26.0) { a *= pow(26.0/ps, 1.15); }",
        "  gl_PointSize = min(ps, uMax);",
        "  vC = aColor; vA = a; vS = ps;",
        "}"].join("\n"),
      fragmentShader: [
        "uniform float uCore; varying vec3 vC; varying float vA; varying float vS;",
        "void main(){",
        "  vec2 p = gl_PointCoord - 0.5; float d = length(p)*2.0;",
        "  if (d > 1.0) discard;",
        "  float k = vS > 26.0 ? 3.0 : 14.0;",
        "  float core = exp(-d*d*k); float halo = exp(-d*d*3.2)*0.32*(1.0-d);",
        "  vec3 c = vC*(core+halo) + vec3(1.0)*core*core*uCore;",
        "  gl_FragColor = vec4(c*vA, 1.0);",
        "}"].join("\n")
    });
    mat.blending = THREE.CustomBlending;
    mat.blendSrc = THREE.OneFactor; mat.blendDst = THREE.OneFactor; mat.blendEquation = THREE.AddEquation;
    var pts = new THREE.Points(g, mat);
    pts.frustumCulled = false;
    if (opts.renderOrder != null) pts.renderOrder = opts.renderOrder;
    stage.scene.add(pts);
    return {
      n: n, pos: pos, col: col, size: size, alpha: alpha, points: pts,
      flush: function () {
        g.attributes.position.needsUpdate = true; g.attributes.aColor.needsUpdate = true;
        g.attributes.aSize.needsUpdate = true; g.attributes.aAlpha.needsUpdate = true;
      }
    };
  };

  // A texture from an <img id> already in the page (the <img> holds the page's load event). The image is drawn
  // into a canvas at its natural size and the texture is made only once the image is decoded: a THREE.Texture of
  // the <img> itself renders black in the render browser, and one first uploaded empty keeps a 1x1 storage, so
  // the later upload fails ("Offset overflows texture dimensions"). Call poll() in draw(t); it returns ready.
  P.imgTexture = function (id, onReady, srgb) {
    var img = document.getElementById(id);
    var h = { ready: false, texture: null };
    h.poll = function () {
      if (!h.ready && img && img.complete && img.naturalWidth > 0) {
        var cv = document.createElement("canvas");
        cv.width = img.naturalWidth; cv.height = img.naturalHeight;
        cv.getContext("2d").drawImage(img, 0, 0);
        var tex = new THREE.CanvasTexture(cv);
        tex.colorSpace = srgb ? THREE.SRGBColorSpace : THREE.NoColorSpace;
        tex.minFilter = THREE.LinearMipmapLinearFilter; tex.magFilter = THREE.LinearFilter;
        tex.anisotropy = 8; tex.needsUpdate = true;
        h.texture = tex; h.ready = true;
        if (onReady) onReady(tex);
      }
      return h.ready;
    };
    h.poll();
    return h;
  };

  // The glyph plane of a word, w x h world units, from its texture <img id> (R fill, G glow, B letter index).
  // opts: {top, bottom (fill gradient), glow (glow colour), sweepCol, sweepW (light sweep colour and width in
  // texture widths), reveal (letters appear at their lock time), revealDur, mirror (a fading reflection)}.
  // Uniforms in .u: uOpacity, uFill, uGlow, uSweep (sweep centre, -1 off, 0..1 across), uSweepAmt, uT (scene
  // time), uLock[k] (lock time of letter k). The mesh is hidden until the texture is ready.
  P.glyphPlane = function (stage, texId, w, h, opts) {
    opts = opts || {};
    var lock = []; for (var i = 0; i <= MAX_LETTERS; i++) lock.push(-100);
    var u = {
      uTex: { value: null }, uOpacity: { value: 0 }, uFill: { value: 1 }, uGlow: { value: 0.6 },
      uTop: { value: new THREE.Color(opts.top || "#ffffff") }, uBot: { value: new THREE.Color(opts.bottom || "#ffffff") },
      uGlowCol: { value: new THREE.Color(opts.glow || "#c8c8c8") },
      uSweep: { value: -1 }, uSweepW: { value: opts.sweepW || 0.06 }, uSweepCol: { value: new THREE.Color(opts.sweepCol || "#ffffff") },
      uSweepAmt: { value: 1.6 },
      uT: { value: 0 }, uReveal: { value: opts.reveal ? 1 : 0 }, uLock: { value: lock }, uRevealDur: { value: opts.revealDur || 0.35 },
      uMirror: { value: opts.mirror ? 1 : 0 }
    };
    var mat = new THREE.ShaderMaterial({
      uniforms: u, transparent: true, depthWrite: false,
      vertexShader: "varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0);}",
      fragmentShader: [
        "uniform sampler2D uTex; uniform float uOpacity, uFill, uGlow, uSweep, uSweepW, uSweepAmt, uT, uReveal, uRevealDur, uMirror;",
        "uniform vec3 uTop, uBot, uGlowCol, uSweepCol; uniform float uLock[" + (MAX_LETTERS + 1) + "];",
        "varying vec2 vUv;",
        "void main(){",
        "  vec2 uv = vUv; if (uMirror > 0.5) uv.y = 1.0 - uv.y;",
        "  vec4 s = texture2D(uTex, uv);",
        "  float fill = s.r, glow = s.g;",
        "  float r = 1.0;",
        "  if (uReveal > 0.5) { int li = int(floor(s.b*255.0/" + STEP.toFixed(1) + " + 0.5)) - 1; float lk = -100.0;",
        "    for (int i=0;i<" + (MAX_LETTERS + 1) + ";i++){ if (i==li) lk = uLock[i]; }",
        "    r = clamp((uT - lk)/uRevealDur, 0.0, 1.0); r = r*r*(3.0-2.0*r); }",
        "  float sx = uv.x + (uv.y - 0.5)*0.22;",
        "  float bd = (sx - uSweep)/uSweepW; float band = exp(-bd*bd);",
        "  vec3 base = mix(uBot, uTop, smoothstep(0.2, 0.8, uv.y));",
        "  vec3 c = base*fill*uFill + uGlowCol*glow*glow*uGlow + uSweepCol*band*(fill*uSweepAmt + glow*0.45*uSweepAmt);",
        "  float m = uMirror > 0.5 ? smoothstep(0.35, 1.0, vUv.y) : 1.0;",
        "  gl_FragColor = vec4(c*uOpacity*r*m, 1.0);",
        "}"].join("\n")
    });
    mat.blending = THREE.CustomBlending;
    mat.blendSrc = THREE.OneFactor; mat.blendDst = THREE.OneFactor; mat.blendEquation = THREE.AddEquation;
    var mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, h), mat);
    var tex = P.imgTexture(texId, function (t) { u.uTex.value = t; });
    mesh.visible = tex.ready;
    var poll = tex.poll;
    tex.poll = function () { var r = poll(); mesh.visible = r; return r; };
    stage.scene.add(mesh);
    return { mesh: mesh, u: u, tex: tex };
  };

  // White sprite textures drawn on a canvas, cached by kind: "dot" (radial falloff), "ring", "streak"
  // (a horizontal line soft at both ends).
  var spriteCache = {};
  P.spriteTexture = function (kind) {
    kind = kind || "dot";
    if (spriteCache[kind]) return spriteCache[kind];
    var cv = document.createElement("canvas"); cv.width = 256; cv.height = kind === "streak" ? 32 : 256;
    var cx = cv.getContext("2d");
    if (kind === "streak") {
      var gr = cx.createLinearGradient(0, 0, 256, 0);
      gr.addColorStop(0, "rgba(255,255,255,0)"); gr.addColorStop(0.5, "rgba(255,255,255,1)"); gr.addColorStop(1, "rgba(255,255,255,0)");
      cx.fillStyle = gr; cx.fillRect(0, 0, 256, 32);
      var gv = cx.createLinearGradient(0, 0, 0, 32);
      gv.addColorStop(0, "rgba(0,0,0,1)"); gv.addColorStop(0.5, "rgba(0,0,0,0)"); gv.addColorStop(1, "rgba(0,0,0,1)");
      cx.globalCompositeOperation = "destination-out"; cx.fillStyle = gv; cx.fillRect(0, 0, 256, 32);
    } else if (kind === "ring") {
      var rr = cx.createRadialGradient(128, 128, 0, 128, 128, 128);
      rr.addColorStop(0, "rgba(255,255,255,0)"); rr.addColorStop(0.62, "rgba(255,255,255,0.03)");
      rr.addColorStop(0.86, "rgba(255,255,255,0.9)"); rr.addColorStop(0.9, "rgba(255,255,255,0.5)"); rr.addColorStop(1, "rgba(255,255,255,0)");
      cx.fillStyle = rr; cx.fillRect(0, 0, 256, 256);
    } else {
      var rg = cx.createRadialGradient(128, 128, 0, 128, 128, 128);
      rg.addColorStop(0, "rgba(255,255,255,1)"); rg.addColorStop(0.18, "rgba(255,255,255,0.55)");
      rg.addColorStop(0.45, "rgba(255,255,255,0.14)"); rg.addColorStop(1, "rgba(255,255,255,0)");
      cx.fillStyle = rg; cx.fillRect(0, 0, 256, 256);
    }
    var t = new THREE.CanvasTexture(cv);
    spriteCache[kind] = t;
    return t;
  };

  // An additive glow sprite facing the camera, opacity 0, no depth test (a sprite crossing geometry keeps no
  // straight edge). Set .mesh.position, .mesh.scale and .mat.opacity from t.
  P.glow = function (stage, color, kind) {
    var mat = new THREE.SpriteMaterial({ map: P.spriteTexture(kind), color: new THREE.Color(color || "#ffffff"),
      transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending, opacity: 0 });
    var s = new THREE.Sprite(mat);
    stage.scene.add(s);
    return { mesh: s, mat: mat };
  };

  // A static star field of n points on a far shell behind the scene, colours picked from `colors` (CSS colours,
  // default white), seeded. Call .update(t) in draw for the twinkle.
  P.stars = function (stage, n, seed, colors) {
    var c = P.cloud(n, stage, { core: 0.4 });
    var r = P.rng(seed || 1), cols = (colors || ["#ffffff"]).map(P.col);
    var ph = new Float32Array(n), base = new Float32Array(n);
    for (var i = 0; i < n; i++) {
      var th = r() * Math.PI * 2, z = r() * 2 - 1, rr = 150 + r() * 60, s = Math.sqrt(1 - z * z);
      c.pos[3 * i] = rr * s * Math.cos(th); c.pos[3 * i + 1] = rr * z * 0.8; c.pos[3 * i + 2] = -Math.abs(rr * s * Math.sin(th));
      var cc = cols[Math.floor(r() * cols.length)];
      c.col[3 * i] = cc[0]; c.col[3 * i + 1] = cc[1]; c.col[3 * i + 2] = cc[2];
      c.size[i] = 0.25 + Math.pow(r(), 6) * 1.2;
      base[i] = 0.25 + r() * 0.6; ph[i] = r() * 50;
    }
    c.update = function (t) {
      for (var i = 0; i < n; i++) c.alpha[i] = base[i] * (0.7 + 0.3 * Math.sin(t * 3.1 + ph[i]));
      c.flush();
    };
    return c;
  };

  // Pin a DOM element (position: absolute at the frame's top left) to the 3D point p: its centre goes to the
  // projected point plus `extra` px down, scaled by ref / (camera distance to p), so it grows as the camera
  // pushes in like the 3D text beside it, and at most to maxWidth px wide when given.
  var v3 = null;
  P.pin = function (el, camera, p, ref, extra, maxWidth) {
    if (!v3) v3 = new THREE.Vector3();
    v3.set(p[0], p[1], p[2]);
    var dist = camera.position.distanceTo(v3);
    v3.project(camera);
    var x = (v3.x * 0.5 + 0.5) * P.size.width, y = (-v3.y * 0.5 + 0.5) * P.size.height;
    var k = ref / dist;
    var ew = Math.max(el.offsetWidth, el.scrollWidth);   // scrollWidth: a nowrap line wider than its box
    if (maxWidth && ew) k = Math.min(k, maxWidth / ew);
    el.style.transform = "translate(" + x.toFixed(2) + "px," + (y + (extra || 0)).toFixed(2) + "px) translate(-50%,-50%) scale(" + k.toFixed(4) + ")";
  };

  // Link every shader program and draw twice, now and again at the page's load event (when the glyph textures'
  // <img> are decoded). Without it the render's frame 0 can come out without particles. draw(t) is the page's
  // draw; time() returns the current scene time.
  P.prime = function (renderer, scene, camera, draw, time) {
    renderer.compile(scene, camera);
    draw(time()); draw(time());
    window.addEventListener("load", function () { renderer.compile(scene, camera); draw(time()); draw(time()); });
  };
})();
