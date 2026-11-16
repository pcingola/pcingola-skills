/*
 * Kit labels3d: HTML elements anchored to 3D points. Classic script for three.js 0.159.0 (global THREE).
 * The label element and the WebGL canvas share one positioned parent of the stage size.
 */
(function () {
  "use strict";
  var Kit = window.Kit = window.Kit || {};
  var v = new THREE.Vector3();

  // The pixel position of world point `point` (THREE.Vector3 or [x, y, z]) in a width x height frame.
  // behind is true when the point is behind the camera or beyond its far plane.
  Kit.project = function (camera, point, width, height) {
    camera.updateMatrixWorld();
    if (Array.isArray(point)) v.set(point[0], point[1], point[2]); else v.copy(point);
    v.project(camera);
    return { x: (v.x + 1) / 2 * width, y: (1 - v.y) / 2 * height, behind: v.z > 1 || v.z < -1 };
  };

  // Move `el` so its anchor (fractions of its own box, default centre [0.5, 0.5]) sits on the projection of
  // `point`, shifted by `offset` pixels. opts: {width, height (default: the parent's client size), anchor,
  // offset, hideBehind (default true)}. Returns the projected position.
  Kit.anchor = function (el, camera, point, opts) {
    opts = opts || {};
    var parent = el.parentElement;
    var w = opts.width || parent.clientWidth, h = opts.height || parent.clientHeight;
    var a = opts.anchor || [0.5, 0.5], o = opts.offset || [0, 0];
    var p = Kit.project(camera, point, w, h);
    el.style.position = "absolute";
    el.style.left = "0px";
    el.style.top = "0px";
    el.style.transform = "translate(" + (p.x + o[0]).toFixed(2) + "px," + (p.y + o[1]).toFixed(2) + "px) translate(" +
      (-a[0] * 100) + "%," + (-a[1] * 100) + "%)";
    el.style.visibility = p.behind && opts.hideBehind !== false ? "hidden" : "";
    return p;
  };
})();
