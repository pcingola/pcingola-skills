/*
 * Kit tiltshift: a post pass with tilt-shift blur (by screen height) and depth blur (by distance), written in
 * plain ShaderMaterials because the three.js postprocessing addons are ES modules and do not load from
 * file://. The scene renders into a multisampled half-float target with a depth texture; three blur levels
 * (1/2, 1/4, 1/8 resolution) are mixed per pixel by the blur amount. Classic script for three.js 0.159.0.
 */
(function () {
  "use strict";
  var Kit = window.Kit = window.Kit || {};

  var VS = "varying vec2 vUv; void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }";
  var BLUR_FS = [
    "uniform sampler2D tSrc; uniform vec2 uDir; varying vec2 vUv;",
    "void main(){",
    "  vec4 c = texture2D(tSrc, vUv) * 0.2270270270;",
    "  c += (texture2D(tSrc, vUv + uDir * 1.3846153846) + texture2D(tSrc, vUv - uDir * 1.3846153846)) * 0.3162162162;",
    "  c += (texture2D(tSrc, vUv + uDir * 3.2307692308) + texture2D(tSrc, vUv - uDir * 3.2307692308)) * 0.0702702703;",
    "  gl_FragColor = c;",
    "}"].join("\n");
  var COMP_FS = [
    "uniform sampler2D tSharp, tMed, tStrong, tHuge, tDepth;",
    "uniform float uTilt, uDof, uFocus, uRange, uNear, uFar, uVig, uDither; uniform vec4 uBand;",
    "varying vec2 vUv;",
    "float linDepth(float d){ float z = d * 2.0 - 1.0; return 2.0 * uNear * uFar / (uFar + uNear - z * (uFar - uNear)); }",
    "void main(){",
    "  float ty = 1.0 - vUv.y;",
    "  float ct = (1.0 - smoothstep(0.0, uBand.x, ty)) * uBand.z + smoothstep(uBand.y, 1.0, ty) * uBand.w;",
    "  float cd = clamp((linDepth(texture2D(tDepth, vUv).x) - uFocus) / uRange, 0.0, 1.0);",
    "  float coc = clamp(max(ct * uTilt, cd * uDof), 0.0, 1.0) * 3.0;",
    "  vec3 s = texture2D(tSharp, vUv).rgb, m = texture2D(tMed, vUv).rgb, g = texture2D(tStrong, vUv).rgb, h = texture2D(tHuge, vUv).rgb;",
    "  vec3 c = coc < 1.0 ? mix(s, m, coc) : (coc < 2.0 ? mix(m, g, coc - 1.0) : mix(g, h, coc - 2.0));",
    "  vec2 q = vUv - 0.5; c *= mix(1.0, 1.0 - dot(q, q) * 0.9, uVig);",
    "  gl_FragColor = vec4(c, 1.0);",
    "  #include <colorspace_fragment>",
    "  gl_FragColor.rgb += uDither * (fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453) - 0.5) / 255.0;",
    "}"].join("\n");

  // opts: {width, height (default: the renderer's drawing buffer), samples (MSAA, 4), tilt (0..1, 1),
  // band ([top, bottom] of the sharp band as fractions of the frame height from the top, [0.35, 0.75]),
  // edge ([blur at the top edge, at the bottom edge], [1, 1]), dof (0..1, 0), focus (sharp distance, 10),
  // range (distance over which blur reaches full, 10; only farther than focus blurs), vignette (0),
  // dither (1 = +-0.5/255 noise against banding, 1)}.
  // Returns {render(scene, camera, target), set(opts), setSize(w, h), dispose()}. render draws to `target`
  // (default null: the canvas). With tilt and dof at 0 it skips the blur passes.
  Kit.tiltShift = function (renderer, opts) {
    opts = opts || {};
    var size = renderer.getDrawingBufferSize(new THREE.Vector2());
    var W = opts.width || size.x, H = opts.height || size.y;
    var depthTex = new THREE.DepthTexture(W, H);
    var main = new THREE.WebGLRenderTarget(W, H, { samples: opts.samples === undefined ? 4 : opts.samples,
      type: THREE.HalfFloatType, depthTexture: depthTex });
    var rtOpts = { type: THREE.HalfFloatType, minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, depthBuffer: false };
    var levels = [2, 4, 8].map(function (f) {
      return [new THREE.WebGLRenderTarget(Math.ceil(W / f), Math.ceil(H / f), rtOpts),
              new THREE.WebGLRenderTarget(Math.ceil(W / f), Math.ceil(H / f), rtOpts), f];
    });
    var quadCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    var quadScene = new THREE.Scene();
    var quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), null);
    quad.frustumCulled = false;
    quadScene.add(quad);
    var blurMat = new THREE.ShaderMaterial({
      uniforms: { tSrc: { value: null }, uDir: { value: new THREE.Vector2() } },
      vertexShader: VS, fragmentShader: BLUR_FS, depthTest: false, depthWrite: false
    });
    var comp = new THREE.ShaderMaterial({
      uniforms: {
        tSharp: { value: main.texture }, tMed: { value: levels[0][1].texture }, tStrong: { value: levels[1][1].texture },
        tHuge: { value: levels[2][1].texture }, tDepth: { value: depthTex },
        uTilt: { value: 1 }, uDof: { value: 0 }, uFocus: { value: 10 }, uRange: { value: 10 },
        uNear: { value: 0.1 }, uFar: { value: 100 }, uBand: { value: new THREE.Vector4(0.35, 0.75, 1, 1) },
        uVig: { value: 0 }, uDither: { value: 1 }
      },
      vertexShader: VS, fragmentShader: COMP_FS, depthTest: false, depthWrite: false
    });
    var U = comp.uniforms;

    function set(o) {
      if (o.tilt !== undefined) U.uTilt.value = o.tilt;
      if (o.dof !== undefined) U.uDof.value = o.dof;
      if (o.focus !== undefined) U.uFocus.value = o.focus;
      if (o.range !== undefined) U.uRange.value = Math.max(1e-6, o.range);
      if (o.band) { U.uBand.value.x = o.band[0]; U.uBand.value.y = o.band[1]; }
      if (o.edge) { U.uBand.value.z = o.edge[0]; U.uBand.value.w = o.edge[1]; }
      if (o.vignette !== undefined) U.uVig.value = o.vignette;
      if (o.dither !== undefined) U.uDither.value = o.dither;
    }
    set(opts);

    function pass(mat, target) { quad.material = mat; renderer.setRenderTarget(target); renderer.render(quadScene, quadCam); }
    function blur(src, dst, dx, dy) { blurMat.uniforms.tSrc.value = src.texture; blurMat.uniforms.uDir.value.set(dx, dy); pass(blurMat, dst); }

    function render(scene, camera, target) {
      var prev = renderer.getRenderTarget();
      renderer.setRenderTarget(main);
      renderer.render(scene, camera);
      if (camera.near !== undefined) { U.uNear.value = camera.near; U.uFar.value = camera.far; }
      if (U.uTilt.value > 0.001 || U.uDof.value > 0.001) {
        var src = main;
        levels.forEach(function (l) {
          var w = l[0].width, h = l[0].height;
          blur(src, l[0], 1.5 / w, 0);
          blur(l[0], l[1], 0, 1.5 / h);
          src = l[1];
        });
      }
      pass(comp, target === undefined ? null : target);
      if (target === undefined) renderer.setRenderTarget(prev);
    }

    function setSize(w, h) {
      W = w; H = h;
      main.setSize(w, h);
      levels.forEach(function (l) { l[0].setSize(Math.ceil(w / l[2]), Math.ceil(h / l[2])); l[1].setSize(Math.ceil(w / l[2]), Math.ceil(h / l[2])); });
    }

    function dispose() {
      main.dispose(); depthTex.dispose();
      levels.forEach(function (l) { l[0].dispose(); l[1].dispose(); });
      blurMat.dispose(); comp.dispose(); quad.geometry.dispose();
    }

    return { render: render, set: set, setSize: setSize, dispose: dispose, uniforms: U };
  };
})();
