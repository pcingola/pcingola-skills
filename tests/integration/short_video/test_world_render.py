"""Integration test of a shared world with the real HyperFrames renderer: two silent scenes (`Length:`), one GSAP
page across both, rendered once and cut into one scene.mp4 per scene (references/storyboard.md, "Shared worlds")."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from short_video_tool import config, media, mix, scenes, settings, state, status, storyboard, world
from tests.prereq import requires
from tests.integration.short_video.fast_render import set_fps
from tests.integration.short_video.wrapper_env import NODE_DIR

STORYBOARD = """# World test

Topic: A square crosses one world over two scenes.

## left
Brief: A white square slides from the left edge to the centre.
Length: 1
World: track

## right
Brief: The square slides on from the centre to the right edge.
Length: 1.5
World: track
"""
SQUARE = """<div id="square" style="position:absolute;left:0;top:440px;width:200px;height:200px;background:#fff"></div>
    <!-- the world's elements here -->"""
MOVE = """const tl = gsap.timeline({ paused: true });
  tl.fromTo("#square", { x: 0 }, { x: 860, duration: STE("left") - ST("left"), ease: "none" }, ST("left"));
  tl.to("#square", { x: 1720, duration: STE("right") - ST("right"), ease: "none" }, ST("right"));"""


@requires(scenes.node_ready(NODE_DIR, config.NODE_SRC), "HyperFrames node_modules missing; run plugins/media/skills/short-video/scripts/short-video.sh setup")
class TestWorldRender(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.project = p = Path(cls._tmp.name) / "world_project"
        p.mkdir()
        (p / "storyboard.md").write_text(STORYBOARD, encoding="utf-8")
        set_fps(p)
        settings.use_project(p)
        cls.data = storyboard.load(p)
        cls.fps = settings.get()["video"]["fps"]
        cls.wdir = world.scaffold(p, cls.data, "track", NODE_DIR)
        html = (cls.wdir / "index.html").read_text()
        html = html.replace("<!-- the world's elements here -->", SQUARE)
        html = html.replace("const tl = gsap.timeline({ paused: true });", MOVE)
        (cls.wdir / "index.html").write_text(html)
        cls.outs = world.render(p, cls.data, "track", NODE_DIR)

    @classmethod
    def tearDownClass(cls) -> None:
        settings.use_project(None)
        cls._tmp.cleanup()

    def test_one_clip_per_scene_with_its_frames(self) -> None:
        """world.render writes scenes/<id>/v1/scene.mp4 for both scenes, with 1 s and 1.5 s worth of frames and a
        silent audio track. Guards the frame-aligned cut of the world's render."""
        self.assertEqual(self.outs, [self.project / "scenes" / sid / "v1" / "scene.mp4" for sid in ("left", "right")])
        for out, frames in zip(self.outs, (self.fps, round(1.5 * self.fps))):
            streams = media.probe(out)["streams"]
            video = next(s for s in streams if s["codec_type"] == "video")
            self.assertEqual(int(video["nb_frames"]), frames, out)
            self.assertIn("audio", [s["codec_type"] for s in streams])

    def test_meta_and_status(self) -> None:
        """Each cut's meta.json names the world, its version and the scene's start, with no voice version, and
        status reports nothing to redo. Guards the per-scene records of a world render."""
        metas = [state.read_meta(out.parent) for out in self.outs]
        self.assertEqual([(m["world"], m["world_version"], m["start"], "voice_version" in m) for m in metas],
                         [("track", "v1", 0.0, False), ("track", "v1", 1.0, False)])
        self.assertEqual([s["render_reasons"] for s in status.report(self.project, self.data)["scenes"]], [[], []])

    def test_motion_continues_across_the_cut(self) -> None:
        """The square is one frame's travel short of the centre on the last frame of `left` (860 px/s over 1 s) and
        at the centre on the first frame of `right`. Guards one timeline running on across the scene boundary."""
        def square_x(path: Path, t: float) -> int:
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", str(path), "-frames:v", "1",
                                  "-vf", "crop=1920:1:0:540,format=gray", "-f", "rawvideo", "-"],
                                 check=True, capture_output=True).stdout
            return next(i for i, b in enumerate(raw) if b > 240)

        end_left = square_x(self.outs[0], 1.0 - 1 / self.fps)
        start_right = square_x(self.outs[1], 0.0)
        self.assertAlmostEqual(end_left, 860 * (1 - 1 / self.fps), delta=10)
        self.assertAlmostEqual(start_right, 860, delta=10)

    def test_assemble_silent_film(self) -> None:
        """mix.assemble joins the two silent scenes into a 2.5 s film with an audio track; the loudness pass skips
        normalisation when the measured loudness is -inf. Guards a film where no scene has sound."""
        film = mix.assemble(self.project, self.data)
        self.assertAlmostEqual(media.duration(film), 2.5, delta=0.1)
        self.assertIn("audio", [s["codec_type"] for s in media.probe(film)["streams"]])


if __name__ == "__main__":
    unittest.main()
