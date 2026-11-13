"""Clip scenes (`Engine: clip`): the storyboard rules, the length estimate,
`validate`, the commands that skip or refuse them, and `clip.import_clip`
on clips made with FFmpeg lavfi (skipped without FFmpeg)."""
import argparse
import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from fractions import Fraction
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from short_video_tool import cli, clip, media, mix, music, scenes, settings, state, storyboard, versions
from tests.prereq import requires

MD = """\
# Clips

Topic: Transitions.

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
Image: b.png
Brief: Hold.

| Narration | On screen |
|---|---|
| The same lab today. | hold |

## told
Engine: clip
Image: a.png

| Narration | On screen |
|---|---|
| Then it changes. | the morph |
"""

W, H, FPS = 320, 180, 30
SETTINGS = f"author: [Jane Doe]\nvideo: {{width: {W}, height: {H}, fps: {FPS}}}\n"


def _error(text: str) -> str:
    with unittest.TestCase().assertRaises(storyboard.StoryboardError) as cm:
        storyboard.parse_markdown(text)
    return str(cm.exception)


class TestStoryboard(unittest.TestCase):

    def test_parse(self) -> None:
        """storyboard.parse_markdown reads a silent clip scene (brief, no table) and a narrated one (image,
        table), and is_clip and narrated classify them. Guards the `Engine: clip` storyboard rules."""
        drawing, morph, photo, told = storyboard.parse_markdown(MD)["scenes"]
        self.assertEqual(morph, {"id": "morph", "brief": "The drawing turns into the photograph.",
                                 "engine": "clip", "narration": [], "beats": []})
        self.assertEqual(told, {"id": "told", "image": "a.png", "engine": "clip",
                                "narration": ["Then it changes."], "beats": ["the morph"]})
        self.assertTrue(storyboard.is_clip(morph) and storyboard.is_clip(told))
        self.assertFalse(storyboard.is_clip(drawing))
        self.assertFalse(storyboard.narrated(morph))
        self.assertTrue(storyboard.narrated(told) and storyboard.narrated(photo))

    def test_clip_without_brief_or_image(self) -> None:
        """storyboard.parse_markdown accepts a clip scene with neither Brief nor Image. Guards Brief and Image
        being optional for clip scenes."""
        text = "# T\n\nTopic: x.\n\n## c\nEngine: clip\n"
        self.assertEqual(storyboard.parse_markdown(text)["scenes"],
                         [{"id": "c", "engine": "clip", "narration": [], "beats": []}])

    def test_errors(self) -> None:
        """storyboard.parse_markdown refuses a missing table on non-clip scenes (manim included), Engine on a
        template, an empty table and an unknown engine. Guards a silent scene being allowed only for clips."""
        no_table = "# T\n\nTopic: x.\n\n## a\nImage: a.png\nBrief: b.\n"
        self.assertIn("scene 'a': missing the `| Narration | On screen |` table "
                      "(only an `Engine: clip` scene may have none)", _error(no_table))
        manim = "# T\n\nTopic: x.\n\n## a\nEngine: manim\nBrief: b.\n"
        self.assertIn("only an `Engine: clip` scene may have none", _error(manim))
        template = "# T\n\nTopic: x.\n\n## title\nTemplate: title\nEngine: clip\n"
        msg = _error(template)
        self.assertIn("a template scene takes no `Engine:`", msg)
        self.assertIn("missing the `| Narration | On screen |` table", msg)
        empty = "# T\n\nTopic: x.\n\n## c\nEngine: clip\n\n| Narration | On screen |\n|---|---|\n"
        self.assertIn("scene 'c': the table has no rows", _error(empty))
        self.assertIn("`Engine:` must be one of html, manim, clip",
                      _error("# T\n\nTopic: x.\n\n## c\nEngine: video\n"))


def _meta(project: Path, sid: str, **meta) -> Path:
    sdir = versions.next_version(state.scene_root(project, sid))
    meta.setdefault("clip_duration", meta.get("duration"))
    state.write_meta(sdir, {"scene": sid, "engine": "clip", "voice_version": None, "width": W, "height": H,
                            "fps": FPS, **meta})
    return sdir


def _timing(seconds: float) -> dict:
    return {"duration": seconds, "sentences": [{
        "index": 1, "text": "Then it changes.", "start": 0.25, "end": 1.2,
        "words": [{"text": "Then", "start": 0.25, "end": 0.5}, {"text": "it", "start": 0.55, "end": 0.7},
                  {"text": "changes.", "start": 0.75, "end": 1.2}]}]}


def _write_voice(project: Path, sid: str, seconds: float) -> Path:
    vdir = versions.next_version(state.voice_root(project, sid))
    (vdir / "timing.json").write_text(json.dumps(_timing(seconds)))
    state.write_meta(vdir, {"duration": seconds})
    return vdir


class TestLengthAndValidate(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = p = Path(self._tmp.name)
        (p / "images").mkdir()
        for name in ("a.png", "b.png"):
            (p / "images" / name).write_bytes(b"png")
        (p / "settings.yaml").write_text(SETTINGS)
        (p / "storyboard.md").write_text(MD)
        settings.use_project(p)
        self.data = storyboard.load(p)

    def tearDown(self) -> None:
        settings.use_project(None)
        self._tmp.cleanup()

    def test_estimate(self) -> None:
        """storyboard.estimate_seconds counts a silent clip scene as length.clip_seconds before import and as
        its imported clip after, and music.clip_durations lists it. Guards the length estimate and music length
        with silent clips."""
        words = 5 + 4 + 3
        per = settings.get()["length"]["words_per_second"]
        self.assertAlmostEqual(storyboard.estimate_seconds(self.data), words / per + 6)
        self.assertAlmostEqual(storyboard.estimate_seconds(self.data, self.project), words / per + 6)
        _meta(self.project, "morph", duration=3.5)
        self.assertAlmostEqual(storyboard.estimate_seconds(self.data, self.project), words / per + 3.5)
        self.assertEqual(music.clip_durations(self.project, self.data), [3.5])

    def test_validate_warnings(self) -> None:
        """storyboard.validate warns about clip scenes with no import, an import at another size, a narrated
        clip without a voice version, imported without narration or muxed with an older voice, and a muxed voice
        on a scene that lost its narration. Guards every clip staleness warning."""
        warnings = storyboard.validate(self.data, self.project).warnings
        self.assertIn("scene morph: no clip imported yet; make it at the `video:` size and fps and "
                      "import it with `clip`", warnings)
        self.assertTrue(any(w.startswith("scene told: no clip imported yet") for w in warnings))
        _meta(self.project, "morph", duration=3.5, width=640)
        warnings = storyboard.validate(self.data, self.project).warnings
        self.assertTrue(any(w.startswith(f"scene morph: the imported clip is 640x{H} at {FPS} fps") for w in warnings))
        _meta(self.project, "morph", duration=3.5)
        _meta(self.project, "told", duration=3.5)
        warnings = storyboard.validate(self.data, self.project).warnings
        self.assertFalse(any(w.startswith("scene morph") for w in warnings))
        self.assertIn("scene told: no voice version yet; run `script`, voice it and run `voice`, "
                      "then `clip` again", warnings)
        _write_voice(self.project, "told", 2.0)
        self.assertIn("scene told: the clip was imported without narration; run `clip` again to mux the voice",
                      storyboard.validate(self.data, self.project).warnings)
        _meta(self.project, "told", duration=3.5, voice_version="v1")
        self.assertFalse(any(w.startswith("scene told") and "clip" in w
                             for w in storyboard.validate(self.data, self.project).warnings))
        _write_voice(self.project, "told", 2.0)
        self.assertIn("scene told: the clip was muxed with voice v1, the latest voice version is v2; "
                      "run `clip` again", storyboard.validate(self.data, self.project).warnings)
        _meta(self.project, "morph", duration=3.5, voice_version="v1")
        self.assertIn("scene morph: the scene has no narration now; run `clip` again",
                      storyboard.validate(self.data, self.project).warnings)

    def test_narrated_clip_counts_at_least_its_clip(self) -> None:
        """storyboard.estimate_seconds and music.voice_durations count a narrated clip scene as max(narration,
        clip). Guards the music length when the clip outlasts its narration."""
        per = settings.get()["length"]["words_per_second"]
        told = storyboard.scene_by_id(self.data, "told")
        base = storyboard.estimate_seconds(self.data, self.project)
        _meta(self.project, "told", duration=10.0, clip_duration=10.0)
        self.assertAlmostEqual(storyboard.estimate_seconds(self.data, self.project), base - 3 / per + 10.0)
        _write_voice(self.project, "told", 2.0)
        self.assertEqual(music.voice_durations(self.project, {"scenes": [told]}), [10.0])
        _meta(self.project, "told", duration=2.0, clip_duration=1.0)
        self.assertEqual(music.voice_durations(self.project, {"scenes": [told]}), [2.0])

    def _run(self, func, **kw) -> tuple[str, str]:
        out, err = io.StringIO(), io.StringIO()
        args = argparse.Namespace(project=str(self.project), **kw)
        with redirect_stdout(out), redirect_stderr(err):
            try:
                func(args)
            except SystemExit:
                pass
        return out.getvalue(), err.getvalue()

    def test_script_skips_silent_clip_and_refuses_it_by_name(self) -> None:
        """cli script skips a clip scene without a table, and script and voice refuse it by name. Guards writing
        an empty script for a silent clip."""
        out, _ = self._run(cli._cmd_script, scene=None)
        self.assertIn("sources/narration/told/script.txt", out)
        self.assertNotIn("morph", out)
        self.assertFalse((self.project / "sources" / "narration" / "morph").exists())
        _, err = self._run(cli._cmd_script, scene=["morph"])
        self.assertIn("morph have no narration table", err)
        _, err = self._run(cli._cmd_voice, scene=["morph"], src=None)
        self.assertIn("morph have no narration table", err)

    def test_render_and_scaffold_refuse_clip_scenes(self) -> None:
        """cli render and scaffold refuse a clip scene and point to `clip --scene`. Guards rendering a
        HyperFrames page over an imported clip."""
        for func, name in ((cli._cmd_render, "render"), (cli._cmd_scaffold, "scaffold")):
            _, err = self._run(func, scene="morph")
            self.assertIn(f"scene morph is a clip scene (`Engine: clip`); `{name}` does not apply. "
                          "Import its video with `clip --scene morph FILE`", err)

    def test_length_counts_imported_clips(self) -> None:
        """cli length reports the imported silent clips' seconds and does not count them as unnarrated or
        unimported. Guards the length report with clip scenes."""
        _meta(self.project, "morph", duration=3.5)
        out, err = self._run(cli._cmd_length)
        self.assertIn("clips without narration: 3.5 s", out)
        self.assertIn("3 scene(s) have no narration yet", err)
        self.assertNotIn("no imported clip", err)

    def test_sources_skip_silent_clips(self) -> None:
        """mix.sources lists no narration for a silent clip scene (voice_version null). Guards audiocheck being
        given a missing narration file."""
        _meta(self.project, "morph", duration=3.5)
        self.assertEqual(mix.sources(self.project, self.data), [])


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def _testsrc(path: Path, seconds: float, size: str = f"{W}x{H}", fps: int = FPS) -> Path:
    _ffmpeg("-f", "lavfi", "-i", f"testsrc=size={size}:rate={fps}:duration={seconds}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path))
    return path


def _video(path: Path) -> dict:
    return next(s for s in media.probe(path)["streams"] if s["codec_type"] == "video")


@requires(shutil.which("ffmpeg") is not None, "ffmpeg not installed (brew install ffmpeg)")
class TestImport(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project = p = Path(self._tmp.name) / "project"
        (p / "images").mkdir(parents=True)
        (p / "settings.yaml").write_text(SETTINGS)
        settings.use_project(p)
        self.morph, self.told = (storyboard.scene_by_id(storyboard.parse_markdown(MD), sid)
                                 for sid in ("morph", "told"))
        self.src = Path(self._tmp.name) / "src"
        self.src.mkdir()

    def tearDown(self) -> None:
        settings.use_project(None)
        self._tmp.cleanup()

    def _voice(self, seconds: float) -> Path:
        vdir = versions.next_version(state.voice_root(self.project, "told"))
        _ffmpeg("-f", "lavfi", "-i", f"sine=frequency=330:sample_rate=24000:duration={seconds}",
                str(vdir / "narration.wav"))
        (vdir / "timing.json").write_text(json.dumps(_timing(seconds)))
        state.write_meta(vdir, {"duration": seconds})
        return vdir

    def test_silent_clip(self) -> None:
        """clip.import_clip of a silent clip writes clip.mp4 unchanged, silent.mp4 re-encoded with the `encode:`
        codec, fps and SAR 1:1, scene.mp4 with silent audio, contact sheet, brief and meta.json with source,
        sha256 and durations. Guards the clip version layout assemble and frames read."""
        src = _testsrc(self.src / "morph.mp4", 2)
        out = clip.import_clip(self.project, self.morph, src)
        sdir = self.project / "scenes" / "morph" / "v1"
        self.assertEqual(out, sdir / "scene.mp4")
        self.assertEqual(sorted(f.name for f in sdir.iterdir()),
                         ["brief.md", "clip.mp4", "contact.png", "meta.json", "scene.mp4", "silent.mp4"])
        self.assertEqual((sdir / "clip.mp4").read_bytes(), src.read_bytes())
        silent = _video(sdir / "silent.mp4")
        self.assertEqual((silent["codec_name"], silent["pix_fmt"], silent["r_frame_rate"]), ("h264", "yuv420p", "30/1"))
        self.assertEqual((silent["width"], silent["height"], silent.get("sample_aspect_ratio", "1:1")), (W, H, "1:1"))
        streams = media.probe(out)["streams"]
        self.assertEqual(sorted(s["codec_type"] for s in streams), ["audio", "video"])
        self.assertAlmostEqual(media.duration(out), 2.0, delta=0.05)
        meta = state.read_meta(sdir)
        self.assertEqual(state.latest_render(self.project, "morph"), sdir)
        self.assertEqual((meta["engine"], meta["voice_version"], meta["fps"], meta["clip"]), ("clip", None, FPS, "clip.mp4"))
        self.assertEqual(meta["source"], str(src.resolve()))
        self.assertEqual(meta["sha256"], hashlib.sha256(src.read_bytes()).hexdigest())
        self.assertAlmostEqual(meta["clip_duration"], 2.0, delta=0.05)
        self.assertAlmostEqual(meta["duration"], 2.0, delta=0.05)
        self.assertIn("The drawing turns into the photograph.", (sdir / "brief.md").read_text())
        self.assertIn("Narration: none (silent)", (sdir / "brief.md").read_text())
        self.assertEqual(len(scenes.frames(self.project, "morph", [1.0])), 1)

    def test_wrong_size_or_fps_refused(self) -> None:
        """clip.import_clip refuses another size, another fps and a file without video, and leaves no version.
        Guards assemble's concat getting inputs of one size and rate."""
        for name, kw in (("big.mp4", {"size": "640x360"}), ("slow.mp4", {"fps": 25})):
            src = _testsrc(self.src / name, 1, **kw)
            with self.assertRaises(scenes.SceneError) as cm:
                clip.import_clip(self.project, self.morph, src)
            self.assertIn(f"the film needs {W}x{H} at {FPS} fps (`video:` in settings.yaml)", str(cm.exception))
        self.assertIsNone(state.latest_scene(self.project, "morph"))
        audio = self.src / "tone.wav"
        _ffmpeg("-f", "lavfi", "-i", "sine=duration=1", str(audio))
        with self.assertRaisesRegex(scenes.SceneError, "has no video stream"):
            clip.import_clip(self.project, self.morph, audio)

    def test_refusals(self) -> None:
        """clip.import_clip refuses a non-clip scene, a narrated clip scene without a voice version and a
        missing file. Guards the checks before any copy."""
        src = _testsrc(self.src / "c.mp4", 1)
        with self.assertRaisesRegex(scenes.SceneError, "is not a clip scene"):
            clip.import_clip(self.project, {"id": "drawing", "image": "a.png", "narration": ["x"]}, src)
        with self.assertRaisesRegex(scenes.SceneError, "scene told: no voice yet"):
            clip.import_clip(self.project, self.told, src)
        with self.assertRaisesRegex(scenes.SceneError, "not found"):
            clip.import_clip(self.project, self.morph, self.src / "missing.mp4")

    def test_narrated_clip_held_to_the_narration(self) -> None:
        """clip.import_clip holds a clip shorter than its narration on the last frame to the narration length,
        records the voice version and writes the brief with sentence and word times. Guards tpad=stop_mode=clone
        and the narrated clip's sources."""
        vdir = self._voice(3.0)
        out = clip.import_clip(self.project, self.told, _testsrc(self.src / "short.mp4", 2))
        self.assertAlmostEqual(media.video_duration(out), 3.0, delta=1.5 / FPS)
        self.assertAlmostEqual(media.duration(out), 3.0, delta=0.05)
        meta = state.read_meta(out.parent)
        self.assertEqual(meta["voice_version"], vdir.name)
        self.assertAlmostEqual(meta["clip_duration"], 2.0, delta=0.05)
        brief = (out.parent / "brief.md").read_text()
        self.assertIn('1. S(1)=0.25 to SE(1)=1.20: "Then it changes."', brief)
        self.assertIn("   - Words: Then 0.25, it 0.55, changes. 0.75", brief)
        self.assertIn("   - Beat: the morph", brief)
        self.assertEqual(mix.sources(self.project, {"scenes": [self.told]}), [vdir / "narration.wav"])

    def test_narrated_clip_longer_than_the_narration(self) -> None:
        """clip.import_clip of a clip longer than its narration keeps the clip length and pads the audio to it.
        Guards apad,atrim to the video length in scenes.finish."""
        self._voice(1.5)
        out = clip.import_clip(self.project, self.told, _testsrc(self.src / "long.mp4", 3))
        self.assertAlmostEqual(media.video_duration(out), 3.0, delta=1.5 / FPS)
        audio = next(s for s in media.probe(out)["streams"] if s["codec_type"] == "audio")
        self.assertAlmostEqual(float(audio["duration"]), 3.0, delta=0.05)

    def test_audio_stream_warned_and_dropped(self) -> None:
        """clip.import_clip warns that a clip's own audio is not used and drops it from silent.mp4. Guards the
        clip's sound reaching the film."""
        src = self.src / "with_audio.mp4"
        _ffmpeg("-f", "lavfi", "-i", f"testsrc=size={W}x{H}:rate={FPS}:duration=1",
                "-f", "lavfi", "-i", "sine=frequency=880:duration=1",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(src))
        err = io.StringIO()
        with redirect_stderr(err):
            out = clip.import_clip(self.project, self.morph, src)
        self.assertIn(f"{src} has an audio stream; the clip's audio is not used", err.getvalue())
        self.assertNotIn("audio", [s["codec_type"] for s in media.probe(out.parent / "silent.mp4")["streams"]])

    def test_ntsc_rate(self) -> None:
        """clip.same_rate accepts 30000/1001 for 29.97 and refuses 25 or 30 against other rates, and import_clip
        accepts an NTSC clip. Guards the limit_denominator(1001) rate comparison."""
        (self.project / "settings.yaml").write_text(SETTINGS.replace(f"fps: {FPS}", "fps: 29.97"))
        settings.use_project(self.project)
        src = self.src / "ntsc.mp4"
        _ffmpeg("-f", "lavfi", "-i", f"testsrc=size={W}x{H}:rate=30000/1001:duration=1",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src))
        out = clip.import_clip(self.project, self.morph, src)
        self.assertAlmostEqual(media.video_duration(out), 1.0, delta=0.05)
        self.assertTrue(clip.same_rate(Fraction(30000, 1001), 29.97))
        self.assertTrue(clip.same_rate(Fraction(30), 30))
        self.assertFalse(clip.same_rate(Fraction(25), 30))
        self.assertFalse(clip.same_rate(Fraction(30), 29.97))


if __name__ == "__main__":
    unittest.main()
