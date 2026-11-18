"""The short-video kit (`assets/kit/*.js`) in headless Chromium: each helper is called on a test page that loads
three.js 0.159.0 and the kit as classic scripts, and the test asserts on what it computes or draws. three.js comes
from short-video's node environment and Chromium from HyperFrames (`hyperframes browser path`), the ones scene
renders use. The page is served from a local HTTP server because a snap Chromium cannot read the system /tmp."""
from __future__ import annotations

import base64
import functools
import hashlib
import shutil
import subprocess
import tempfile
import threading
import unittest
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
from playwright.sync_api import sync_playwright

from short_video_tool import config
from short_video_tool.particle_text import ParticleText
from tests.integration.short_video.wrapper_env import NODE_DIR
from tests.prereq import requires

KIT = config.SCRIPTS_DIR.parent / "assets" / "kit"
KIT_FILES = ("camera.js", "labels3d.js", "glow.js", "shadow.js", "ribbon.js", "tiltshift.js", "pipeline.js", "particles.js",
             "gallery.js")
# The font of the two-letter particle-text targets of test_particles (one the repository ships).
PT_FONT = (config.SCRIPTS_DIR.parents[4] / "plugins/docs/skills/revealjs-slideshow/assets/reveal.js/dist/theme/fonts"
           / "source-sans-pro/source-sans-pro-semibold.ttf")
THREE_SHA = "7b1c5d75b28d9de15042e2b374f83566d8c7146697af8fdeb4558b0fb528a585"
THREE = NODE_DIR / "node_modules" / "three" / "build" / "three.min.js"
HYPERFRAMES = NODE_DIR / "node_modules" / ".bin" / "hyperframes"
LAUNCH_ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars"]
W, H = 640, 360


def three_ok() -> bool:
    return THREE.is_file() and hashlib.sha256(THREE.read_bytes()).hexdigest() == THREE_SHA


def chrome() -> str:
    done = subprocess.run([str(HYPERFRAMES), "browser", "path"], cwd=NODE_DIR, capture_output=True, text=True,
                          timeout=25)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip().splitlines()[-1]


# One Playwright and one Chrome for the module, started by the first class that needs them; each test opens its
# own page.
_PW: dict = {}


def browser():
    """The module's Chrome, launched on first use."""
    if "pw" not in _PW:
        _PW["pw"] = sync_playwright().start()
    if "browser" not in _PW:
        _PW["browser"] = _PW["pw"].chromium.launch(executable_path=chrome(), args=LAUNCH_ARGS)
    return _PW["browser"]


def tearDownModule() -> None:
    if "browser" in _PW:
        _PW.pop("browser").close()
    if "pw" in _PW:
        _PW.pop("pw").stop()


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


@contextmanager
def serve(folder: Path):
    """Serve `folder` on 127.0.0.1 and yield its base URL."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(folder)))
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()


def build_page(folder: Path, width: int = W, height: int = H) -> Path:
    """A page in `folder` with three.js, the kit, a `#stage` of width x height holding a WebGL renderer
    (`window.R`, preserveDrawingBuffer) and a `px(x, y)` reader of the canvas from the top left."""
    shutil.copyfile(THREE, folder / "three.min.js")
    for f in KIT_FILES:
        shutil.copyfile(KIT / f, folder / f)
    scripts = "\n".join(f'<script src="{f}"></script>' for f in ("three.min.js", *KIT_FILES))
    page = folder / "index.html"
    page.write_text(f"""<!doctype html><html><head><meta charset="utf-8">
<style>body{{margin:0;background:#000}} #stage{{position:relative;width:{width}px;height:{height}px;overflow:hidden}}
.label{{font:600 18px sans-serif;color:#111;background:#fff;padding:4px 8px;border-radius:4px;white-space:nowrap}}</style>
{scripts}</head><body><div id="stage"></div><script>
window.R = new THREE.WebGLRenderer({{antialias: false, preserveDrawingBuffer: true}});
R.setPixelRatio(1); R.setSize({width}, {height}, false); R.domElement.id = "gl";
R.outputColorSpace = THREE.SRGBColorSpace;
document.getElementById("stage").appendChild(R.domElement);
window.px = function (x, y) {{
  var gl = R.getContext(), out = new Uint8Array(4);
  gl.readPixels(x, {height} - 1 - y, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, out);
  return [out[0], out[1], out[2]];
}};
window.rowMean = function (y, x0, x1) {{
  var gl = R.getContext(), n = x1 - x0, out = new Uint8Array(4 * n);
  gl.readPixels(x0, {height} - 1 - y, n, 1, gl.RGBA, gl.UNSIGNED_BYTE, out);
  return out;
}};
</script></body></html>""", encoding="utf-8")
    return page


# The scene of the combined still: ground, blocks with shadows, two route ribbons, glows, a label, a camera
# from a keyframe path at t = 2, and the tilt-shift pass.
STILL_JS = """
() => {
  var scene = new THREE.Scene();
  scene.background = new THREE.Color(0xd9dde0);
  scene.fog = new THREE.Fog(0xd9dde0, 14, 30);
  var cam = new THREE.PerspectiveCamera(35, R.domElement.width / R.domElement.height, 0.1, 100);
  var L = Kit.lights(scene, R, {elevation: 38, azimuth: -40, extent: 6});
  var ground = new THREE.Mesh(new THREE.PlaneGeometry(40, 40).rotateX(-Math.PI / 2), new THREE.MeshLambertMaterial({color: 0xc9cdc6}));
  ground.receiveShadow = true; scene.add(ground);
  var mat = new THREE.MeshLambertMaterial({color: 0xf2f2ee});
  for (var i = -3; i <= 3; i++) for (var j = -3; j <= 3; j++) {
    if ((i + j) % 2 === 0) continue;
    var h = 0.3 + 0.9 * Math.abs(Math.sin(i * 12.9 + j * 7.3));
    var b = new THREE.Mesh(new THREE.BoxGeometry(0.7, h, 0.7), mat);
    b.position.set(i * 1.1, h / 2, j * 1.1); scene.add(b);
  }
  Kit.shadows(scene, true, true);
  var r1 = Kit.ribbon(Kit.roundCorners([[-3.85, 3.3], [-3.85, 0], [0, 0], [0, -3.3], [3.85, -3.3]], 0.3, 0.05),
                      {width: 0.16, color: 0x0f8ca0, opacity: 0.85, order: 2});
  Kit.ribbonProgress(r1, 0.8); scene.add(r1);
  var r2 = Kit.ribbon(Kit.roundCorners([[3.85, 3.3], [3.85, 1.1], [-1.1, 1.1], [-1.1, -2.2]], 0.3, 0.05),
                      {width: 0.12, color: 0xe0782a, opacity: 0.85, order: 3});
  Kit.ribbonProgress(r2, 0.6, 0.1); scene.add(r2);
  var head = r1.userData.sampler.at(0.8 * r1.userData.length);
  scene.add(Kit.glow({color: 0x2fd0e0, size: 1.6, position: [head.x, 0.1, head.z]}));
  scene.add(Kit.glowPoints([[-2.2, 0.5, -2.2], [2.2, 0.5, 2.2], [2.2, 0.5, -1.1], [-2.2, 0.5, 1.1]], {color: 0xffc070, size: 1.4}));
  var path = Kit.camera.path([
    {t: 0, tx: 0, ty: 0, tz: 0, d: 16, pitch: 70, yaw: 0, fov: 35},
    {t: 3, d: 11, pitch: 42, yaw: 20, ease: "sineInOut"}]);
  path.apply(cam, 2);
  L.aim([0, 0, 0], 6);
  var el = document.createElement("div"); el.className = "label"; el.id = "lab"; el.textContent = "Route head";
  document.getElementById("stage").appendChild(el);
  Kit.anchor(el, cam, [head.x, 0.1, head.z], {anchor: [0.5, 1], offset: [0, -14]});
  var post = Kit.tiltShift(R, {band: [0.35, 0.7], vignette: 0.25});
  post.render(scene, cam);
  return true;
}
"""


@requires(three_ok(), f"three.js 0.159.0 at {THREE} with the pinned SHA-256; run short-video.sh setup")
@requires(HYPERFRAMES.exists(), f"HyperFrames at {HYPERFRAMES}; run short-video.sh setup")
class TestKit(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls._tmp.name)
        build_page(cls.folder)
        cls.pt = ParticleText(("HI",), PT_FONT, size=200, count=2000, seed=5)
        cls.pt.write("pt", cls.folder)
        cls._serve = serve(cls.folder)
        cls.url = cls._serve.__enter__() + "index.html"
        cls.browser = browser()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._serve.__exit__(None, None, None)
        cls._tmp.cleanup()

    def page(self):
        page = self.browser.new_page(viewport={"width": W, "height": H})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(self.url)
        self.assertEqual(errors, [])
        self.addCleanup(page.close)
        return page

    def test_camera_path(self) -> None:
        """path.at interpolates each field with the segment's ease, holds outside the keys, inherits omitted
        fields, cuts on equal times; apply puts the camera at distance d from the target, straight above at
        pitch 90."""
        r = self.page().evaluate("""() => {
          var p = Kit.camera.path([{t: 0, tx: 0, d: 10, pitch: 90, yaw: 0}, {t: 2, d: 20, ease: "linear"},
                                   {t: 4, d: 30, tx: 2, ease: "sineInOut"}, {t: 5, d: 30}, {t: 5, d: 50}]);
          var cam = new THREE.PerspectiveCamera(35, 16 / 9, 0.1, 100);
          p.apply(cam, 1);
          return {mid: p.at(1).d, eased: p.at(3).d, quarter: p.at(2.5).d, tx: p.at(3).tx, before: p.at(-1).d,
                  after: p.at(9).d, cut: p.at(5).d, pitch: p.at(3).pitch,
                  pos: cam.position.toArray(), dist: cam.position.length()};
        }""")
        self.assertAlmostEqual(r["mid"], 15)
        self.assertAlmostEqual(r["eased"], 25)
        self.assertAlmostEqual(r["quarter"], 20 + 10 * (0.5 - 0.5 * __import__("math").cos(__import__("math").pi / 4)))
        self.assertAlmostEqual(r["tx"], 1)
        self.assertEqual((r["before"], r["after"], r["cut"], r["pitch"]), (10, 50, 50, 90))
        self.assertAlmostEqual(r["dist"], 15, places=5)
        self.assertAlmostEqual(r["pos"][0], 0, places=5)
        self.assertAlmostEqual(r["pos"][1], 15, places=5)

    def test_camera_fit(self) -> None:
        """fit moves tx, tz and d from a start pose until two world points land on the frame positions they have
        under a reference pose."""
        r = self.page().evaluate("""() => {
          var cam = new THREE.PerspectiveCamera(35, 16 / 9, 0.1, 100);
          var ref = {tx: 0.8, tz: -0.6, d: 7, pitch: 45, yaw: 10}, pts = [[1, 0, 1], [-1, 0, -2]];
          Kit.camera.pose(cam, ref);
          var goals = pts.map(function (p) { var q = Kit.project(cam, p, 1, 1); return p.concat([q.x, q.y]); });
          var s = Kit.camera.fit(cam, {tx: 0, tz: 0, d: 10, pitch: 45, yaw: 10}, ["tx", "tz", "d"], goals);
          return {s: s, ref: ref};
        }""")
        for k in ("tx", "tz", "d"):
            self.assertAlmostEqual(r["s"][k], r["ref"][k], places=3)

    def test_label_anchor(self) -> None:
        """The label's anchor sits on the projected point (checked against THREE.Vector3.project), and a point
        behind the camera hides it."""
        r = self.page().evaluate(f"""() => {{
          var cam = new THREE.PerspectiveCamera(40, {W} / {H}, 0.1, 100);
          Kit.camera.pose(cam, {{tx: 0, tz: 0, d: 8, pitch: 35, yaw: 25}});
          var el = document.createElement("div"); el.id = "l1"; el.style.width = "80px"; el.style.height = "20px";
          document.getElementById("stage").appendChild(el);
          Kit.anchor(el, cam, [1.5, 0.5, -0.7], {{anchor: [0.5, 1], offset: [0, -6]}});
          var b = el.getBoundingClientRect();
          var v = new THREE.Vector3(1.5, 0.5, -0.7).project(cam);
          var behind = document.createElement("div"); behind.id = "l2";
          document.getElementById("stage").appendChild(behind);
          Kit.anchor(behind, cam, cam.position.clone().multiplyScalar(2));
          return {{ax: b.left + b.width / 2, ay: b.bottom, ex: (v.x + 1) / 2 * {W}, ey: (1 - v.y) / 2 * {H} - 6,
                   vis: el.style.visibility, hidden: behind.style.visibility}};
        }}""")
        self.assertAlmostEqual(r["ax"], r["ex"], delta=0.05)
        self.assertAlmostEqual(r["ay"], r["ey"], delta=0.05)
        self.assertEqual((r["vis"], r["hidden"]), ("", "hidden"))

    def test_ribbon(self) -> None:
        """The strip has two vertices per path point and its arc length; drawn at progress 0.5 seen from above,
        the first half shows the ribbon colour and the second half the background."""
        r = self.page().evaluate(f"""() => {{
          var pts = Kit.roundCorners([[-4, 0], [0, 0], [0, -2]], 0.5, 0.1);
          var m = Kit.ribbon(pts, {{width: 0.4, color: 0xff0000, feather: 0}});
          var scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000); scene.add(m);
          var cam = new THREE.OrthographicCamera(-5 * {W} / {H}, 5 * {W} / {H}, 5, -5, 0.1, 50);
          Kit.camera.pose(cam, {{d: 10, pitch: 90}});
          Kit.ribbonProgress(m, 0.5);
          R.render(scene, cam);
          var toPx = function (x, z) {{ var p = Kit.project(cam, [x, 0.01, z], {W}, {H}); return px(Math.round(p.x), Math.round(p.y)); }};
          var at = m.userData.sampler.at(m.userData.length * 0.25);
          return {{n: pts.length, verts: m.geometry.attributes.position.count, len: m.userData.length,
                   head: m.material.uniforms.uHead.value, early: toPx(at.x, at.z), late: toPx(0, -1.8),
                   side: m.material.side === THREE.DoubleSide}};
        }}""")
        self.assertEqual(r["verts"], 2 * r["n"])
        # Straight runs of 3.5 and 1.5 plus a quarter arc of radius 0.5 drawn as a quadratic (length ~0.81).
        self.assertAlmostEqual(r["len"], 5.0 + 0.81, delta=0.03)
        self.assertAlmostEqual(r["head"], r["len"] / 2, places=4)
        self.assertGreater(r["early"][0], 200)
        self.assertEqual(r["late"], [0, 0, 0])
        self.assertTrue(r["side"])

    def test_glow(self) -> None:
        """A glow sprite blends additively without depth writes; on black it is bright at its centre, falls off,
        and leaves the corner black. pulse stays in its range and repeats with its period."""
        r = self.page().evaluate(f"""() => {{
          var s = Kit.glow({{color: 0x00ff00, size: 2}});
          var scene = new THREE.Scene(); scene.background = new THREE.Color(0x000000); scene.add(s);
          scene.add(Kit.glowPoints([[3, 0, 0]], {{color: 0xff0000, size: 1}}));
          var cam = new THREE.PerspectiveCamera(40, {W} / {H}, 0.1, 100); cam.position.set(0, 0, 6); cam.lookAt(0, 0, 0);
          R.render(scene, cam);
          var c = Kit.project(cam, [0, 0, 0], {W}, {H}), e = Kit.project(cam, [0.7, 0, 0], {W}, {H});
          return {{add: s.material.blending === THREE.AdditiveBlending, dw: s.material.depthWrite,
                   centre: px(Math.round(c.x), Math.round(c.y)), edge: px(Math.round(e.x), Math.round(e.y)),
                   corner: px(2, 2), p0: Kit.pulse(0, 1.5, 0.2, 1), p1: Kit.pulse(0.75, 1.5, 0.2, 1),
                   p2: Kit.pulse(1.5, 1.5, 0.2, 1)}};
        }}""")
        self.assertTrue(r["add"])
        self.assertFalse(r["dw"])
        self.assertGreater(r["centre"][1], 240)
        self.assertLess(r["edge"][1], r["centre"][1] - 40)
        self.assertGreater(r["edge"][1], 5)
        self.assertEqual(r["corner"], [0, 0, 0])
        self.assertAlmostEqual(r["p0"], 0.2)
        self.assertAlmostEqual(r["p1"], 1.0)
        self.assertAlmostEqual(r["p2"], 0.2)

    def test_shadow(self) -> None:
        """lights turns on PCF soft shadows; a box lit from +x at 45 degrees casts its shadow toward -x, so the
        ground left of the box is darker than the ground right of it."""
        r = self.page().evaluate(f"""() => {{
          var scene = new THREE.Scene();
          var L = Kit.lights(scene, R, {{elevation: 45, azimuth: 0, extent: 4, fill: 0.4}});
          var ground = new THREE.Mesh(new THREE.PlaneGeometry(10, 10).rotateX(-Math.PI / 2), new THREE.MeshLambertMaterial({{color: 0xffffff}}));
          var box = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshLambertMaterial({{color: 0x808080}}));
          box.position.y = 0.5; scene.add(ground, box); Kit.shadows(scene, true, true);
          var cam = new THREE.OrthographicCamera(-4 * {W} / {H}, 4 * {W} / {H}, 4, -4, 0.1, 50);
          Kit.camera.pose(cam, {{d: 10, pitch: 90}});
          R.render(scene, cam);
          var at = function (x) {{ var p = Kit.project(cam, [x, 0, 0], {W}, {H}); return px(Math.round(p.x), Math.round(p.y)); }};
          return {{on: R.shadowMap.enabled, soft: R.shadowMap.type === THREE.PCFSoftShadowMap, cast: L.sun.castShadow,
                   recv: ground.receiveShadow, shade: at(-1.0), lit: at(1.0)}};
        }}""")
        self.assertTrue(r["on"] and r["soft"] and r["cast"] and r["recv"])
        self.assertLess(r["shade"][0] + 30, r["lit"][0])

    def test_tiltshift(self) -> None:
        """Over a fine checkerboard, the tilt-shift pass changes pixels at the top edge and leaves the sharp band
        as the plain render draws it; with tilt 0 the top edge stays sharp too."""
        r = self.page().evaluate(f"""() => {{
          var cv = document.createElement("canvas"); cv.id = "chk"; cv.width = {W}; cv.height = {H};
          var g = cv.getContext("2d");
          for (var y = 0; y < {H}; y += 4) for (var x = 0; x < {W}; x += 4) {{
            g.fillStyle = ((x + y) / 4) % 2 ? "#ffffff" : "#000000"; g.fillRect(x, y, 4, 4); }}
          var tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace;
          tex.minFilter = tex.magFilter = THREE.NearestFilter; tex.generateMipmaps = false;
          var scene = new THREE.Scene();
          scene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), new THREE.MeshBasicMaterial({{map: tex}})));
          var cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 10); cam.position.z = 1;
          function rows() {{
            var out = [];
            [4, {H} / 2].forEach(function (y) {{ out.push(Array.from(rowMean(y, 100, 300))); }});
            return out;
          }}
          R.render(scene, cam); var plain = rows();
          var post = Kit.tiltShift(R, {{dither: 0}});
          post.render(scene, cam); var tilt = rows();
          post.set({{tilt: 0}}); post.render(scene, cam); var off = rows();
          function diff(a, b) {{ var s = 0; for (var i = 0; i < a.length; i += 4) s += Math.abs(a[i] - b[i]); return s / (a.length / 4); }}
          return {{top: diff(plain[0], tilt[0]), band: diff(plain[1], tilt[1]), offTop: diff(plain[0], off[0])}};
        }}""")
        self.assertGreater(r["top"], 60)
        self.assertLess(r["band"], 2)
        self.assertLess(r["offTop"], 2)

    def test_still_all_helpers(self) -> None:
        """The helpers together render a frame with no page error, and the label sits inside the stage."""
        page = self.page()
        self.assertTrue(page.evaluate(STILL_JS))
        box = page.locator("#lab").bounding_box()
        self.assertTrue(0 < box["x"] < W and 0 < box["y"] < H, box)
        center = page.evaluate(f"() => px({W // 2}, {H // 2})")
        self.assertNotEqual(center, [0, 0, 0])

    def test_pipeline_layout_and_level(self) -> None:
        """pipeline.line spaces n points along x around the centre; pipeline.hub puts them at the radius, evenly
        around a full circle or with the ends on the arc's ends; pipeline.level holds the base before tOn, reaches 1
        after the rise, and flashes above 1 at tOn + 0.3."""
        r = self.page().evaluate("""() => {
          var P = Kit.pipeline;
          var full = P.hub(4, {radius: 5}), arc = P.hub(3, {radius: 5, spread: 180, facing: 0});
          return {line: P.line(3, {spacing: 4, center: [1, 0, 2]}), full: full, arc: arc,
                  before: P.level(0, 2, {base: 0.2}), after: P.level(5, 2, {base: 0.2, flash: 0.6}),
                  peak: P.level(2.3, 2, {base: 0.2, flash: 0.6}), none: P.level(5, null, {base: 0.3})};
        }""")
        self.assertEqual(r["line"], [[-3, 0, 2], [1, 0, 2], [5, 0, 2]])
        for p in r["full"] + r["arc"]:
            self.assertAlmostEqual((p[0] ** 2 + p[2] ** 2) ** 0.5, 5, places=5)
        self.assertAlmostEqual(r["full"][0][2], -5, places=5)     # facing 0 is toward -z
        self.assertAlmostEqual(r["full"][2][2], 5, places=5)
        self.assertAlmostEqual(r["arc"][0][0], -5, places=5)      # a 180 degree arc ends on -x and +x
        self.assertAlmostEqual(r["arc"][2][0], 5, places=5)
        self.assertAlmostEqual(r["before"], 0.2, places=5)
        self.assertAlmostEqual(r["after"], 1, places=5)
        self.assertGreater(r["peak"], 1)
        self.assertEqual(r["none"], 0.3)

    def test_pipeline_station_connector_flow(self) -> None:
        """A station's set(level) raises its rim, halo, emissive and light from unlit to lit; each kind builds its
        placeholder; a connector draws only the index range between tail and head; a flow shows no particle before
        t0, lights only particles behind its front, puts them on the curve, gives the same frame whatever the seek
        order, and after stop empties once the last particle has run out; with solid, connector and flow blend normally,
        hidden particles move below the floor and there is no head glow."""
        r = self.page().evaluate("""() => {
          var P = Kit.pipeline;
          var st = P.station({kind: "ring", color: 0x00ff00, light: 10});
          st.set(0); var off = {rim: st.rim.material.opacity, halo: st.halo.material.opacity, em: st.mat.emissiveIntensity, li: st.light.intensity};
          st.set(1); var on = {rim: st.rim.material.opacity, halo: st.halo.material.opacity, em: st.mat.emissiveIntensity, li: st.light.intensity};
          var kinds = ["box", "cylinder", "ring", "stack"].map(function (k) { var n = 0; P.station({kind: k}).obj.traverse(function (o) { if (o.isMesh) n++; }); return n; });
          var curve = P.curve([0, 0, 0], [10, 0, 0], {arc: 1});
          var mid = curve.getPointAt(0.5);
          var c = P.connector(curve, {segments: 100, halo: 0});
          var tube = c.group.children[0], per = tube.geometry.index.count / 100;
          c.progress(0.5, 0.2); var range = [tube.geometry.drawRange.start / per, tube.geometry.drawRange.count / per];
          var f = P.flow(curve, {count: 50, speed: 0.5, spread: 0});
          function lit() { var c = f.points.geometry.attributes.color.array, p = f.points.geometry.attributes.position.array, out = [];
            for (var i = 0; i < 50; i++) if (c[i * 3] + c[i * 3 + 1] + c[i * 3 + 2] > 0) out.push([p[i * 3], p[i * 3 + 1], p[i * 3 + 2]]);
            return out; }
          f.update(0.9, 1); var pre = lit().length;
          f.update(2, 1); var half = lit();
          var snap = Array.from(f.points.geometry.attributes.position.array.slice(0, 30));
          f.update(7, 1); f.update(2, 1);
          var again = Array.from(f.points.geometry.attributes.position.array.slice(0, 30));
          f.update(3.5, 1, {stop: 2}); var drain = lit().length;
          f.update(4.5, 1, {stop: 2}); var drained = lit().length;
          var sf = P.flow(curve, {count: 50, speed: 0.5, spread: 0, solid: true}), sc = P.connector(curve, {solid: true});
          sf.update(2, 1); var sy = sf.points.geometry.attributes.position.array, shown = 0, below = 0;
          for (var i = 0; i < 50; i++) { if (sy[i * 3 + 1] < -1000) below++; else { shown++; } }
          var solid = {shown: shown, below: below, normal: sf.points.material.blending === THREE.NormalBlending,
                       head: sf.headGlow, conn: sc.group.children[0].material.blending === THREE.NormalBlending};
          return {off: off, on: on, kinds: kinds, mid: mid.toArray(), range: range, pre: pre, half: half,
                  same: JSON.stringify(snap) === JSON.stringify(again), drain: drain, drained: drained, solid: solid};
        }""")
        for k in ("rim", "halo", "em", "li"):
            self.assertGreater(r["on"][k], r["off"][k], k)
        self.assertEqual(r["kinds"], [1, 1, 2, 4])
        self.assertAlmostEqual(r["mid"][1], 1, places=5)          # the arc rises `arc` at the middle
        self.assertEqual(r["range"], [20, 30])
        self.assertEqual(r["pre"], 0)
        # one second after t0 at 0.5 lengths per second the front is at x = 5 (half the curve)
        self.assertTrue(r["half"])
        self.assertTrue(all(p[0] <= 5.05 for p in r["half"]), r["half"])
        self.assertTrue(all(0 <= p[1] <= 1.0001 for p in r["half"]))
        self.assertTrue(r["same"])
        self.assertGreater(r["drain"], 0)
        self.assertEqual(r["drained"], 0)
        # solid: normal blending, the particles behind the front shown and the rest moved below the floor, no head
        # the additive flow fades the particle at fraction 0 to black; the solid one shows it
        self.assertIn(r["solid"]["shown"] - len(r["half"]), (0, 1))
        self.assertEqual(r["solid"]["shown"] + r["solid"]["below"], 50)
        self.assertTrue(r["solid"]["normal"] and r["solid"]["conn"])
        self.assertIsNone(r["solid"]["head"])

    def test_particles(self) -> None:
        """Kit.particles decodes the targets `particle-text` writes to the points Python wrote; a cloud point draws
        a bright additive dot; the glyph plane stays black for a letter before its lock time and shows it after;
        stage, pose and pin agree on the frame and pin's maxWidth caps the scale; targets made for another frame
        than #root's throw. Guards kit/particles.js (assets/kit/README.md, Particles)."""
        _, payload = self.pt.render()
        page = self.page()
        page.add_script_tag(url="pt_targets.js")
        page.evaluate("""() => new Promise(ok => { var i = document.createElement("img"); i.id = "tex-pt";
          i.style.width = "1px"; i.onload = ok; i.src = "pt_tex.png"; document.body.appendChild(i); })""")
        r = page.evaluate(f"""() => {{
          var P = Kit.particles, T = P.targets("pt");
          var st = P.stage({{container: "stage", width: {W}, height: {H}, sky: false, clear: "#000000"}});
          var gl = st.renderer.getContext();
          function px(x, y) {{ var o = new Uint8Array(4); gl.readPixels(x, {H} - 1 - y, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, o); return Array.from(o.slice(0, 3)); }}
          P.pose(st.camera, {{d: 10}});
          var c = P.cloud(1, st); c.pos.set([0, 0, 0]); c.col.set([1, 0, 0]); c.size[0] = 0.3; c.alpha[0] = 1; c.flush();
          st.renderer.render(st.scene, st.camera);
          var dot = px({W // 2}, {H // 2}), corner = px(2, 2);
          c.points.visible = false;
          var g = P.glyphPlane(st, "tex-pt", T.w, T.h, {{reveal: true, revealDur: 0.1}});
          var ready = g.tex.poll();
          g.u.uOpacity.value = 1; g.u.uLock.value[0] = 1; g.u.uLock.value[1] = 1;
          var el = document.createElement("div"); el.style.position = "absolute"; el.style.left = "0"; el.style.top = "0";
          el.style.width = "10px"; el.style.height = "10px"; document.getElementById("stage").appendChild(el);
          P.pin(el, st.camera, [T.lc[0], 0, 0], 10);
          var b = el.getBoundingClientRect(), v = new THREE.Vector3(T.lc[0], 0, 0).project(st.camera);
          P.pin(el, st.camera, [T.lc[0], 0, 0], 1000, 0, 5); var capped = el.getBoundingClientRect().width;
          var root = document.createElement("div"); root.id = "root"; root.dataset.width = "1080"; root.dataset.height = "1920";
          document.body.appendChild(root);
          var mismatch = ""; try {{ P.targets("pt"); }} catch (e) {{ mismatch = e.message; }}
          root.remove();
          var at = Kit.project(st.camera, [T.lc[0], 0, 0], {W}, {H});
          var hit = [Math.round(at.x), Math.round(at.y)];
          g.u.uT.value = 0; st.renderer.render(st.scene, st.camera); var before = px(hit[0], hit[1]);
          g.u.uT.value = 2; st.renderer.render(st.scene, st.camera); var after = px(hit[0], hit[1]);
          return {{n: T.n, x: Array.from(T.x.slice(0, 5)), y: Array.from(T.y.slice(0, 5)), letters: T.letters,
                   dot: dot, corner: corner, ready: ready, before: before, after: after, capped: capped, mismatch: mismatch,
                   pin: [b.left + b.width / 2, b.top + b.height / 2], proj: [(v.x + 1) / 2 * {W}, (1 - v.y) / 2 * {H}]}};
        }}""")
        x = [q * payload["half"] / 32767 for q in np.frombuffer(base64.b64decode(payload["xy"]), dtype="<i2")[:10]]
        self.assertEqual((r["n"], r["letters"]), (2000, 2))
        for k in range(5):
            self.assertAlmostEqual(r["x"][k], x[2 * k], places=4)
            self.assertAlmostEqual(r["y"][k], x[2 * k + 1], places=4)
        self.assertGreater(r["dot"][0], 200)
        self.assertEqual(r["corner"], [0, 0, 0])
        self.assertTrue(r["ready"])
        self.assertEqual(r["before"], [0, 0, 0])
        self.assertGreater(min(r["after"]), 150)
        self.assertAlmostEqual(r["pin"][0], r["proj"][0], delta=0.6)
        self.assertAlmostEqual(r["pin"][1], r["proj"][1], delta=0.6)
        self.assertAlmostEqual(r["capped"], 5, delta=0.01)
        self.assertIn("made for a 1920x1080 frame, #root is 1080x1920", r["mismatch"])


    def test_gallery(self) -> None:
        """Kit.gallery (assets/kit/README.md, Gallery): a card shows its canvas picture inside its frame; the floor
        mirrors it below y = 0, and with floor null there is no mirror; an <img> picture is drawn once decoded (not
        black); uFade 0 turns the card to the fog colour; a spot at intensity 1 brightens the floor under it."""
        r = self.page().evaluate(f"""async () => {{
          function solid(c) {{ var cv = document.createElement("canvas"); cv.width = 64; cv.height = 40;
            var g = cv.getContext("2d"); g.fillStyle = c; g.fillRect(0, 0, 64, 40); return cv; }}
          function shot(floor) {{
            var scene = new THREE.Scene();
            var G = Kit.gallery(R, scene, {{fog: "#000000", skyTop: null, floor: floor}});
            var cam = new THREE.PerspectiveCamera(60, {W} / {H}, 0.1, 100); cam.position.set(0, 1.5, 6); cam.lookAt(0, 1.5, 0);
            cam.updateMatrixWorld();
            return {{scene: scene, G: G, cam: cam, at: function (p) {{ var q = Kit.project(cam, p, {W}, {H});
              return px(Math.round(q.x), Math.round(q.y)); }}, draw: function () {{ G.update(cam); R.render(scene, cam); }}}};
          }}
          var a = shot(undefined), c = a.G.card({{picture: solid("#ff0000"), w: 2, b: 0.1, pos: [0, 1.5, 0]}});
          a.draw(); var centre = a.at([0, 1.5, 0]), mirror = a.at([0, -1.5, 0]), aside = a.at([3.5, -1.5, 0]);
          var s = a.G.spot({{x: 0, z: 2.5}}); s.set(0); a.draw(); var dark = a.at([0, 0, 2.5]);
          s.set(1); a.draw(); var lit = a.at([0, 0, 2.5]); s.set(0);
          c.u.uFade.value = 0; a.draw(); var faded = a.at([0, 1.5, 0]);
          var b = shot(null); b.G.card({{picture: solid("#ff0000"), w: 2, b: 0.1, pos: [0, 1.5, 0]}});
          b.draw(); var noMirror = b.at([0, -1.5, 0]);
          var img = document.createElement("img"); img.id = "gal-img"; document.body.appendChild(img);
          img.src = solid("#00ff00").toDataURL(); await img.decode();
          var d = shot(null), ci = d.G.card({{picture: "gal-img", w: 2, pos: [0, 1.5, 0]}});
          d.draw(); var green = d.at([0, 1.5, 0]);
          return {{centre: centre, mirror: mirror, aside: aside, dark: dark, lit: lit, faded: faded, noMirror: noMirror,
                   green: green, aspect: ci.w / ci.h, ready: ci.u.uReady.value}};
        }}""")
        self.assertGreater(r["centre"][0], 200)
        self.assertLess(max(r["centre"][1:]), 60)
        self.assertGreater(r["mirror"][0], r["aside"][0] + 20)
        self.assertLess(r["noMirror"][0], 10)
        self.assertGreater(sum(r["lit"]), sum(r["dark"]) + 30)
        self.assertLess(max(r["faded"]), 10)
        self.assertGreater(r["green"][1], 200)
        self.assertLess(r["green"][0], 60)
        self.assertAlmostEqual(r["aspect"], 64 / 40, places=5)
        self.assertEqual(r["ready"], 1)

    def test_gallery_aspect(self) -> None:
        """Kit.gallery card sizing (assets/kit/README.md, Gallery): a card fits its picture into w x h; an <img>
        card created before decode without `aspect` starts at 16:9 and takes the picture's aspect on its first
        upload (portrait 40x64 into 2 x 2 gives 1.25 x 2, square gives 2 x 2), so the face no longer covers the
        old 16:9 width; `aspect` given at creation sizes the card at once."""
        r = self.page().evaluate(f"""async () => {{
          function img(id, w, h) {{ var cv = document.createElement("canvas"); cv.width = w; cv.height = h;
            var g = cv.getContext("2d"); g.fillStyle = "#ff0000"; g.fillRect(0, 0, w, h);
            var el = document.createElement("img"); el.id = id; document.body.appendChild(el); el.src = cv.toDataURL(); return el; }}
          var scene = new THREE.Scene(), G = Kit.gallery(R, scene, {{fog: "#000000", skyTop: null, floor: null}});
          var p = img("asp-p", 40, 64), q = img("asp-q", 50, 50), e = img("asp-e", 40, 64);
          var cp = G.card({{picture: p, w: 2, h: 2, b: 0, pos: [0, 0, 0]}});
          var cq = G.card({{picture: q, w: 2, h: 2, b: 0, pos: [0, 0, -50]}});
          var ce = G.card({{picture: e, aspect: 40 / 64, w: 2, h: 2, b: 0, pos: [0, 0, -50]}});
          var before = [cp.w, cp.h];
          await p.decode(); await q.decode(); await e.decode();
          var cam = new THREE.PerspectiveCamera(40, {W} / {H}, 0.1, 100); cam.position.set(0, 0, 5); cam.lookAt(0, 0, 0);
          cam.updateMatrixWorld();
          G.update(cam); R.render(scene, cam);
          var at = function (x, y) {{ var t = Kit.project(cam, [x, y, 0], {W}, {H}); return px(Math.round(t.x), Math.round(t.y)); }};
          var pg = cp.group.children[1].geometry.parameters;
          return {{before: before, p: [cp.w, cp.h], q: [cq.w, cq.h], e: [ce.w, ce.h], geo: [pg.width, pg.height],
                   size: cp.u.uSize.value.toArray(), inside: at(0.5, 0.9), outside: at(0.9, 0)}};
        }}""")
        self.assertAlmostEqual(r["before"][0] / r["before"][1], 16 / 9, places=5)
        for k, v in (("p", [1.25, 2]), ("q", [2, 2]), ("e", [1.25, 2]), ("geo", [1.25, 2]), ("size", [1.25, 2])):
            self.assertAlmostEqual(r[k][0], v[0], places=5, msg=k)
            self.assertAlmostEqual(r[k][1], v[1], places=5, msg=k)
        self.assertGreater(r["inside"][0], 200)
        self.assertLess(r["outside"][0], 10)


# kit/beat.js runs on GSAP alone; its tests load gsap.min.js from short-video's node environment and the kit file,
# and the beat_reel technique page with both.
GSAP = NODE_DIR / "node_modules" / "gsap" / "dist" / "gsap.min.js"
TECHNIQUES = KIT.parent / "techniques"
BEAT_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>body{margin:0;background:#000} #stage{position:relative;width:1920px;height:1080px;overflow:hidden}
.layer{position:absolute;inset:0} .mask{overflow:hidden}</style>
<script src="gsap.min.js"></script><script src="kit/beat.js"></script></head><body><div id="stage">
<div id="foot" class="layer"></div><div id="parts" class="layer"></div><div id="word" class="layer">GO</div>
<div id="cap" class="layer"><div class="mask"><div class="ln">one</div></div><div class="mask"><div class="ln">two</div></div></div>
<div id="wipe" class="layer"></div><div id="slices" class="layer"></div><div id="flash" class="layer" style="opacity:0"></div>
</div></body></html>"""


@requires(GSAP.is_file(), f"GSAP at {GSAP}; run short-video.sh setup")
@requires(HYPERFRAMES.exists(), f"HyperFrames at {HYPERFRAMES}; run short-video.sh setup")
class TestBeat(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        folder = Path(cls._tmp.name)
        (folder / "kit").mkdir()
        shutil.copyfile(GSAP, folder / "gsap.min.js")
        shutil.copyfile(KIT / "beat.js", folder / "kit" / "beat.js")
        (folder / "index.html").write_text(BEAT_PAGE, encoding="utf-8")
        reel = folder / "beat_reel"
        shutil.copytree(TECHNIQUES / "beat_reel", reel)
        (reel / "kit").mkdir()
        shutil.copyfile(GSAP, reel / "gsap.min.js")
        shutil.copyfile(KIT / "beat.js", reel / "kit" / "beat.js")
        cls._serve = serve(folder)
        cls.base = cls._serve.__enter__()
        cls.browser = browser()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._serve.__exit__(None, None, None)
        cls._tmp.cleanup()

    def page(self, path: str = "index.html"):
        page = self.browser.new_page(viewport={"width": 1920, "height": 1080})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(self.base + path)
        self.assertEqual(errors, [])
        self.addCleanup(page.close)
        return page

    def test_grid(self) -> None:
        """At 120 bpm a beat is 0.5 s; at, bars, index, snap and list follow the offset."""
        r = self.page().evaluate("""() => {
          var g = Kit.beat.grid(120, {offset: 0.25});
          return {beat: g.beat, bar: g.bar, at: g.at(4), bars: g.bars(2), index: g.index(1.2), snap: g.snap(1.1),
                  list: g.list(1, 3, 2), r1: Kit.beat.rand(7)(), r2: Kit.beat.rand(7)()};
        }""")
        self.assertEqual((r["beat"], r["bar"], r["at"], r["bars"], r["index"], r["snap"]), (0.5, 2, 2.25, 4.25, 1, 1.25))
        self.assertEqual(r["list"], [1.25, 2.25])
        self.assertEqual(r["r1"], r["r2"])
        self.assertTrue(0 <= r["r1"] < 1)

    def test_effects(self) -> None:
        """Seeked on a paused timeline: the flash peaks on its cut frame and is gone after the decay; slice strips
        and the target's filter show only on the frames around the cut; a wipe bar covers the frame centre at the
        cut and none shows after it; a stamped word and a risen caption have opacity 0 outside their windows and
        1 inside; particles are the same at a time whichever way the timeline reached it."""
        r = self.page().evaluate("""() => {
          var tl = gsap.timeline({paused: true}), clock = {t: 0};
          var parts = Kit.beat.particles("#parts", {n: 12, seed: 3, regions: [{x: 100, y: 200, w: 400, h: 300}]});
          tl.to(clock, {t: 4, duration: 4, ease: "none", onUpdate: function () { parts(clock.t); }}, 0);
          Kit.beat.flash(tl, "#flash", 2);
          Kit.beat.slice(tl, "#slices", 2, {seed: 5, target: "#foot"});
          var bars = Kit.beat.wipe(tl, "#wipe", 2);
          Kit.beat.stamp(tl, "#word", 1, {until: 2});
          Kit.beat.rise(tl, "#cap", 2.5, {until: 3.8});
          var op = function (s) { return +getComputedStyle(document.querySelector(s)).opacity; };
          var strips = function () { return Array.from(document.querySelectorAll("#slices > div")).filter(function (s) { return +s.style.opacity > 0; }).length; };
          var covers = function () { return bars.some(function (b) { var q = b.getBoundingClientRect(); return +b.style.opacity > 0 && q.left < 960 && q.right > 960; }); };
          var shown = function () { return bars.filter(function (b) { return +b.style.opacity > 0; }).length; };
          var pos = function () { return parts.elements.map(function (e) { return e.style.transform + e.style.opacity; }).join("|"); };
          var out = {};
          tl.seek(1.5, false); out.p15 = pos(); out.word15 = op("#word");
          tl.seek(0.5, false); out.word05 = op("#word");
          tl.seek(1.97, false); out.strips197 = strips(); out.filter197 = document.querySelector("#foot").style.filter;
          tl.seek(2, false); out.flash2 = op("#flash"); out.covers2 = covers(); out.strips2 = strips(); out.word2 = op("#word");
          tl.seek(2 + 1 / 30 + 0.001, false); out.flash2b = op("#flash");
          tl.seek(2.5, false); out.flash25 = op("#flash"); out.strips25 = strips(); out.shown25 = shown();
          out.filter25 = document.querySelector("#foot").style.filter;
          tl.seek(2.4, false); out.cap24 = op("#cap");
          tl.seek(3.2, false); out.cap32 = op("#cap"); out.ln32 = gsap.getProperty(document.querySelector("#cap .ln"), "yPercent");
          tl.seek(3.9, false); out.cap39 = op("#cap");
          tl.seek(1.5, false); out.p15b = pos();
          out.inside = parts.elements.every(function (e) {
            var m = /translate\\(([-\\d.]+)px,\\s*([-\\d.]+)px\\)/.exec(e.style.transform);
            return +m[1] >= 100 && +m[1] <= 500 && +m[2] >= 200 && +m[2] <= 500; });
          return out;
        }""")
        self.assertEqual((r["word05"], r["word15"], r["word2"]), (0, 1, 0))
        self.assertGreater(r["strips197"], 0)
        self.assertIn("saturate", r["filter197"])
        self.assertEqual(r["flash2"], 1)
        self.assertAlmostEqual(r["flash2b"], 0.55, places=2)
        self.assertEqual(r["flash25"], 0)
        self.assertTrue(r["covers2"])
        self.assertGreater(r["strips2"], 0)
        self.assertEqual((r["strips25"], r["shown25"], r["filter25"]), (0, 0, "none"))
        self.assertEqual((r["cap24"], r["cap32"], r["cap39"], r["ln32"]), (0, 1, 0, 0))
        self.assertEqual(r["p15"], r["p15b"])
        self.assertTrue(r["inside"])

    def test_beat_reel_page(self) -> None:
        """The technique page loads without error, its timeline lasts the root's data-duration, each word shows only
        in its own shot, the flash lands on a cut, and the title holds from the last cut to the end."""
        r = self.page("beat_reel/index.html").evaluate("""() => {
          var tl = window.__timelines["beat_reel"], words = Array.from(document.querySelectorAll("#words .word"));
          var op = function (e) { return +getComputedStyle(e).opacity; };
          var at = function (t) { tl.seek(t, false); return {words: words.map(function (w) { return op(w) > 0.5 ? 1 : 0; }),
            flash: op(document.querySelector("#flash")), title: op(document.querySelector("#final"))}; };
          return {dur: tl.duration(), root: +document.getElementById("root").dataset.duration,
                  t1: at(1), t3: at(3), t5: at(5), t7: at(7), cut: at(4), t85: at(8.5), t94: at(9.4)};
        }""")
        self.assertAlmostEqual(r["dur"], r["root"])
        self.assertEqual([r[k]["words"] for k in ("t1", "t3", "t5", "t7")],
                         [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])
        self.assertEqual(r["cut"]["flash"], 1)
        self.assertEqual((r["t7"]["title"], r["t85"]["title"], r["t94"]["title"]), (0, 1, 1))


# The pipeline_3d technique page with three.js, GSAP and its kit files, in both layouts.
PIPELINE_KIT = ("camera.js", "glow.js", "labels3d.js", "shadow.js", "tiltshift.js", "pipeline.js")


@requires(three_ok(), f"three.js 0.159.0 at {THREE} with the pinned SHA-256; run short-video.sh setup")
@requires(GSAP.is_file(), f"GSAP at {GSAP}; run short-video.sh setup")
@requires(HYPERFRAMES.exists(), f"HyperFrames at {HYPERFRAMES}; run short-video.sh setup")
class TestPipelinePage(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        folder = Path(cls._tmp.name)
        shutil.copytree(TECHNIQUES / "pipeline_3d", folder / "line")
        shutil.copytree(TECHNIQUES / "pipeline_3d", folder / "hub")
        page = (folder / "hub" / "index.html").read_text(encoding="utf-8")
        assert 'const LAYOUT = "line";' in page
        (folder / "hub" / "index.html").write_text(page.replace('const LAYOUT = "line";', 'const LAYOUT = "hub";'),
                                                  encoding="utf-8")
        for sub in ("line", "hub"):
            (folder / sub / "kit").mkdir()
            shutil.copyfile(THREE, folder / sub / "three.min.js")
            shutil.copyfile(GSAP, folder / sub / "gsap.min.js")
            for f in PIPELINE_KIT:
                shutil.copyfile(KIT / f, folder / sub / "kit" / f)
        cls._serve = serve(folder)
        cls.base = cls._serve.__enter__()
        cls.browser = browser()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._serve.__exit__(None, None, None)
        cls._tmp.cleanup()

    def seek(self, layout: str, times: list[float]) -> dict:
        """Load the page in `layout`, seek each time and return in order of `times` the label opacities, the label boxes and
        a hash of the canvas."""
        page = self.browser.new_page(viewport={"width": 1920, "height": 1080})
        self.addCleanup(page.close)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(self.base + layout + "/index.html")
        r = page.evaluate("""(times) => {
          var tl = window.__timelines["pipeline_3d"], labels = Array.from(document.querySelectorAll(".label"));
          var out = {dur: tl.duration(), root: +document.getElementById("root").dataset.duration, at: []};
          times.forEach(function (t) {
            tl.seek(t, false);
            var gl = renderer.getContext(), px = new Uint8Array(4 * gl.drawingBufferWidth * gl.drawingBufferHeight), h = 0;
            gl.readPixels(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight, gl.RGBA, gl.UNSIGNED_BYTE, px);
            for (var i = 0; i < px.length; i += 7) h = (h * 31 + px[i]) % 1000000007;
            out.at.push({op: labels.map(function (e) { return +e.style.opacity; }), canvas: h,
                         boxes: labels.map(function (e) { var b = e.getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; })});
          });
          return out;
        }""", times)
        self.assertEqual(errors, [])
        return r

    def test_line(self) -> None:
        """Line layout: the timeline lasts data-duration; a station's label is out before its time and in after it
        (Transform at 3.6 s, Output at 6.2 s); after the pull back all five labels show inside the frame; the frame
        changes between seconds (the camera travels and the flows run)."""
        r = self.seek("line", [3.0, 4.2, 9.0, 9.5])
        self.assertAlmostEqual(r["dur"], r["root"])
        self.assertEqual(r["at"][0]["op"][2], 0)
        self.assertEqual(r["at"][1]["op"][2], 1)
        self.assertEqual(r["at"][1]["op"][4], 0)
        self.assertEqual(r["at"][2]["op"], [1] * 5)
        for b in r["at"][2]["boxes"]:
            self.assertTrue(0 <= b[0] and b[2] <= 1920 and 0 <= b[1] and b[3] <= 1080, b)
        self.assertNotEqual(r["at"][2]["canvas"], r["at"][3]["canvas"])

    def test_hub(self) -> None:
        """Hub layout: the source label shows from its time, each node's label once its flow arrives (node A at
        1.8 + 1.25 s), and at the end every label is inside the frame."""
        r = self.seek("hub", [0.5, 2.0, 3.6, 9.4])
        self.assertEqual(r["at"][0]["op"][0], 0)
        self.assertEqual(r["at"][1]["op"][0], 1)
        self.assertEqual(r["at"][1]["op"][1], 0)
        self.assertEqual(r["at"][2]["op"][1], 1)
        self.assertEqual(r["at"][3]["op"], [1] * 5)
        for b in r["at"][3]["boxes"]:
            self.assertTrue(0 <= b[0] and b[2] <= 1920 and 0 <= b[1] and b[3] <= 1080, b)


# The gallery_3d technique page with three.js, GSAP and its kit files, in each of its three modes.
GALLERY_KIT = ("camera.js", "glow.js", "tiltshift.js", "gallery.js")
GALLERY_MODES = ("float", "museum", "vortex")


@requires(three_ok(), f"three.js 0.159.0 at {THREE} with the pinned SHA-256; run short-video.sh setup")
@requires(GSAP.is_file(), f"GSAP at {GSAP}; run short-video.sh setup")
@requires(HYPERFRAMES.exists(), f"HyperFrames at {HYPERFRAMES}; run short-video.sh setup")
class TestGalleryPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        folder = Path(cls._tmp.name)
        page = (TECHNIQUES / "gallery_3d" / "index.html").read_text(encoding="utf-8")
        assert 'const MODE = "float";' in page
        for mode in GALLERY_MODES:
            sub = folder / mode
            (sub / "kit").mkdir(parents=True)
            (sub / "index.html").write_text(page.replace('const MODE = "float";', f'const MODE = "{mode}";'),
                                            encoding="utf-8")
            shutil.copyfile(THREE, sub / "three.min.js")
            shutil.copyfile(GSAP, sub / "gsap.min.js")
            for f in GALLERY_KIT:
                shutil.copyfile(KIT / f, sub / "kit" / f)
        cls._serve = serve(folder)
        cls.base = cls._serve.__enter__()
        cls.browser = browser()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._serve.__exit__(None, None, None)
        cls._tmp.cleanup()

    def seek(self, mode: str, times: list[float]) -> dict:
        """Load the page in `mode`, seek each time and return in order of `times` the caption counter, title and
        opacity, the opacity of the end word, the frame x of the left and right edges of each item card and a hash
        of the canvas."""
        page = self.browser.new_page(viewport={"width": 1920, "height": 1080})
        self.addCleanup(page.close)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(self.base + mode + "/index.html")
        r = page.evaluate("""(times) => {
          var tl = window.__timelines["gallery_3d"];
          var out = {dur: tl.duration(), root: +document.getElementById("root").dataset.duration, at: []};
          times.forEach(function (t) {
            tl.seek(t, false);
            var gl = renderer.getContext(), px = new Uint8Array(4 * gl.drawingBufferWidth * gl.drawingBufferHeight), h = 0;
            gl.readPixels(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight, gl.RGBA, gl.UNSIGNED_BYTE, px);
            for (var i = 0; i < px.length; i += 7) h = (h * 31 + px[i]) % 1000000007;
            out.at.push({n: document.querySelector("#cap .n").textContent, of: document.querySelector("#cap .of").textContent,
                         word: document.querySelector("#cap .word").textContent,
                         cap: +getComputedStyle(document.getElementById("cap")).opacity,
                         end: +getComputedStyle(document.getElementById("end")).opacity, canvas: h,
                         edges: items.map(function (it) { var g = it.card.group, p = g.position;
                           return [-1, 1].map(function (s) {
                             var v = new THREE.Vector3(p.x + s * it.card.w / 2, p.y, p.z).project(camera);
                             return (v.x + 1) / 2 * 1920; }); })});
          });
          return out;
        }""", times)
        self.assertEqual(errors, [])
        return r

    def test_float(self) -> None:
        """Float mode: the timeline lasts data-duration; the caption counts the heroes of FLOAT_T (hero 3 of 8 at
        2 s, with its title from PICTURES); the frame changes between frames 1 s apart; no end word."""
        r = self.seek("float", [2.0, 3.0, 2.0])
        self.assertAlmostEqual(r["dur"], r["root"])
        self.assertEqual((r["at"][0]["n"], r["at"][0]["of"], r["at"][0]["word"]), ("03", "08", "Forest"))
        self.assertNotEqual(r["at"][0]["canvas"], r["at"][1]["canvas"])
        self.assertEqual(r["at"][0]["canvas"], r["at"][2]["canvas"])      # a seek back draws the same frame
        self.assertEqual(r["at"][1]["end"], 0)

    def test_museum(self) -> None:
        """Museum mode: one caption item per MUSEUM_T time (6), canvas 4 active at 3.2 s; the frame changes between
        frames 1 s apart through the pull back; the caption is gone after the pull back starts (5.5 s); at
        D - 0.5 s the pull back distance, computed from the row width, shows every canvas whole inside the frame."""
        r = self.seek("museum", [3.2, 4.5, 5.5, 6.5, 7.5])
        self.assertEqual((r["at"][0]["n"], r["at"][0]["of"]), ("04", "06"))
        self.assertEqual(r["at"][0]["cap"], 1)
        for a, b in zip(r["at"], r["at"][1:]):
            self.assertNotEqual(a["canvas"], b["canvas"])
        self.assertEqual(r["at"][3]["cap"], 0)
        edges = [x for pair in r["at"][4]["edges"] for x in pair]
        self.assertTrue(all(0 < x < 1920 for x in edges), edges)
        self.assertGreater(max(edges) - min(edges), 1920 * 0.7)          # and fills most of the width

    def test_vortex(self) -> None:
        """Vortex mode: only the heroes before TV (4.6 s) are counted; the end word is hidden before the flare at
        TV + DV (6.6 s) and shown after it; seeking back before the rush draws the fly-through frame again."""
        r = self.seek("vortex", [3.0, 6.0, 7.5, 3.0])
        self.assertEqual(r["at"][0]["of"], "05")
        self.assertEqual(r["at"][1]["end"], 0)
        self.assertEqual(r["at"][2]["end"], 1)
        self.assertNotEqual(r["at"][0]["canvas"], r["at"][1]["canvas"])
        self.assertEqual(r["at"][0]["canvas"], r["at"][3]["canvas"])
