/*
 * Kit gallery: framed picture cards in a dark space, over an optional glossy floor that mirrors them, with
 * spot lights from above (visible cone, lamp glow, light pool on the floor) and dust motes in the beams.
 * Classic script for three.js 0.159.0 (global THREE); needs kit/glow.js. Everything is set from the scene time:
 * no clocks, no randomness outside the seeded generator of `dust`.
 *
 * Pictures are canvases, <img> elements or element ids. A canvas becomes a CanvasTexture. An <img> is drawn into
 * a canvas before upload, because a texture made straight from an <img> samples black in the render browser;
 * `update` uploads it once it is decoded and again after the load event (an upload made while the page is still
 * parsing can come out empty). Put the <img> elements in the page markup, so its load event waits for them.
 *
 * Defaults are neutral greys; the page passes its palette. Colours are CSS colour strings or THREE.Color.
 */
(function () {
  "use strict";
  var Kit = window.Kit = window.Kit || {};
  var POOLS = 16;

  var CARD_VS = [
    "varying vec2 vUv; varying float vDist; varying float vWy;",
    "void main(){ vUv = uv; vec4 wp = modelMatrix * vec4(position, 1.0); vWy = wp.y;",
    "  vec4 mv = viewMatrix * wp; vDist = -mv.z; gl_Position = projectionMatrix * mv; }"].join("\n");

  // The face of a card: the picture inside a frame of width uB, an edge light uEdge on the frame's outer rim, a
  // warm lip on its inner rim, a top-lit gradient (uSpot), a diagonal light sweep at uSweep, fog by distance. With
  // uRefl 1 it is the mirrored copy under the floor, faded toward the fog colour with the depth below the floor.
  var CARD_FS = [
    "uniform sampler2D map; uniform vec2 uSize; uniform float uB; uniform vec3 uEdge, uFrame, uSweepCol, uFog; uniform vec2 uFogR;",
    "uniform float uBright, uSweep, uSpot, uRefl, uFade, uGlow, uReady, uReflAmt, uReflFall;",
    "varying vec2 vUv; varying float vDist; varying float vWy;",
    "void main(){",
    "  vec2 full = uSize + 2.0 * uB; vec2 p = vUv * full; vec2 q = (p - uB) / uSize;",
    "  vec3 col;",
    "  if (q.x >= 0.0 && q.x <= 1.0 && q.y >= 0.0 && q.y <= 1.0) {",
    "    col = mix(uFrame, texture2D(map, q).rgb, uReady);",
    "    col *= mix(1.0, mix(0.72, 1.18, smoothstep(0.0, 1.0, q.y)), uSpot);",
    "    vec2 c = q - 0.5; col *= (1.0 - dot(c, c) * 0.45) * uBright;",
    "  } else {",
    "    float dOut = min(min(p.x, full.x - p.x), min(p.y, full.y - p.y));",
    "    float dIn = max(uB - dOut, 0.0);",
    "    col = uFrame + vec3(0.05) * smoothstep(0.0, uB, dOut);",
    "    col += uEdge * (exp(-dOut / 0.010) * 1.6 + 0.18) * uGlow;",
    "    col += uSweepCol * exp(-dIn / 0.005) * 0.5 * uBright;",
    "  }",
    "  float s = (vUv.x + 0.5 * vUv.y) / 1.5;",
    "  col += uSweepCol * exp(-pow((s - uSweep) / 0.05, 2.0)) * 0.38;",
    "  col += uSweepCol * exp(-pow((s - uSweep + 0.07) / 0.1, 2.0)) * 0.1;",
    "  col = mix(col, uFog, smoothstep(uFogR.x, uFogR.y, vDist) * 0.92);",
    "  col = mix(uFog, col, uFade);",
    "  if (uRefl > 0.5) col = mix(uFog, col, pow(smoothstep(-uReflFall, 0.0, vWy), 1.6) * uReflAmt);",
    "  gl_FragColor = vec4(col, 1.0);",
    "  #include <colorspace_fragment>",
    "}"].join("\n");

  var FLOOR_VS = [
    "varying vec3 vW; varying float vDist;",
    "void main(){ vec4 wp = modelMatrix * vec4(position, 1.0); vW = wp.xyz; vec4 mv = viewMatrix * wp; vDist = -mv.z;",
    "  gl_Position = projectionMatrix * mv; }"].join("\n");
  // Semi-transparent over the mirrored cards: light pools (xz centre, radius, intensity), tile seams lit by the
  // pools, fog by distance.
  var FLOOR_FS = [
    "#define NP " + POOLS,
    "uniform vec4 uPools[NP]; uniform vec3 uPoolCol[NP]; uniform vec3 uFog, uBase, uSeam; uniform vec2 uFogR; uniform float uTile;",
    "varying vec3 vW; varying float vDist;",
    "void main(){",
    "  vec2 xz = vW.xz; vec3 col = uBase; float lit = 0.0;",
    "  for (int i = 0; i < NP; i++) { vec2 d = xz - uPools[i].xy; float r = uPools[i].z;",
    "    float e = exp(-dot(d, d) / (r * r)) * uPools[i].w; col += uPoolCol[i] * e; lit += e; }",
    "  vec2 g = abs(fract(xz / uTile) - 0.5); float w = fwidth(xz.x / uTile) * 1.2 + 0.004;",
    "  float seam = 1.0 - smoothstep(0.5 - w, 0.5, max(g.x, g.y));",
    "  col += uSeam * (1.0 - seam) * (0.35 + lit * 2.0);",
    "  float a = mix(0.5, 0.36, smoothstep(4.0, 30.0, vDist)) + min(lit, 1.0) * 0.15;",
    "  float f = smoothstep(uFogR.x, uFogR.y, vDist);",
    "  col = mix(col, uFog, f * 0.95); a = mix(a, 1.0, f);",
    "  gl_FragColor = vec4(col, a);",
    "  #include <colorspace_fragment>",
    "}"].join("\n");

  var CONE_VS = [
    "uniform float uH; varying float vH; varying vec3 vN; varying vec3 vV;",
    "void main(){ vH = (position.y + uH * 0.5) / uH; vec4 mv = modelViewMatrix * vec4(position, 1.0);",
    "  vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }"].join("\n");
  var CONE_FS = [
    "uniform vec3 uColor; uniform float uI; varying float vH; varying vec3 vN; varying vec3 vV;",
    "void main(){ float f = pow(abs(dot(vN, vV)), 1.6);",
    "  float a = uI * f * (0.025 + 0.4 * pow(vH, 3.0)) * smoothstep(0.0, 0.25, vH);",
    "  gl_FragColor = vec4(uColor * a, 1.0);",
    "  #include <colorspace_fragment>",
    "}"].join("\n");

  var SKY_VS = "varying vec3 vD; void main(){ vD = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }";
  var SKY_FS = [
    "uniform vec3 uTop, uHor; varying vec3 vD;",
    "void main(){ float h = clamp(vD.y * 2.2, 0.0, 1.0); vec3 c = mix(uHor, uTop, pow(h, 0.7));",
    "  gl_FragColor = vec4(c, 1.0);",
    "  #include <colorspace_fragment>",
    "}"].join("\n");

  function col(c, d) { return c instanceof THREE.Color ? c.clone() : new THREE.Color(c === undefined ? d : c); }

  // Build the gallery in `scene`. opts: {fog (horizon and fog colour, "#0c0d10"), fogNear (14), fogFar (46),
  // skyTop (colour at the zenith of a sky sphere that follows the camera, "#17191e"; null: no sky), floor (floor
  // colour, "#060709"; null: no floor and no mirrored cards), seam (tile seam colour, "#1e2127"), tile (tile size,
  // 2.4), floorSize (400), floorZ (floor centre z, 0), reflect (mirror strength, 0.6), reflectFall (depth below
  // the floor over which the mirror fades, 2.6), frame (card frame colour, "#08090b"), back (card back colour,
  // "#0b0c0f"), sweep (colour of the light sweep and the frame's inner lip, "#fff2e0")}.
  // Returns {card, spot, dust, picture, update(camera), cards, sky, floor, fog}.
  Kit.gallery = function (renderer, scene, opts) {
    opts = opts || {};
    function o(k, d) { return opts[k] === undefined ? d : opts[k]; }
    var fog = col(opts.fog, "#0c0d10");
    var fogR = new THREE.Vector2(o("fogNear", 14), o("fogFar", 46));
    var frameC = col(opts.frame, "#08090b"), backC = col(opts.back, "#0b0c0f"), sweepC = col(opts.sweep, "#fff2e0");
    var maxAniso = renderer.capabilities.getMaxAnisotropy();

    var sky = null;
    if (o("skyTop", "#17191e") !== null) {
      sky = new THREE.Mesh(new THREE.SphereGeometry(200, 32, 16), new THREE.ShaderMaterial({
        uniforms: { uTop: { value: col(opts.skyTop, "#17191e") }, uHor: { value: fog } },
        vertexShader: SKY_VS, fragmentShader: SKY_FS, side: THREE.BackSide, depthWrite: false }));
      sky.renderOrder = -10;
      scene.add(sky);
    }

    var pools = [], poolCols = [], poolCount = 0, floor = null, reflRoot = null;
    for (var i = 0; i < POOLS; i++) { pools.push(new THREE.Vector4(0, 0, 1, 0)); poolCols.push(new THREE.Color(0, 0, 0)); }
    if (o("floor", "#060709") !== null) {
      var floorMat = new THREE.ShaderMaterial({
        uniforms: { uPools: { value: pools }, uPoolCol: { value: poolCols }, uFog: { value: fog }, uFogR: { value: fogR },
          uBase: { value: col(opts.floor, "#060709") }, uSeam: { value: col(opts.seam, "#1e2127") }, uTile: { value: o("tile", 2.4) } },
        vertexShader: FLOOR_VS, fragmentShader: FLOOR_FS, transparent: true, depthWrite: true,
        extensions: { derivatives: true } });
      var size = o("floorSize", 400);
      floor = new THREE.Mesh(new THREE.PlaneGeometry(size, size).rotateX(-Math.PI / 2), floorMat);
      floor.position.z = o("floorZ", 0);
      floor.renderOrder = 1;
      scene.add(floor);
      reflRoot = new THREE.Group();
      reflRoot.scale.y = -1;
      scene.add(reflRoot);
    }

    var textures = [];
    window.addEventListener("load", function () { textures.forEach(function (t) { if (t.userData.img) t.userData.ok = false; }); });
    // A texture for a canvas, an <img> or the id of either; the same source gives the same texture.
    function picture(src) {
      var el = typeof src === "string" ? document.getElementById(src) : src;
      if (!el) throw new Error("Kit.gallery: no picture " + src);
      for (var k = 0; k < textures.length; k++) if (textures[k].userData.src === el) return textures[k];
      var t;
      if (el.tagName === "CANVAS") {
        t = new THREE.CanvasTexture(el);
        t.userData = { src: el, img: null, ok: true, w: el.width, h: el.height };
      } else {
        t = new THREE.Texture(document.createElement("canvas"));
        t.userData = { src: el, img: el, ok: false, w: el.naturalWidth, h: el.naturalHeight };
      }
      t.colorSpace = THREE.SRGBColorSpace;
      t.anisotropy = maxAniso;
      t.minFilter = THREE.LinearMipmapLinearFilter;
      textures.push(t);
      return t;
    }
    function upload() {
      textures.forEach(function (t) {
        var img = t.userData.img;
        if (!img || t.userData.ok || !img.complete || !img.naturalWidth) return;
        var cv = t.image;
        cv.width = img.naturalWidth; cv.height = img.naturalHeight;
        cv.getContext("2d").drawImage(img, 0, 0);
        t.userData.w = cv.width; t.userData.h = cv.height;
        t.needsUpdate = true; t.userData.ok = true;
      });
    }

    var cards = [];
    // A framed card facing +z. o: {picture (canvas, <img> or id), w (largest picture width, 2), h (largest picture
    // height; default none, so the width is w), aspect (width / height; default the picture's), b (frame width,
    // 0.06), edge (edge light colour, "#ffffff"), glow (edge light, 0.5), bright (1), reflect (mirror strength of
    // this card, 1), pos ([x, y, z]), yaw (radians)}. The picture is w wide, or h high when w / aspect exceeds h.
    // An <img> not yet decoded and without `aspect` starts at 16 / 9 and is resized on its first upload.
    // Returns {group, u, w, h, reflect}: move `group`; set u.uBright, u.uSpot (top light 0..1), u.uSweep (light
    // sweep position, -0.3 before the card to 1.4 past it), u.uGlow and u.uFade (0 fog colour .. 1 shown) per frame.
    function card(c) {
      var t = picture(c.picture);
      var known = c.aspect || (t.userData.w && t.userData.h ? t.userData.w / t.userData.h : 0);
      var maxW = c.w || 2, maxH = c.h || Infinity, b = c.b === undefined ? 0.06 : c.b;
      function size(a) { var ww = Math.min(maxW, maxH * a); return [ww, ww / a]; }
      var wh = size(known || 16 / 9), w = wh[0], h = wh[1];
      var uni = {
        map: { value: t }, uSize: { value: new THREE.Vector2(w, h) }, uB: { value: b },
        uEdge: { value: col(c.edge, "#ffffff") }, uFrame: { value: frameC }, uSweepCol: { value: sweepC },
        uFog: { value: fog }, uFogR: { value: fogR }, uBright: { value: c.bright === undefined ? 1 : c.bright },
        uSweep: { value: -1 }, uSpot: { value: 0 }, uRefl: { value: 0 }, uFade: { value: 1 },
        uReflAmt: { value: o("reflect", 0.6) }, uReflFall: { value: o("reflectFall", 2.6) },
        uGlow: { value: c.glow === undefined ? 0.5 : c.glow }, uReady: { value: 0 } };
      var geo = new THREE.PlaneGeometry(w + 2 * b, h + 2 * b);
      var face = new THREE.Mesh(geo, new THREE.ShaderMaterial({ uniforms: uni, vertexShader: CARD_VS, fragmentShader: CARD_FS }));
      face.position.z = 0.026;
      var backM = new THREE.Mesh(new THREE.BoxGeometry(w + 2 * b, h + 2 * b, 0.05), new THREE.MeshBasicMaterial({ color: backC }));
      var g = new THREE.Group();
      g.add(backM, face);
      scene.add(g);
      var rg = null, runi = null;
      if (reflRoot) {
        runi = {};
        Object.keys(uni).forEach(function (k) { runi[k] = uni[k]; });
        runi.uRefl = { value: 1 };
        runi.uReflAmt = { value: uni.uReflAmt.value };
        var rface = new THREE.Mesh(geo, new THREE.ShaderMaterial({ uniforms: runi, vertexShader: CARD_VS,
          fragmentShader: CARD_FS, side: THREE.DoubleSide }));
        rface.position.z = 0.026;
        rg = new THREE.Group();
        rg.add(rface);
        reflRoot.add(rg);
      }
      if (c.pos) g.position.set(c.pos[0], c.pos[1], c.pos[2]);
      if (c.yaw) g.rotation.y = c.yaw;
      var it = { group: g, refl: rg, u: uni, w: w, h: h, tex: t, reflect: c.reflect === undefined ? 1 : c.reflect };
      var pending = !known;
      // Give the card the picture's aspect: new face and back geometry, uSize and it.w, it.h.
      function resize(a) {
        var nw = size(a);
        it.w = nw[0]; it.h = nw[1];
        uni.uSize.value.set(it.w, it.h);
        var ng = new THREE.PlaneGeometry(it.w + 2 * b, it.h + 2 * b);
        face.geometry = ng;
        if (rg) rg.children[0].geometry = ng;
        geo.dispose(); geo = ng;
        backM.geometry.dispose();
        backM.geometry = new THREE.BoxGeometry(it.w + 2 * b, it.h + 2 * b, 0.05);
      }
      it.sync = function () {
        if (pending && t.userData.ok) { pending = false; resize(t.userData.w / t.userData.h); }
        uni.uReady.value = t.userData.ok ? 1 : 0;
        if (!rg) return;
        rg.position.copy(g.position); rg.quaternion.copy(g.quaternion); rg.scale.copy(g.scale);
        runi.uReflAmt.value = uni.uReflAmt.value * it.reflect;
        rg.visible = g.visible && it.reflect > 0.01;
      };
      cards.push(it);
      return it;
    }

    // A spot light from above at (x, z). s: {x, z, color ("#fff0d8"), height (7.5), radius (cone base, 2.4),
    // poolR (radius of the floor pool, 0.75 radius), poolI (pool strength at full light, 0.22), poolColor (the
    // light colour)}. Returns {cone, lamp, set(I)}; set the intensity I (0 off .. about 1) per frame.
    function spot(s) {
      var H = s.height || 7.5, R = s.radius || 2.4, c = col(s.color, "#fff0d8");
      var mat = new THREE.ShaderMaterial({ uniforms: { uColor: { value: c }, uI: { value: 0 }, uH: { value: H } },
        vertexShader: CONE_VS, fragmentShader: CONE_FS, transparent: true, depthWrite: false,
        blending: THREE.AdditiveBlending, side: THREE.DoubleSide });
      var cone = new THREE.Mesh(new THREE.ConeGeometry(R, H, 48, 1, true), mat);
      cone.position.set(s.x, H / 2, s.z);
      cone.renderOrder = 5;
      scene.add(cone);
      var lamp = Kit.glow({ color: c, size: 1.2, opacity: 0, position: [s.x, H - 0.1, s.z] });
      lamp.material.depthTest = false;
      scene.add(lamp);
      var pi = poolCount < POOLS ? poolCount++ : -1;
      if (pi >= 0) {
        pools[pi].set(s.x, s.z, s.poolR || R * 0.75, 0);
        poolCols[pi].copy(s.poolColor === undefined ? c : col(s.poolColor));
      }
      return { cone: cone, lamp: lamp, set: function (I) {
        mat.uniforms.uI.value = I; lamp.material.opacity = Math.min(1, I * 0.9);
        if (pi >= 0) pools[pi].w = I * (s.poolI === undefined ? 0.22 : s.poolI);
        cone.visible = I > 0.002; lamp.visible = I > 0.002; } };
    }

    // Dust motes rising through the beams. centers: [[x, z, r]], per: motes per centre. d: {seed (5), color
    // ("#ffe6c0"), size (0.07), height (6.5)}. Returns {points, update(t)}.
    function dust(centers, per, d) {
      d = d || {};
      var s = d.seed || 5, top = d.height || 6.5;
      var rnd = function () { return (s = (s * 16807) % 2147483647) / 2147483647; };
      var base = [];
      centers.forEach(function (c) { for (var k = 0; k < per; k++) {
        var a = rnd() * Math.PI * 2, r = Math.sqrt(rnd()) * c[2];
        base.push([c[0] + Math.cos(a) * r, rnd() * top, c[1] + Math.sin(a) * r, rnd() * 6.28, 0.5 + rnd()]); } });
      var geo = new THREE.BufferGeometry();
      var arr = new Float32Array(base.length * 3);
      geo.setAttribute("position", new THREE.BufferAttribute(arr, 3));
      var pts = new THREE.Points(geo, new THREE.PointsMaterial({ map: Kit.glowTexture(), color: col(d.color, "#ffe6c0"),
        size: d.size || 0.07, transparent: true, opacity: 0.8, depthWrite: false, blending: THREE.AdditiveBlending }));
      pts.frustumCulled = false;
      scene.add(pts);
      function update(t) {
        base.forEach(function (b, i) {
          arr[i * 3] = b[0] + Math.sin(t * 0.7 * b[4] + b[3]) * 0.12;
          arr[i * 3 + 1] = 0.2 + ((b[1] + t * 0.18 * b[4]) % top);
          arr[i * 3 + 2] = b[2] + Math.cos(t * 0.6 * b[4] + b[3]) * 0.12;
        });
        geo.attributes.position.needsUpdate = true;
      }
      update(0);
      return { points: pts, update: update };
    }

    // Call once per frame before rendering: uploads decoded pictures, centres the sky on the camera and moves the
    // mirrored cards with their cards.
    function update(camera) {
      upload();
      if (sky) sky.position.copy(camera.position);
      cards.forEach(function (c) { c.sync(); });
    }

    return { card: card, spot: spot, dust: dust, picture: picture, update: update, cards: cards, sky: sky,
      floor: floor, fog: fog };
  };
})();
