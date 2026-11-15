"""short_video_tool.video_scene and `Engine: video` in the storyboard: parsing,
validation errors, the fill-to-duration filter, the scaffold of a video scene
(references/video-model.md, references/storyboard.md "Video scenes")."""
import array
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.prereq import requires
from short_video_tool import scenes, settings, state, status, storyboard, versions, video_scene
from short_video_tool.engine import Engine

MD = """\
# Video

Topic: Cells.

## swim
Engine: video
Image: a.png
Brief: The cell drifts to the right, the camera follows slowly.

| Narration | On screen |
|---|---|
| The cell moves. | drift |
"""

JSON_SCENE = {"id": "swim", "engine": "video", "image": "a.png", "brief": "Drift.",
              "narration": ["The cell moves."], "beats": ["drift"]}

TIMING = {
    "audio": "narration.wav", "sample_rate": 24000, "duration": 3.5, "backend": "kokoro", "voice": "af_heart",
    "speed": 1.0, "sentences": [{"index": 1, "text": "The cell moves.", "start": 0.25, "end": 3.0, "aligned": True,
                                 "words": [{"text": "The", "start": 0.25, "end": 0.4}]}],
}


def _error(text: str) -> str:
    with unittest.TestCase().assertRaises(storyboard.StoryboardError) as cm:
        storyboard.parse_markdown(text)
    return str(cm.exception)


class TestEngine(unittest.TestCase):

    def test_enum(self) -> None:
        """Engine lists the five engines, storyboard.ENGINES follows it, and Engine.of defaults to html.
        Guards one fixed set of engine names."""
        self.assertEqual(storyboard.ENGINES, ("html", "manim", "clip", "video", "presenter"))
        self.assertEqual(Engine.of({}), Engine.HTML)
        self.assertEqual(Engine.of({"engine": "video"}), Engine.VIDEO)


class TestStoryboard(unittest.TestCase):

    def test_parse(self) -> None:
        """storyboard.parse_markdown reads a video scene with its Image and Brief, and is_video tells it from an
        html scene. Guards `Engine: video` in storyboard.md."""
        scene = storyboard.parse_markdown(MD)["scenes"][0]
        self.assertEqual(scene, {"id": "swim", "engine": "video", "image": "a.png",
                                 "brief": "The cell drifts to the right, the camera follows slowly.",
                                 "narration": ["The cell moves."], "beats": ["drift"]})
        self.assertTrue(storyboard.is_video(scene))
        self.assertFalse(storyboard.is_video(dict(scene, engine="html")))

    def test_json(self) -> None:
        """storyboard.parse_json accepts a video scene and refuses one without `image`. Guards the same rules
        in storyboard.json."""
        data = {"title": "T", "topic": "x", "scenes": [JSON_SCENE]}
        self.assertEqual(storyboard.parse_json(json.dumps(data))["scenes"][0]["engine"], "video")
        bad = {"title": "T", "topic": "x", "scenes": [{k: v for k, v in JSON_SCENE.items() if k != "image"}]}
        with self.assertRaisesRegex(storyboard.StoryboardError,
                                    "scene 'swim': missing `image`; a scene with `engine` video animates"):
            storyboard.parse_json(json.dumps(bad))

    def test_errors(self) -> None:
        """storyboard.parse_markdown refuses a video scene without Image, without Brief, or with a Template, and
        a video scene without a table. Guards the rules of references/storyboard.md "Video scenes"."""
        cases = [
            ("Image: a.png\n", "", "scene 'swim': missing `Image:`; an `Engine: video` scene animates that image"),
            ("Brief: The cell drifts to the right, the camera follows slowly.\n", "", "scene 'swim': missing `Brief:`"),
            ("Image: a.png\n", "Template: title\n", "a template scene takes no `Engine:`"),
            ("| Narration | On screen |\n|---|---|\n| The cell moves. | drift |\n", "",
             "scene 'swim': missing the `| Narration | On screen |` table"),
        ]
        for old, new, fragment in cases:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, _error(MD.replace(old, new, 1)))


class TestAmbienceKey(unittest.TestCase):

    def setUp(self) -> None:
        settings.use_project(None)

    def test_parse(self) -> None:
        """`Ambience: off` and `Ambience: on` in a video scene parse to `ambience` False and True; without the key
        the scene has none. Guards a storyboard.md scene turning its ambience off."""
        for value, parsed in (("off", False), ("on", True), ("Off", False)):
            with self.subTest(value=value):
                scene = storyboard.parse_markdown(MD.replace("Image: a.png\n", f"Image: a.png\nAmbience: {value}\n"))
                self.assertIs(scene["scenes"][0]["ambience"], parsed)
        self.assertNotIn("ambience", storyboard.parse_markdown(MD)["scenes"][0])

    def test_errors(self) -> None:
        """storyboard.md refuses an `Ambience:` other than on or off, and `Ambience:` on a scene that is not a
        video scene; storyboard.json refuses a non-boolean `ambience`. Guards the one key both files share."""
        self.assertIn("scene 'swim': `Ambience:` must be on or off",
                      _error(MD.replace("Image: a.png\n", "Image: a.png\nAmbience: quiet\n")))
        self.assertIn("scene 'swim': only an `Engine: video` scene has `Ambience:`",
                      _error(MD.replace("Engine: video\n", "Ambience: off\n")))
        bad = {"title": "T", "topic": "x", "scenes": [dict(JSON_SCENE, ambience="off")]}
        with self.assertRaisesRegex(storyboard.StoryboardError, "`ambience` must be true or false"):
            storyboard.parse_json(json.dumps(bad))


def _ffmpeg(*args) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *map(str, args)], check=True)


def _samples(path: Path, start: float, end: float) -> array.array:
    """The float samples (channels interleaved) of `path` between `start` and `end` seconds."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-af", f"atrim={start}:{end}", "-f", "f32le",
                          "-"], capture_output=True, check=True).stdout
    return array.array("f", raw)


@requires(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg and ffprobe not installed")
class TestAmbienceMix(unittest.TestCase):
    """video_scene.mix_ambience with the real FFmpeg on a generated narration and generated clips with sound."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = d = Path(self._tmp.name)
        settings.use_project(d)
        (d / settings.PROJECT_FILE).write_text(
            "mix: {ambience_relative_db: -15.0, ambience_max_gain_db: 10.0, ambience_fade: 0.1}\n")
        self.narration = d / "narration.wav"  # 3 s of a 330 Hz tone
        _ffmpeg("-f", "lavfi", "-i", "sine=frequency=330:sample_rate=24000:duration=3", self.narration)
        self.clip = self._clip("model.mp4", 0)

    def _clip(self, name: str, db: float) -> Path:
        """2 s of picture with a 1 kHz tone at `db` from the sine source's level."""
        path = self.dir / name
        _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=128x96:rate=24:duration=2", "-f", "lavfi", "-i",
                "sine=frequency=1000:sample_rate=48000:duration=2", "-af", f"volume={db}dB", "-ac", 2,
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", path)
        return path

    def tearDown(self) -> None:
        settings.use_project(None)
        self._tmp.cleanup()

    def test_gain(self) -> None:
        """ambience_gain puts the ambience `relative_db` LU from the narration and caps the gain. Guards a
        near-silent model track raised into noise."""
        self.assertEqual(video_scene.ambience_gain(-22.0, -30.0, -15.0, 10.0), -7.0)
        self.assertEqual(video_scene.ambience_gain(-22.0, -60.0, -15.0, 10.0), 10.0)
        self.assertEqual(video_scene.ambience_gain(-22.0, float("-inf"), -15.0, 10.0), 10.0)

    def test_mix(self) -> None:
        """mix_ambience measures narration and clip with ebur128, levels the clip's sound 15 LU under the
        narration, writes the film's 48 kHz stereo as long as the scene, and leaves the narration alone after
        the clip ends. Guards model tracks of different loudness reaching the scene at the same level."""
        out = self.dir / video_scene.AUDIO_WAV
        m = video_scene.mix_ambience(self.narration, self.clip, out, 2.0, 3.0)
        self.assertAlmostEqual(m["ambience_lufs"] + m["ambience_gain_db"], m["narration_lufs"] - 15.0, delta=0.01)
        louder = self._clip("louder.mp4", 6)
        m2 = video_scene.mix_ambience(self.narration, louder, self.dir / "b.wav", 2.0, 3.0)
        self.assertAlmostEqual(m2["ambience_gain_db"], m["ambience_gain_db"] - 6.0, delta=0.3)
        a = next(s for s in scenes.media.probe(out)["streams"] if s["codec_type"] == "audio")
        self.assertEqual((int(a["sample_rate"]), a["channels"]), (settings.get()["mix"]["sample_rate"], 2))
        self.assertAlmostEqual(scenes.media.duration(out), 3.0, delta=0.02)
        # FFmpeg's mono to stereo upmix puts the narration at -3 dB per channel, the same loudness
        voice_tail = max(abs(x) for x in _samples(self.narration, 2.2, 3.0)) * 2 ** -0.5
        self.assertAlmostEqual(max(abs(x) for x in _samples(out, 2.2, 3.0)), voice_tail, delta=0.002)

    def test_quiet_track_capped(self) -> None:
        """A track 60 dB under the tone gets the capped gain, `mix.ambience_max_gain_db`. Guards a near-silent
        model track raised into noise."""
        quiet = self._clip("quiet.mp4", -60)
        m = video_scene.mix_ambience(self.narration, quiet, self.dir / "q.wav", 2.0, 3.0)
        self.assertEqual(m["ambience_gain_db"], 10.0)

    def test_level(self) -> None:
        """ambience_level is `mix.ambience_relative_db` for a clip with sound, and None for `ambience` False or a
        clip without an audio stream (a model that generates no sound, such as LTX-Video 0.9.5). Guards today's
        narration-only scenes staying as they are, and `status` comparing the level a render recorded."""
        silent = self.dir / "silent.mp4"
        _ffmpeg("-i", self.clip, "-an", "-c:v", "copy", silent)
        self.assertEqual(video_scene.ambience_level(JSON_SCENE, self.clip), -15.0)
        self.assertIsNone(video_scene.ambience_level(dict(JSON_SCENE, ambience=False), self.clip))
        self.assertIsNone(video_scene.ambience_level(JSON_SCENE, silent))

    def test_filter(self) -> None:
        """ambience_filter fades the ambience in and out within the shorter of clip and scene, applies the gain,
        pads it to the scene and mixes it with the narration without normalizing. Guards a longer clip's sound
        running past the scene and the fades ending at the clip's end."""
        f = video_scene.ambience_filter(5.0, 3.0, -7.5)
        self.assertIn("atrim=0:3,", f)
        self.assertIn("afade=t=out:st=2.9:d=0.1", f)
        self.assertIn("volume=-7.5dB", f)
        self.assertIn("apad=whole_dur=3[amb]", f)
        self.assertIn("amix=inputs=2:normalize=0", f)


class TestFill(unittest.TestCase):

    def setUp(self) -> None:
        settings.use_project(None)
        v, e = settings.get()["video"], settings.encode()
        self.size, self.fps, self.pix = (v["width"], v["height"]), v["fps"], e["pixel_format"]

    def test_short_clip_holds_last_frame(self) -> None:
        """video_scene.fill_filter scales and crops to the `video:` frame, sets fps, SAR and pixel format, and
        holds the last frame for the time the scene runs past a shorter clip. Guards a 5 s model clip filling a
        7.25 s scene."""
        w, h = self.size
        self.assertEqual(video_scene.fill_filter(5.0, 7.25),
                         f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={self.fps},"
                         f"setsar=1,format={self.pix},tpad=stop_mode=clone:stop_duration=2.25")

    def test_long_clip_not_padded(self) -> None:
        """video_scene.fill_filter adds no hold when the clip is as long as the scene or longer. Guards padding
        only a short clip."""
        self.assertNotIn("tpad", video_scene.fill_filter(8.0, 7.25))
        self.assertNotIn("tpad", video_scene.fill_filter(7.25, 7.25))

    def test_command_cuts_at_scene_length(self) -> None:
        """video_scene.fill_command cuts the output at the scene length with `-t`, after the fill filter, with
        no audio. Guards a longer model clip setting the scene length."""
        cmd = [str(c) for c in video_scene.fill_command(Path("in.mp4"), Path("out.mp4"), 8.0, 7.25)]
        self.assertEqual(cmd[cmd.index("-t") + 1], "7.25")
        self.assertEqual(cmd[cmd.index("-vf") + 1], video_scene.fill_filter(8.0, 7.25))
        self.assertIn("-an", cmd)
        self.assertEqual(cmd[-1], "out.mp4")


class TestScaffold(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = p = Path(self._tmp.name)
        (p / "images").mkdir()
        (p / "images" / "a.png").write_bytes(b"png")
        vdir = versions.next_version(state.voice_root(p, "swim"))
        (vdir / "timing.json").write_text(json.dumps(TIMING))
        (vdir / "narration.wav").write_bytes(b"")
        state.write_meta(vdir, {"duration": TIMING["duration"]})
        settings.use_project(None)
        self.scene = storyboard.parse_markdown(MD)["scenes"][0]

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_scaffold_files(self) -> None:
        """video_scene.scaffold writes prompt.txt (the Brief), background.png, brief.md, timing.json and
        voice_version into scenes/<id>/v1, and status finds the version's brief.md current. Guards the video
        scene version layout."""
        out = video_scene.scaffold(self.project, self.scene)
        self.assertEqual(out, self.project / "scenes" / "swim" / "v1")
        self.assertEqual(sorted(f.name for f in out.iterdir()),
                         ["background.png", "brief.md", "prompt.txt", "timing.json", "voice_version"])
        self.assertEqual((out / "prompt.txt").read_text(), self.scene["brief"] + "\n")
        self.assertEqual((out / scenes.BACKGROUND).read_bytes(), b"png")
        brief = (out / "brief.md").read_text()
        self.assertIn("## Video model", brief)
        self.assertIn("references/video-model.md", brief)
        self.assertEqual((out / "brief.md").read_text(),
                         status.BRIEFS[Engine.VIDEO](self.scene, TIMING, "v1"))

    def test_rescaffold_keeps_prompt(self) -> None:
        """video_scene.scaffold copies the edited prompt.txt from the latest version. Guards a re-scaffold losing
        the agent's prompt."""
        first = video_scene.scaffold(self.project, self.scene)
        (first / "prompt.txt").write_text("Slow push in.\n")
        second = video_scene.scaffold(self.project, self.scene)
        self.assertEqual((second / "prompt.txt").read_text(), "Slow push in.\n")

    def test_refusals(self) -> None:
        """video_scene.scaffold refuses a non-video scene, a scene without voice and a missing image, and
        video_scene.render refuses a scene never scaffolded or with an empty prompt, before any model call.
        Guards the order scaffold, then render."""
        with self.assertRaisesRegex(scenes.SceneError, "not a video scene"):
            video_scene.scaffold(self.project, {"id": "swim", "image": "a.png"})
        with self.assertRaisesRegex(scenes.SceneError, "no voice yet"):
            video_scene.scaffold(self.project, dict(self.scene, id="other"))
        with self.assertRaisesRegex(scenes.SceneError, "nothing.png not found"):
            video_scene.scaffold(self.project, dict(self.scene, image="nothing.png"))
        with self.assertRaisesRegex(scenes.SceneError, "run `scaffold` first"):
            video_scene.render(self.project, self.scene)
        out = video_scene.scaffold(self.project, self.scene)
        (out / "prompt.txt").write_text(" \n")
        with self.assertRaisesRegex(scenes.SceneError, "prompt.txt is empty"):
            video_scene.render(self.project, self.scene)
