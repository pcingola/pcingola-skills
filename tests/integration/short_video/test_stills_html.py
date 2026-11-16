"""Integration test of `stills` and `html` with the real HyperFrames snapshot and the render browser: a GSAP scene, an
anime.js scene and a two-scene world, none rendered. `stills` seeks each page in the browser (references/scenes.md,
"Stills"); film.html plays every page in one file and seeks it from its own clock (SKILL.md, "The HTML film")."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

from short_video_tool import config, film_html, pages, scenes, settings, stills, storyboard, world
from tests.integration.short_video.test_kit import LAUNCH_ARGS, chrome
from tests.integration.short_video.wrapper_env import NODE_DIR
from tests.prereq import requires
from tests.unit.short_video.pngs import solid_png

DATA = Path(__file__).resolve().parents[2] / "data"

STORYBOARD = """# Stills test

Topic: A white square slides right in each scene.

## by_gsap
Brief: A white square slides from the left edge to the right.
Length: 2

## by_anime
Brief: A white square slides from the left edge to the right.
Length: 2

## by_three
Brief: A three.js grey ground behind a white box that slides right.
Length: 2

## no_draw
Brief: A three.js page that never draws its canvas.
Length: 2

## left
Brief: The square slides to the centre.
Length: 1
World: track

## right
Brief: The square slides on to the right edge.
Length: 1.5
World: track
"""
PAGE = """<!doctype html>
<html><head><meta charset="UTF-8" />
<script src="{lib}"></script>
<style>
  * {{ margin: 0; padding: 0; }}
  html, body {{ width: 1920px; height: 1080px; overflow: hidden; background: #000; }}
  #root {{ position: relative; width: 1920px; height: 1080px; overflow: hidden; background: #000; }}
  #square {{ position: absolute; left: 0; top: 440px; width: 200px; height: 200px; background: #fff; }}
</style></head>
<body>
<div id="root" data-composition-id="{sid}" data-start="0" data-duration="2" data-full-length
     data-width="1920" data-height="1080" data-fps="30"{attr}>
  <div id="square"></div>
</div>
<script>{script}</script>
</body></html>
"""
GSAP = """
  window.__timelines = window.__timelines || {};
  const tl = gsap.timeline({ paused: true });
  tl.fromTo("#square", { x: 0 }, { x: 1720, duration: 2, ease: "none" }, 0);
  window.__timelines["by_gsap"] = tl;
"""
ANIME = """
  const tl = anime.createTimeline({ autoplay: false });
  tl.add("#square", { translateX: [0, 1720], duration: 2000, ease: "linear" }, 0);
  tl.seek(0);
  window.addEventListener("hf-seek", e => tl.seek(e.detail.time * 1000));
"""
THREE_PAGE = """<!doctype html>
<html><head><meta charset="UTF-8" />
<script src="three.min.js"></script><script src="gsap.min.js"></script>
<style>* {{ margin: 0; padding: 0; }} html, body, #root {{ width: 1920px; height: 1080px; overflow: hidden; background: #000; }}
canvas {{ position: absolute; inset: 0; }}</style></head>
<body>
<div id="root" data-composition-id="{sid}" data-start="0" data-duration="2" data-full-length
     data-width="1920" data-height="1080" data-fps="30"><canvas id="gl" width="1920" height="1080"></canvas></div>
<script>
  const renderer = new THREE.WebGLRenderer({{ canvas: document.getElementById("gl"), preserveDrawingBuffer: true }});
  renderer.setPixelRatio(1); renderer.setSize(1920, 1080, false);
  const scene = new THREE.Scene(); scene.background = new THREE.Color("#808080");
  const camera = new THREE.OrthographicCamera(0, 1920, 540, -540, -10, 10);
  const box = new THREE.Mesh(new THREE.PlaneGeometry(200, 200), new THREE.MeshBasicMaterial({{ color: 0xffffff }}));
  scene.add(box);
  function draw(t) {{ box.position.set(100 + 860 * t, 0, 0); {render} }}
  const clock = {{ t: 0 }};
  const tl = gsap.timeline({{ paused: true }});
  tl.to(clock, {{ t: 2, duration: 2, ease: "none", onUpdate: () => draw(clock.t) }}, 0);
  draw(0);
  window.__timelines = {{ "{sid}": tl }};
</script></body></html>
"""
CASES = {"by_gsap": ("gsap.min.js", GSAP, ""), "by_anime": ("anime.umd.min.js", ANIME, " data-no-timeline")}
SQUARE = """<div id="square" style="position:absolute;left:0;top:440px;width:200px;height:200px;background:#fff"></div>
    <!-- the world's elements here -->"""
MOVE = """const tl = gsap.timeline({ paused: true });
  tl.fromTo("#square", { x: 0 }, { x: 860, duration: STE("left") - ST("left"), ease: "none" }, ST("left"));
  tl.to("#square", { x: 1720, duration: STE("right") - ST("right"), ease: "none" }, ST("right"));"""


def square_x(im: Image.Image, y: int) -> int:
    """The first white column on row `y`."""
    gray = im.convert("L")
    return next(x for x in range(gray.width) if gray.getpixel((x, y)) > 200)


@requires(scenes.node_ready(NODE_DIR, config.NODE_SRC), "HyperFrames node_modules missing; run plugins/media/skills/short-video/scripts/short-video.sh setup")
class TestStillsAndHtml(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.project = p = Path(cls._tmp.name) / "stills_project"
        p.mkdir()
        (p / "storyboard.md").write_text(STORYBOARD, encoding="utf-8")
        settings.use_project(p)
        cls.data = storyboard.load(p)
        for sid, (lib, script, attr) in CASES.items():
            sdir = scenes.scaffold(p, storyboard.scene_by_id(cls.data, sid), NODE_DIR)
            (sdir / "index.html").write_text(PAGE.format(lib=lib, script=script, sid=sid, attr=attr), encoding="utf-8")
        for sid, render in (("by_three", "renderer.render(scene, camera);"), ("no_draw", "")):
            sdir = scenes.scaffold(p, storyboard.scene_by_id(cls.data, sid), NODE_DIR)
            (sdir / "index.html").write_text(THREE_PAGE.format(sid=sid, render=render), encoding="utf-8")
        wdir = world.scaffold(p, cls.data, "track", NODE_DIR)
        html = (wdir / "index.html").read_text()
        html = html.replace("<!-- the world's elements here -->", SQUARE)
        html = html.replace("const tl = gsap.timeline({ paused: true });", MOVE)
        (wdir / "index.html").write_text(html)

    @classmethod
    def tearDownClass(cls) -> None:
        settings.use_project(None)
        cls._tmp.cleanup()

    def stills_of(self, sid: str, times: list[float], **kw) -> list[Path]:
        page = pages.scene_page(self.project, self.data, storyboard.scene_by_id(self.data, sid))
        return stills.stills(sid, page, times, NODE_DIR, **kw)

    def test_stills_of_page_scenes(self) -> None:
        """stills of the GSAP and the anime.js scene, unrendered, show the square 430 and 860 px right at 0.5 s and
        1 s. Guards `stills` seeking a page through window.__timelines and hf-seek without an MP4."""
        for sid in CASES:
            with self.subTest(sid):
                paths = self.stills_of(sid, [0.5, 1.0])
                self.assertEqual([p.name for p in paths], ["at_000.500.png", "at_001.000.png"])
                self.assertEqual([square_x(Image.open(p), 540) for p in paths], [430, 860])
                self.assertFalse((paths[0].parent.parent / "scene.mp4").exists())

    def test_stills_of_three_page_cold_seek(self) -> None:
        """A single cold still of a three.js page at 1.5 s shows the grey ground and the white box 1290 px right, not
        a black canvas, three times in a row. Guards the warm-up seek before each still: on a hardware GPU the first
        draw after a cold seek came out black."""
        for run in range(3):
            with self.subTest(run=run):
                [path] = self.stills_of("by_three", [1.5])
                im = Image.open(path).convert("RGB")
                self.assertFalse(stills.is_blank(path))
                self.assertEqual(im.getpixel((200, 200)), (128, 128, 128))
                self.assertAlmostEqual(square_x(im, 540), 1290, delta=4)

    def test_stills_of_blank_webgl_page_fail(self) -> None:
        """A three.js page that never draws gives a blank still twice (taken again once) and `stills` fails naming
        the time. Guards against handing a black canvas over as a still."""
        with self.assertRaisesRegex(scenes.SceneError, r"page times 1 s are blank twice"):
            self.stills_of("no_draw", [1.0])

    def test_black_fraction_and_blank(self) -> None:
        """With FFmpeg decoding, an all-black PNG is blank and a near-black (#050505) one is not. Guards the exact
        #000000 test of a still."""
        with tempfile.TemporaryDirectory() as d:
            black = solid_png(Path(d) / "black.png", 64, 36, (0, 0, 0))
            near = solid_png(Path(d) / "near.png", 64, 36, (5, 5, 5))
            self.assertEqual(stills.black_fraction(black), 1.0)
            self.assertTrue(stills.is_blank(black))
            self.assertEqual(stills.black_fraction(near), 0.0)
            self.assertFalse(stills.is_blank(near))

    def test_stills_of_world_scene(self) -> None:
        """stills of the world scene `right` at scene times 0 and 0.75 s show the square at 860 and 1290 px, the
        world page at start + t; --mark and --sheet add a marked copy and a contact sheet. Guards scene-local
        times of a world scene, the mark and the sheet."""
        paths = self.stills_of("right", [0.0, 0.75], mark=stills.Mark(100, 100, 300, 200), sheet=True)
        self.assertEqual([p.name for p in paths], ["right_at_000.000.png", "right_at_000.750.png",
                                                   "right_at_000.000_mark.png", "right_at_000.750_mark.png",
                                                   "right_sheet.png"])
        self.assertEqual([square_x(Image.open(p), 540) for p in paths[:2]], [860, 1290])
        marked = Image.open(paths[2]).convert("RGB")
        self.assertEqual(marked.getpixel((102, 150)), (255, 0, 0))
        self.assertNotEqual(Image.open(paths[0]).convert("RGB").getpixel((102, 150)), (255, 0, 0))
        c = settings.get()["contact_sheet"]
        self.assertEqual(Image.open(paths[4]).width, 2 * c["width"])

    def test_html_film_seeks(self) -> None:
        """film.html, opened from file:// in the render browser, plays the six scenes in order and, seeked to a
        time in the GSAP scene, the anime.js scene and the world's second scene, shows the square where its page
        puts it. Guards the standalone film: inlined pages, the player's clock and seek, and the world spanning
        its scenes."""
        # Under tests/data, not /tmp: a snap-packaged Chromium reads no file:// page from the host's /tmp.
        DATA.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=DATA, prefix="tmp_film_") as shots, sync_playwright() as pw:
            out, warnings = film_html.write(self.project, self.data, NODE_DIR, Path(shots) / "film.html")
            self.assertEqual(warnings, ["world track: font 'Inter' is not embedded; film.html shows another font on "
                                        "a machine without it. Copy an OFL font file into the page's fonts/ and "
                                        "load it with @font-face"])
            browser = pw.chromium.launch(executable_path=chrome(), args=LAUNCH_ARGS)
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 840})
                page.goto(out.as_uri())
                page.evaluate("() => film.ready")
                self.assertEqual(page.evaluate("() => [film.segments, film.duration]"), [5, 10.5])
                stage = page.locator("#stage")
                scale = stage.bounding_box()["width"] / 1920
                for t, x in [(0.5, 430), (3.0, 860), (9.75, 1290)]:
                    with self.subTest(t=t):
                        page.evaluate("t => film.seek(t)", t)
                        shot = Path(shots) / f"film_{t}.png"
                        stage.screenshot(path=str(shot))
                        im = Image.open(shot)
                        self.assertAlmostEqual(square_x(im, round(540 * scale)) / scale, x, delta=6)
            finally:
                browser.close()

    def test_html_film_opens_at_fragment(self) -> None:
        """film.html#t=9.75 opens paused at 9.75 s with the world's square at 1290 px. Guards checking the film at a
        given time from a URL."""
        DATA.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=DATA, prefix="tmp_film_") as shots, sync_playwright() as pw:
            out, _ = film_html.write(self.project, self.data, NODE_DIR, Path(shots) / "film.html")
            browser = pw.chromium.launch(executable_path=chrome(), args=LAUNCH_ARGS)
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 840})
                page.goto(out.as_uri() + "#t=9.75")
                page.evaluate("() => film.opened")
                self.assertEqual(page.evaluate("() => [film.time, film.playing]"), [9.75, False])
                stage = page.locator("#stage")
                scale = stage.bounding_box()["width"] / 1920
                shot = Path(shots) / "film_fragment.png"
                stage.screenshot(path=str(shot))
                self.assertAlmostEqual(square_x(Image.open(shot), round(540 * scale)) / scale, 1290, delta=6)
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
