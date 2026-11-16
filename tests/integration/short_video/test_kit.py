"""The short-video kit (`assets/kit/*.js`) in headless Chromium: each helper is called on a test page that loads
three.js 0.159.0 and the kit as classic scripts, and the test asserts on what it computes or draws. three.js comes
from short-video's node environment and Chromium from HyperFrames (`hyperframes browser path`), the ones scene
renders use. The page is served from a local HTTP server because a snap Chromium cannot read the system /tmp."""
from __future__ import annotations

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

from playwright.sync_api import sync_playwright

from short_video_tool import config
from tests.integration.short_video.wrapper_env import NODE_DIR
from tests.prereq import requires

KIT = config.SCRIPTS_DIR.parent / "assets" / "kit"
KIT_FILES = ("camera.js", "labels3d.js", "glow.js", "shadow.js", "ribbon.js", "tiltshift.js")
THREE_SHA = "7b1c5d75b28d9de15042e2b374f83566d8c7146697af8fdeb4558b0fb528a585"
THREE = NODE_DIR / "node_modules" / "three" / "build" / "three.min.js"
HYPERFRAMES = NODE_DIR / "node_modules" / ".bin" / "hyperframes"
LAUNCH_ARGS = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--hide-scrollbars"]
W, H = 640, 360


def three_ok() -> bool:
    return THREE.is_file() and hashlib.sha256(THREE.read_bytes()).hexdigest() == THREE_SHA


def chrome() -> str:
    done = subprocess.run([str(HYPERFRAMES), "browser", "path"], cwd=NODE_DIR, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip().splitlines()[-1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass


@contextmanager
def serve(folder: Path):
    """Serve `folder` on 127.0.0.1 and yield its base URL."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(folder)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
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
        cls._serve = serve(cls.folder)
        cls.url = cls._serve.__enter__() + "index.html"
        cls._pw = sync_playwright().start()
        cls.browser = cls._pw.chromium.launch(executable_path=chrome(), args=LAUNCH_ARGS)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.browser.close()
        cls._pw.stop()
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


def still(out: Path, width: int = 1280, height: int = 720) -> Path:
    """Render the combined still to `out` (PNG)."""
    with tempfile.TemporaryDirectory() as tmp:
        build_page(Path(tmp), width, height)
        with serve(Path(tmp)) as base, sync_playwright() as pw:
            url = base + "index.html"
            browser = pw.chromium.launch(executable_path=chrome(), args=LAUNCH_ARGS)
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(url)
            page.evaluate(STILL_JS)
            page.locator("#stage").screenshot(path=str(out))
            browser.close()
    return out
