/*
 * Kit shadow: a hemisphere fill plus one shadow-casting sun with PCF soft shadows, aimed by elevation and
 * azimuth, and a shadow catcher plane. Classic script for three.js 0.159.0 (global THREE).
 */
(function () {
  "use strict";
  var Kit = window.Kit = window.Kit || {};
  var D2R = Math.PI / 180;

  // Turn on soft shadows in `renderer` and add the lights to `scene`. opts: {sky (0xffffff), ground (0x808080),
  // fill (hemisphere intensity, 0.6), sun (0xffffff), intensity (1), elevation (45 degrees), azimuth (degrees
  // from +x toward +z, -30), target ([0, 0, 0]), extent (half size of the shadow box, 10), mapSize (2048),
  // radius (shadow blur, 3), bias (-0.0004), normalBias (0.004)}. fill and intensity are in legacy light units:
  // when renderer.useLegacyLights is false (the three.js 0.159.0 default) they are multiplied by pi, so a white
  // Lambert surface facing the sun at intensity 1 with fill 0 renders white in both modes.
  // Returns {hemi, sun, aim(target, extent, elevation, azimuth)}; aim moves the sun and its shadow box.
  Kit.lights = function (scene, renderer, opts) {
    opts = opts || {};
    function o(k, d) { return opts[k] === undefined ? d : opts[k]; }
    var units = renderer.useLegacyLights ? 1 : Math.PI;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    var hemi = new THREE.HemisphereLight(o("sky", 0xffffff), o("ground", 0x808080), o("fill", 0.6) * units);
    var sun = new THREE.DirectionalLight(o("sun", 0xffffff), o("intensity", 1) * units);
    sun.castShadow = true;
    sun.shadow.mapSize.set(o("mapSize", 2048), o("mapSize", 2048));
    sun.shadow.bias = o("bias", -0.0004);
    sun.shadow.normalBias = o("normalBias", 0.004);
    sun.shadow.radius = o("radius", 3);
    scene.add(hemi, sun, sun.target);
    var state = { elevation: o("elevation", 45), azimuth: o("azimuth", -30), extent: o("extent", 10), target: o("target", [0, 0, 0]) };
    function aim(target, extent, elevation, azimuth) {
      if (target) state.target = Array.isArray(target) ? target : [target.x, target.y, target.z];
      if (extent !== undefined) state.extent = extent;
      if (elevation !== undefined) state.elevation = elevation;
      if (azimuth !== undefined) state.azimuth = azimuth;
      var el = state.elevation * D2R, az = state.azimuth * D2R, t = state.target, e = state.extent;
      var dist = 4 * e;
      sun.target.position.set(t[0], t[1], t[2]);
      sun.position.set(t[0] + Math.cos(el) * Math.cos(az) * dist, t[1] + Math.sin(el) * dist, t[2] + Math.cos(el) * Math.sin(az) * dist);
      sun.target.updateMatrixWorld();
      var c = sun.shadow.camera;
      c.left = -e; c.right = e; c.top = e; c.bottom = -e; c.near = 0.01 * dist; c.far = dist + 4 * e;
      c.updateProjectionMatrix();
    }
    aim();
    return { hemi: hemi, sun: sun, aim: aim };
  };

  // Set castShadow and receiveShadow on `obj` and every mesh under it.
  Kit.shadows = function (obj, cast, receive) {
    obj.traverse(function (m) {
      if (m.isMesh || m.isInstancedMesh) { m.castShadow = cast !== false; m.receiveShadow = receive !== false; }
    });
    return obj;
  };

  // A horizontal plane that shows only the shadows falling on it. opts: {size (20), opacity (0.35),
  // color (0x000000), y (0)}.
  Kit.shadowCatcher = function (opts) {
    opts = opts || {};
    var m = new THREE.Mesh(new THREE.PlaneGeometry(opts.size || 20, opts.size || 20).rotateX(-Math.PI / 2),
      new THREE.ShadowMaterial({ opacity: opts.opacity === undefined ? 0.35 : opts.opacity, color: opts.color || 0x000000 }));
    m.position.y = opts.y || 0;
    m.receiveShadow = true;
    return m;
  };
})();
