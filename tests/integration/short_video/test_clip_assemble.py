"""Integration test: a film of an image scene, a clip scene without narration
(a transition) imported with `clip`, and a second image scene, assembled
with real FFmpeg. The image scenes are rendered versions made with FFmpeg
lavfi as `render` leaves them (test_assemble.py does the same); the clip is
an FFmpeg testsrc at the project's `video:` size and fps."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from short_video_tool import clip, media, mix, settings, state, storyboard, versions
from tests.prereq import requires

W, H, FPS = 320, 180, 30
IMAGE_SCENES = {"drawing": 3.0, "photo": 2.5}
CLIP_SECONDS = 2.0

MD = """\
# Clip film

Topic: A drawing turns into a photograph.

## drawing
Image: a.png
Brief: Hold.

| Narration | On screen |
|---|---|
| A drawing of the lab. | hold |

## morph
Engine: clip
Brief: The drawing turns into the photograph.

## photo
Image: a.png
Brief: Hold.

| Narration | On screen |
|---|---|
| The same lab today. | hold |
"""


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True, timeout=25)


@requires(shutil.which("ffmpeg") is not None, "ffmpeg not installed (brew install ffmpeg)")
class TestClipFilm(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.project = p = Path(cls._tmp.name) / "clip_film"
        for d in ("images", "sources", "voice", "scenes", "music", "film"):
            (p / d).mkdir(parents=True)
        _ffmpeg("-f", "lavfi", "-i", f"color=c=gray:s={W}x{H}", "-frames:v", "1", str(p / "images" / "a.png"))
        (p / "storyboard.md").write_text(MD, encoding="utf-8")
        (p / "settings.yaml").write_text(f"author: [Jane Doe]\nvideo: {{width: {W}, height: {H}, fps: {FPS}}}\n",
                                         encoding="utf-8")
        settings.use_project(p)
        cls.data = storyboard.load(p)

        for sid, dur in IMAGE_SCENES.items():
            vdir = versions.next_version(state.voice_root(p, sid))
            state.write_meta(vdir, {"duration": dur})
            sdir = versions.next_version(state.scene_root(p, sid))
            _ffmpeg("-f", "lavfi", "-i", f"color=c=blue:s={W}x{H}:r={FPS}:d={dur}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=24000:duration={dur}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(sdir / "scene.mp4"))
            state.write_meta(sdir, {"voice_version": vdir.name, "duration": dur})

        src = Path(cls._tmp.name) / "morph.mp4"
        _ffmpeg("-f", "lavfi", "-i", f"testsrc=size={W}x{H}:rate={FPS}:duration={CLIP_SECONDS}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src))
        cls.clip_mp4 = clip.import_clip(p, storyboard.scene_by_id(cls.data, "morph"), src)
        cls.film = mix.assemble(p, cls.data)

    @classmethod
    def tearDownClass(cls) -> None:
        settings.use_project(None)
        cls._tmp.cleanup()

    def test_film_length_is_sum_of_scenes(self) -> None:
        """mix.assemble of image, silent clip and image scenes gives a film, audio and video, as long as the sum
        of the scene lengths, the clip scene its imported length. Guards the silent clip's anullsrc audio and
        the concat of clip and rendered scenes."""
        scene_seconds = [media.video_duration(state.latest_render(self.project, s["id"]) / "scene.mp4")
                         for s in storyboard.scenes(self.data)]
        self.assertAlmostEqual(scene_seconds[1], CLIP_SECONDS, delta=1 / FPS)
        self.assertAlmostEqual(media.duration(self.film), sum(scene_seconds), delta=1 / FPS)
        video = next(s for s in media.probe(self.film)["streams"] if s["codec_type"] == "video")
        self.assertAlmostEqual(float(video["duration"]), sum(scene_seconds), delta=1 / FPS)

    def test_manifest(self) -> None:
        """mix.assemble records voice_version null for the silent clip, and mix.film_sources lists only the
        narrated scenes' narration. Guards audiocheck --film on films with silent clips."""
        manifest = json.loads((self.film.parent / "manifest.json").read_text())
        self.assertEqual([(s["id"], s["voice_version"]) for s in manifest["scenes"]],
                         [("drawing", "v1"), ("morph", None), ("photo", "v1")])
        self.assertEqual(mix.film_sources(self.project, manifest["version"]),
                         [self.project / "voice" / sid / "v1" / "narration.wav" for sid in IMAGE_SCENES])

    def test_validate_and_estimate_use_the_clip(self) -> None:
        """storyboard.validate after clip.import_clip gives no warning for the clip scene and an estimate
        counting its imported length. Guards the meta.json fields import_clip writes being the ones validate and
        the estimate read."""
        v = storyboard.validate(self.data, self.project)
        self.assertEqual([w for w in v.warnings if w.startswith("scene morph")], [])
        words = 5 + 4
        per = settings.get()["length"]["words_per_second"]
        self.assertAlmostEqual(v.estimated_seconds, words / per + CLIP_SECONDS, delta=0.05)


if __name__ == "__main__":
    unittest.main()
