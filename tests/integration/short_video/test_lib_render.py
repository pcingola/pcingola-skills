"""Integration test of anime.js and Motion scenes with the real HyperFrames renderer: two silent scenes (`Length:`)
whose pages have `data-no-timeline` and seek their timeline in an `hf-seek` listener (references/scenes.md,
"Library files"). Their library file is named only after scaffold, so render copies it."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from short_video_tool import config, scenes, settings, storyboard
from tests.prereq import requires
from tests.integration.short_video.wrapper_env import NODE_DIR

STORYBOARD = """# Library test

Topic: A white square slides right, once with anime.js and once with Motion.

## by_anime
Brief: A white square slides from the left edge to the right.
Length: 1.5

## by_motion
Brief: A white square slides from the left edge to the right.
Length: 1.5
"""
PAGE = """<!doctype html>
<html><head><meta charset="UTF-8" />
<script src="{lib}"></script>
<style>
  * {{ margin: 0; padding: 0; }}
  html, body {{ width: {w}px; height: {h}px; overflow: hidden; background: #000; }}
  #root {{ position: relative; width: {w}px; height: {h}px; overflow: hidden; }}
  #bg-fill {{ position: absolute; inset: 0; background: #000; }}
  #square {{ position: absolute; left: 0; top: {top}px; width: 200px; height: 200px; background: #fff; }}
</style></head>
<body>
<div id="root" data-composition-id="{sid}" data-start="0" data-duration="1.5" data-full-length
     data-width="{w}" data-height="{h}" data-fps="{fps}" data-no-timeline>
  <div id="bg-fill" class="clip" data-start="0" data-duration="1.5" data-full-length data-track-index="0"></div>
  <div id="square"></div>
</div>
<script>{script}</script>
</body></html>
"""
ANIME = """
  const tl = anime.createTimeline({ autoplay: false });
  tl.add("#square", { translateX: [0, 1200], duration: 1500, ease: "linear" }, 0);
  tl.seek(0);
  window.addEventListener("hf-seek", e => tl.seek(e.detail.time * 1000));
"""
MOTION = """
  const anim = Motion.animate("#square", { x: [0, 1200] }, { duration: 1.5, ease: "linear" });
  anim.pause();
  anim.time = 0;
  window.addEventListener("hf-seek", e => {
    anim.time = e.detail.time;
    e.detail.waitUntil(new Promise(r => Motion.frame.postRender(() => r())));
  });
"""
CASES = {"by_anime": ("anime.umd.min.js", ANIME), "by_motion": ("motion.js", MOTION)}


@requires(scenes.node_ready(NODE_DIR, config.NODE_SRC), "HyperFrames node_modules missing; run plugins/media/skills/short-video/scripts/short-video.sh setup")
class TestLibRender(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.project = p = Path(cls._tmp.name) / "lib_project"
        p.mkdir()
        (p / "storyboard.md").write_text(STORYBOARD, encoding="utf-8")
        settings.use_project(p)
        data = storyboard.load(p)
        v = settings.get()["video"]
        cls.height = v["height"]
        cls.top = v["height"] // 2 - 100
        cls.outs = {}
        for scene in data["scenes"]:
            lib, script = CASES[scene["id"]]
            sdir = scenes.scaffold(p, scene, NODE_DIR)
            (sdir / "index.html").write_text(PAGE.format(lib=lib, script=script, sid=scene["id"], w=v["width"],
                                                         h=v["height"], fps=v["fps"], top=cls.top), encoding="utf-8")
            cls.outs[scene["id"]] = scenes.render(p, scene, NODE_DIR)

    @classmethod
    def tearDownClass(cls) -> None:
        settings.use_project(None)
        cls._tmp.cleanup()

    def _square_x(self, path: Path, t: float) -> int:
        """The first white column of the frame at `t` on the square's middle row."""
        width = settings.get()["video"]["width"]
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(path), "-frames:v", "1",
                              "-vf", f"crop={width}:1:0:{self.top + 100},format=gray", "-f", "rawvideo", "-"],
                             check=True, capture_output=True).stdout
        return next(i for i, b in enumerate(raw) if b > 240)

    def test_installed_libs_match_pins(self) -> None:
        """scenes.lib_failures finds every LIBS file installed by setup with its pinned SHA-256. Guards the
        package-lock.json resolving to the pinned files."""
        self.assertEqual(scenes.lib_failures(NODE_DIR), [])

    def test_square_moves(self) -> None:
        """In each scene the square starts at the left edge and is about 600 px right at 0.75 s, and render copied
        the library file the page names. Guards anime.js and Motion seeking through hf-seek under HyperFrames."""
        for sid, out in self.outs.items():
            with self.subTest(sid):
                self.assertTrue((out.parent / CASES[sid][0]).is_file())
                self.assertLess(self._square_x(out, 0.0), 10)
                self.assertAlmostEqual(self._square_x(out, 0.75), 600, delta=60)


if __name__ == "__main__":
    unittest.main()
